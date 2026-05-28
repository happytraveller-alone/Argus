use async_trait::async_trait;
use reqwest::{Client, Url};
use serde_json::json;

use crate::runtime::intelligent::{
    config::{IntelligentLlmConfig, IntelligentLlmProvider},
    types::{now_rfc3339, IntelligentTaskEvent},
};

/// Maximum number of HTTP attempts (1 initial + 2 retries = 3 total).
const MAX_HTTP_ATTEMPTS: u32 = 3;

/// Hard upper bound on bytes copied out of the HTTP body for diagnostics.
/// Beyond this we truncate and append an ellipsis marker. Keeps memory and
/// log volume bounded when the gateway returns a multi-megabyte HTML error page.
const RAW_BODY_PREVIEW_BYTES: usize = 2048;

/// Build a truncated preview of a text payload that is safe to embed in an
/// event-log JSON object. Indicates truncation with a trailing marker so a
/// human reading the log knows the string is not the full content.
///
/// The cap is supplied per-call via `IntelligentLlmConfig.preview_chars`,
/// which is threaded from `AppConfig.intelligent_llm_preview_chars` and
/// defaults to 16384 (env: `INTELLIGENT_LLM_PREVIEW_CHARS`).
pub(crate) fn build_text_preview(text: &str, max_chars: usize) -> String {
    let total = text.chars().count();
    if total <= max_chars {
        return text.to_string();
    }
    let head: String = text.chars().take(max_chars).collect();
    format!("{head}…[truncated {} chars]", total - max_chars)
}

/// Build a truncated preview of raw response bytes. The gateway response is
/// expected to be UTF-8 JSON but on failure may be anything (HTML, binary,
/// partial bytes), so we render via lossy UTF-8 conversion.
fn build_body_preview(body: &[u8]) -> String {
    let head = if body.len() <= RAW_BODY_PREVIEW_BYTES {
        body
    } else {
        &body[..RAW_BODY_PREVIEW_BYTES]
    };
    let text = String::from_utf8_lossy(head).to_string();
    if body.len() > RAW_BODY_PREVIEW_BYTES {
        format!(
            "{text}…[truncated {} bytes]",
            body.len() - RAW_BODY_PREVIEW_BYTES
        )
    } else {
        text
    }
}

/// Compute wait duration for a transient HTTP error.
///
/// Honors the `Retry-After` header when present (parsed as seconds).
/// Falls back to exponential back-off: 1 s, 2 s, 4 s, … (1 << attempt).
fn compute_retry_wait(attempt: u32, retry_after_secs: Option<u64>) -> std::time::Duration {
    let secs = retry_after_secs.unwrap_or(1u64 << attempt);
    std::time::Duration::from_secs(secs)
}

/// Return `true` when the HTTP status warrants a retry (rate-limited or
/// transient server error).
fn is_retryable_status(status: reqwest::StatusCode) -> bool {
    status.as_u16() == 429 || status.is_server_error()
}

/// Build the OpenAI-compatible request body. Extracted as a pure helper so the
/// `response_format: {"type": "json_object"}` constraint can be unit-tested
/// without spinning up an HTTP client. See AC-B3 — JSON-mode enforcement is
/// load-bearing for the prompt's contract that the response is a JSON object.
pub(crate) fn build_openai_body(
    model: &str,
    prompt: &str,
    max_tokens: i64,
    temperature: f64,
) -> serde_json::Value {
    json!({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": false,
        "response_format": {"type": "json_object"},
    })
}

/// Build the Anthropic-compatible request body with the prefill assistant turn
/// that seeds the response with `{`. Extracted as a pure helper so the prefill
/// shape can be unit-tested without spinning up an HTTP client. See AC-B4 —
/// the prefill is what makes `stitch_prefill` necessary downstream.
pub(crate) fn build_anthropic_body(
    model: &str,
    prompt: &str,
    max_tokens: i64,
) -> serde_json::Value {
    json!({
        "model": model,
        "system": "You are a security audit assistant. Respond ONLY with the requested JSON object. Do not use any tools. Do not call any functions. Output raw JSON text directly.",
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "{"},
        ],
        "max_tokens": max_tokens,
    })
}

/// Stitch the leading `{` back onto an Anthropic prefill response if the model
/// continued the prefill without re-emitting the brace. Idempotent across three
/// shapes:
///   1. Content already starts with `{` → return as-is (already object-shaped).
///   2. Content starts AND ends with `"` (a string-encoded / double-encoded
///      JSON literal such as `"{\"k\":1}"`) → return as-is so downstream
///      `unwrap_stringified_json` still applies.
///   3. Otherwise the model continued the prefill `{` without echoing it →
///      prepend `{`. This is the common case for Anthropic prefill: the
///      assistant turn ends with `{`, and the model continues with the inner
///      object content (typically a key literal such as `"key":"value"}`).
///      Without the start+end discriminator in case 2, that continuation
///      would be mis-classified as already-encoded and the leading `{` would
///      never be restored.
pub(crate) fn stitch_prefill(raw: String) -> String {
    let trimmed = raw.trim();
    if trimmed.starts_with('{') {
        return raw;
    }
    if trimmed.starts_with('"') && trimmed.ends_with('"') {
        return raw;
    }
    format!("{{{raw}")
}

#[derive(Clone, Debug)]
pub struct IntelligentLlmInvocation {
    pub content: String,
    pub finished_at: String,
    pub attempt_event: IntelligentTaskEvent,
}

#[derive(Clone, Debug)]
pub struct IntelligentLlmInvocationError {
    pub stage: &'static str,
    pub redacted_message: String,
    /// `llm_attempt` event carrying prompt/response/raw-body previews and
    /// HTTP status. Emitted by the pipeline layer (`invoke_json`) so the
    /// failure attempt surfaces in the task event log alongside the
    /// audit_pipeline_failed marker that comes from `task.rs`. Without this,
    /// the user only sees the opaque `[llm_request] ...` string and has no
    /// way to inspect what the gateway actually returned.
    pub attempt_event: IntelligentTaskEvent,
}

impl std::fmt::Display for IntelligentLlmInvocationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.stage, self.redacted_message)
    }
}

impl std::error::Error for IntelligentLlmInvocationError {}

/// Outcome of a single end-to-end LLM HTTP exchange. Returned by the inner
/// provider-specific methods so `invoke()` can build a single rich
/// `llm_attempt` event regardless of provider or success/failure status.
struct AttemptOutcome {
    /// Extracted text content. Empty when `error` is set.
    content: String,
    /// Truncated UTF-8 preview of the raw HTTP response body, populated
    /// whenever bytes were read (success or decode-failure). Lets the
    /// time-log show exactly what the upstream gateway returned when the
    /// body was not parseable as the expected JSON shape.
    raw_body_preview: Option<String>,
    /// HTTP status code of the final attempt (last retry).
    http_status: Option<u16>,
    /// Total HTTP attempts made (1..=MAX_HTTP_ATTEMPTS).
    attempts: u32,
    /// Redacted error description when the call did not yield usable content.
    error: Option<String>,
}

#[async_trait]
pub trait IntelligentLlmInvoker {
    async fn invoke(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError>;
}

/// Append a fixed endpoint segment to the configured `base_url`.
///
/// `Url::join` follows RFC 3986 §5.3 — when the base URL has no trailing slash,
/// its last path segment is **replaced** instead of preserved. Concretely,
/// `Url::parse("https://host/v1").join("chat/completions")` resolves to
/// `https://host/chat/completions` (the `/v1` is dropped). The preflight path
/// in `crate::llm::tester` avoids this by trimming the trailing slash and
/// appending `"/<endpoint>"` via `format!`. This helper keeps both code paths
/// in sync so a base URL such as `https://gateway/v1` (without trailing slash)
/// still hits `https://gateway/v1/chat/completions` like the preflight does.
fn build_endpoint_url(base_url: &Url, endpoint: &str) -> Result<Url, String> {
    let trimmed_base = base_url.as_str().trim_end_matches('/');
    let trimmed_endpoint = endpoint.trim_start_matches('/');
    let combined = format!("{trimmed_base}/{trimmed_endpoint}");
    Url::parse(&combined).map_err(|e| e.to_string())
}

/// Redact sensitive values from a string before it enters logs or event records.
/// Replaces the api_key with `***`.
pub fn redact_for_logging(raw: &str, config: &IntelligentLlmConfig) -> String {
    let mut result = raw.to_string();
    if !config.api_key.is_empty() {
        result = result.replace(&config.api_key, "***");
    }
    result
}

pub struct HttpIntelligentLlmInvoker {
    client: Client,
}

impl Default for HttpIntelligentLlmInvoker {
    fn default() -> Self {
        Self {
            client: Client::builder()
                .no_proxy()
                .build()
                .expect("failed to build no-proxy HTTP client"),
        }
    }
}

impl HttpIntelligentLlmInvoker {
    pub fn with_client(client: Client) -> Self {
        Self { client }
    }
}

#[async_trait]
impl IntelligentLlmInvoker for HttpIntelligentLlmInvoker {
    async fn invoke(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
        let started_at = now_rfc3339();
        let timeout = std::time::Duration::from_millis(config.timeout_ms.max(1) as u64);

        let outcome = match config.provider {
            IntelligentLlmProvider::OpenAiCompatible => {
                self.invoke_openai(prompt, config, timeout).await
            }
            IntelligentLlmProvider::AnthropicCompatible => {
                self.invoke_anthropic(prompt, config, timeout).await
            }
        };

        let finished_at = now_rfc3339();
        build_invocation_result(prompt, config, &started_at, &finished_at, outcome)
    }
}

/// Translate the raw provider outcome into the public Result the trait
/// returns, building the rich `llm_attempt` event in a single place so both
/// providers share the same shape. The event is always populated — on
/// failure it is moved into the error so the pipeline layer can emit it.
fn build_invocation_result(
    prompt: &str,
    config: &IntelligentLlmConfig,
    started_at: &str,
    finished_at: &str,
    outcome: AttemptOutcome,
) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
    let content_is_empty = outcome.content.trim().is_empty();
    let success = outcome.error.is_none() && !content_is_empty;

    let prompt_chars = prompt.chars().count();
    let prompt_preview =
        redact_for_logging(&build_text_preview(prompt, config.preview_chars), config);

    let mut data = json!({
        "provider": format!("{:?}", config.provider),
        "model": config.model,
        "fingerprint": config.llm_fingerprint_for_log(),
        "started": started_at,
        "completed": finished_at,
        "success": success,
        "attempts": outcome.attempts,
        "promptChars": prompt_chars,
        "promptPreview": prompt_preview,
    });

    if let Some(status) = outcome.http_status {
        data["httpStatus"] = json!(status);
    }
    if let Some(raw) = outcome.raw_body_preview.as_deref() {
        data["rawBodyPreview"] = json!(redact_for_logging(raw, config));
    }

    if success {
        let response_chars = outcome.content.chars().count();
        let response_preview = redact_for_logging(
            &build_text_preview(&outcome.content, config.preview_chars),
            config,
        );
        data["responseChars"] = json!(response_chars);
        data["responsePreview"] = json!(response_preview);

        let attempt_event = IntelligentTaskEvent::new("llm_attempt").with_data(data);
        Ok(IntelligentLlmInvocation {
            content: outcome.content,
            finished_at: finished_at.to_string(),
            attempt_event,
        })
    } else {
        let error_text = outcome
            .error
            .unwrap_or_else(|| "LLM returned empty response".to_string());
        let redacted_message = redact_for_logging(&error_text, config);
        data["redacted_error"] = json!(redacted_message.clone());

        let attempt_event = IntelligentTaskEvent::new("llm_attempt").with_data(data);
        Err(IntelligentLlmInvocationError {
            stage: "llm_request",
            redacted_message,
            attempt_event,
        })
    }
}

impl HttpIntelligentLlmInvoker {
    async fn invoke_openai(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
        timeout: std::time::Duration,
    ) -> AttemptOutcome {
        let url = match build_endpoint_url(&config.base_url, "chat/completions") {
            Ok(u) => u,
            Err(e) => {
                return AttemptOutcome {
                    content: String::new(),
                    raw_body_preview: None,
                    http_status: None,
                    attempts: 0,
                    error: Some(redact_for_logging(&e, config)),
                };
            }
        };

        let body = build_openai_body(
            &config.model,
            prompt,
            config.max_tokens_per_call,
            config.temperature,
        );

        let mut last_err = String::new();
        let mut last_status: Option<u16> = None;
        let mut attempts: u32 = 0;
        for attempt in 0..MAX_HTTP_ATTEMPTS {
            attempts = attempt + 1;
            let response = match self
                .client
                .post(url.clone())
                .timeout(timeout)
                .bearer_auth(&config.api_key)
                .json(&body)
                .send()
                .await
            {
                Ok(r) => r,
                Err(e) => {
                    return AttemptOutcome {
                        content: String::new(),
                        raw_body_preview: None,
                        http_status: last_status,
                        attempts,
                        error: Some(redact_for_logging(&e.to_string(), config)),
                    };
                }
            };

            let status = response.status();
            last_status = Some(status.as_u16());
            if is_retryable_status(status) {
                let retry_after = response
                    .headers()
                    .get("retry-after")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|s| s.parse::<u64>().ok());
                let wait = compute_retry_wait(attempt, retry_after);
                last_err = format!("HTTP {status}");
                tracing::warn!(
                    status = status.as_u16(),
                    attempt,
                    wait_secs = wait.as_secs(),
                    "invoke_openai: retrying after transient error"
                );
                tokio::time::sleep(wait).await;
                continue;
            }

            // Read raw bytes first so we can show the gateway response in
            // event logs when JSON decoding fails. `response.json()` swallows
            // the body before yielding its opaque "error decoding response
            // body" message — the actual root cause (HTML error page, empty
            // body, partial chunk, content-type mismatch) becomes invisible.
            //
            // Body-stream failures (chunk read timeout, premature EOF, h2
            // RST_STREAM, brotli/gzip decode error) are transient: the gateway
            // accepted the request and started streaming, then the connection
            // dropped. Treat them like 429/5xx and retry instead of failing
            // the whole stage on the first hiccup.
            let bytes = match response.bytes().await {
                Ok(b) => b,
                Err(e) => {
                    last_err = format!("HTTP body read failed: {e}");
                    tracing::warn!(
                        attempt,
                        error = %e,
                        "invoke_openai: body read failed; retrying"
                    );
                    let wait = compute_retry_wait(attempt, None);
                    tokio::time::sleep(wait).await;
                    continue;
                }
            };

            let raw_preview = build_body_preview(&bytes);

            if !status.is_success() {
                return AttemptOutcome {
                    content: String::new(),
                    raw_body_preview: Some(raw_preview),
                    http_status: last_status,
                    attempts,
                    error: Some(format!("HTTP {status}")),
                };
            }

            let json: serde_json::Value = match serde_json::from_slice(&bytes) {
                Ok(v) => v,
                Err(e) => {
                    return AttemptOutcome {
                        content: String::new(),
                        raw_body_preview: Some(raw_preview),
                        http_status: last_status,
                        attempts,
                        error: Some(redact_for_logging(
                            &format!("error decoding response body: {e}"),
                            config,
                        )),
                    };
                }
            };

            let content = json["choices"][0]["message"]["content"]
                .as_str()
                .unwrap_or("")
                .to_string();
            return AttemptOutcome {
                content,
                raw_body_preview: Some(raw_preview),
                http_status: last_status,
                attempts,
                error: None,
            };
        }

        AttemptOutcome {
            content: String::new(),
            raw_body_preview: None,
            http_status: last_status,
            attempts,
            error: Some(if last_err.is_empty() {
                "exhausted HTTP retries".to_string()
            } else {
                last_err
            }),
        }
    }

    async fn invoke_anthropic(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
        timeout: std::time::Duration,
    ) -> AttemptOutcome {
        let url = match build_endpoint_url(&config.base_url, "messages") {
            Ok(u) => u,
            Err(e) => {
                return AttemptOutcome {
                    content: String::new(),
                    raw_body_preview: None,
                    http_status: None,
                    attempts: 0,
                    error: Some(redact_for_logging(&e, config)),
                };
            }
        };

        let body = build_anthropic_body(&config.model, prompt, config.max_tokens_per_call);

        let mut last_err = String::new();
        let mut last_status: Option<u16> = None;
        let mut attempts: u32 = 0;
        for attempt in 0..MAX_HTTP_ATTEMPTS {
            attempts = attempt + 1;
            let response = match self
                .client
                .post(url.clone())
                .timeout(timeout)
                .header("x-api-key", &config.api_key)
                .header("anthropic-version", "2023-06-01")
                .json(&body)
                .send()
                .await
            {
                Ok(r) => r,
                Err(e) => {
                    return AttemptOutcome {
                        content: String::new(),
                        raw_body_preview: None,
                        http_status: last_status,
                        attempts,
                        error: Some(redact_for_logging(&e.to_string(), config)),
                    };
                }
            };

            let status = response.status();
            last_status = Some(status.as_u16());
            if is_retryable_status(status) {
                let retry_after = response
                    .headers()
                    .get("retry-after")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|s| s.parse::<u64>().ok());
                let wait = compute_retry_wait(attempt, retry_after);
                last_err = format!("HTTP {status}");
                tracing::warn!(
                    status = status.as_u16(),
                    attempt,
                    wait_secs = wait.as_secs(),
                    "invoke_anthropic: retrying after transient error"
                );
                tokio::time::sleep(wait).await;
                continue;
            }

            // Body-stream failures (chunk read timeout, premature EOF, h2
            // RST_STREAM, brotli/gzip decode error) are transient — retry
            // rather than failing the whole stage on the first hiccup.
            let bytes = match response.bytes().await {
                Ok(b) => b,
                Err(e) => {
                    last_err = format!("HTTP body read failed: {e}");
                    tracing::warn!(
                        attempt,
                        error = %e,
                        "invoke_anthropic: body read failed; retrying"
                    );
                    let wait = compute_retry_wait(attempt, None);
                    tokio::time::sleep(wait).await;
                    continue;
                }
            };
            let raw_preview = build_body_preview(&bytes);

            if !status.is_success() {
                return AttemptOutcome {
                    content: String::new(),
                    raw_body_preview: Some(raw_preview),
                    http_status: last_status,
                    attempts,
                    error: Some(format!("HTTP {status}")),
                };
            }

            let json: serde_json::Value = match serde_json::from_slice(&bytes) {
                Ok(v) => v,
                Err(e) => {
                    return AttemptOutcome {
                        content: String::new(),
                        raw_body_preview: Some(raw_preview),
                        http_status: last_status,
                        attempts,
                        error: Some(redact_for_logging(
                            &format!("error decoding response body: {e}"),
                            config,
                        )),
                    };
                }
            };

            let content_array = json.get("content").and_then(|c| c.as_array());

            // Primary: extract first non-empty text block
            let text_content = content_array
                .and_then(|arr| {
                    arr.iter()
                        .filter(|item| item.get("type").and_then(|t| t.as_str()) == Some("text"))
                        .find_map(|item| {
                            let t = item.get("text").and_then(|t| t.as_str()).unwrap_or("");
                            if t.trim().is_empty() {
                                None
                            } else {
                                Some(t.to_string())
                            }
                        })
                })
                .unwrap_or_default();

            // Fallback: if proxy injected tools and model put output in tool_use input
            let content_raw = if text_content.is_empty() {
                let tool_content = content_array
                    .and_then(|arr| {
                        arr.iter()
                            .filter(|item| {
                                item.get("type").and_then(|t| t.as_str()) == Some("tool_use")
                            })
                            .find_map(|item| {
                                let input = item.get("input")?;
                                if input.is_object() || input.is_array() {
                                    Some(serde_json::to_string(input).unwrap_or_default())
                                } else {
                                    input.as_str().map(|s| s.to_string())
                                }
                            })
                    })
                    .unwrap_or_default();
                if tool_content.is_empty() {
                    tracing::warn!(
                        stage = "anthropic_empty_response",
                        content_array_len = content_array.map(|a| a.len()),
                        stop_reason = ?json.get("stop_reason"),
                        "invoke_anthropic: no usable content in response"
                    );
                }
                tool_content
            } else {
                text_content
            };

            // Anthropic prefill mode: we sent assistant `{` as the seed turn; the
            // model continues from there and typically does NOT echo the brace.
            // Restore it here so downstream `parse_json` sees a complete object.
            // Idempotent for the (1) already-object and (2) double-encoded shapes.
            let content = stitch_prefill(content_raw);

            return AttemptOutcome {
                content,
                raw_body_preview: Some(raw_preview),
                http_status: last_status,
                attempts,
                error: None,
            };
        }

        AttemptOutcome {
            content: String::new(),
            raw_body_preview: None,
            http_status: last_status,
            attempts,
            error: Some(if last_err.is_empty() {
                "exhausted HTTP retries".to_string()
            } else {
                last_err
            }),
        }
    }
}

// Helper to expose fingerprint safely for logging (it's already a hash, not a secret)
trait LlmConfigLogHelper {
    fn llm_fingerprint_for_log(&self) -> &str;
}

impl LlmConfigLogHelper for IntelligentLlmConfig {
    fn llm_fingerprint_for_log(&self) -> &str {
        &self.fingerprint
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_config_with_key(api_key: &str) -> IntelligentLlmConfig {
        use reqwest::Url;
        IntelligentLlmConfig {
            row_id: "test".to_string(),
            provider: IntelligentLlmProvider::OpenAiCompatible,
            model: "gpt-test".to_string(),
            base_url: Url::parse("https://api.example.com/v1/").unwrap(),
            api_key: api_key.to_string(),
            fingerprint: "sha256:abc123".to_string(),
            timeout_ms: 30000,
            temperature: 0.0,
            max_tokens_per_call: 1024,
            first_token_timeout_seconds: 30,
            stream_timeout_seconds: 60,
            custom_header_names: vec![],
            auth_kind: "openai_compatible_bearer",
            preview_chars: 16_384,
        }
    }

    // ── AC2.1 helpers ──────────────────────────────────────────────────────

    #[test]
    fn compute_retry_wait_uses_retry_after_header_when_present() {
        let d = compute_retry_wait(0, Some(30));
        assert_eq!(d.as_secs(), 30);
    }

    #[test]
    fn compute_retry_wait_exponential_backoff_when_no_header() {
        assert_eq!(compute_retry_wait(0, None).as_secs(), 1); // 1 << 0
        assert_eq!(compute_retry_wait(1, None).as_secs(), 2); // 1 << 1
        assert_eq!(compute_retry_wait(2, None).as_secs(), 4); // 1 << 2
    }

    #[test]
    fn is_retryable_status_429_and_5xx() {
        assert!(is_retryable_status(reqwest::StatusCode::TOO_MANY_REQUESTS));
        assert!(is_retryable_status(
            reqwest::StatusCode::INTERNAL_SERVER_ERROR
        ));
        assert!(is_retryable_status(
            reqwest::StatusCode::SERVICE_UNAVAILABLE
        ));
        assert!(!is_retryable_status(reqwest::StatusCode::OK));
        assert!(!is_retryable_status(reqwest::StatusCode::BAD_REQUEST));
        assert!(!is_retryable_status(reqwest::StatusCode::UNAUTHORIZED));
    }

    // ── AC2.3 — invoker retry integration tests ───────────────────────────

    /// When the server always returns 429, the invoker exhausts MAX_HTTP_ATTEMPTS
    /// (3) and returns Err. Verifies the retry loop fires all 3 attempts.
    #[tokio::test]
    async fn invoker_exhausts_retries_on_persistent_429() {
        use httpmock::prelude::*;
        use reqwest::Url;

        let server = MockServer::start();
        let mock_429 = server.mock(|when, then| {
            when.method(POST).path("/v1/chat/completions");
            then.status(429).header("retry-after", "0");
        });

        let base_url = Url::parse(&format!("http://{}/v1/", server.address())).unwrap();
        let config = IntelligentLlmConfig {
            row_id: "test".to_string(),
            provider: IntelligentLlmProvider::OpenAiCompatible,
            model: "gpt-test".to_string(),
            base_url,
            api_key: "sk-test".to_string(),
            fingerprint: "sha256:test".to_string(),
            timeout_ms: 5000,
            temperature: 0.0,
            max_tokens_per_call: 128,
            first_token_timeout_seconds: 5,
            stream_timeout_seconds: 10,
            custom_header_names: vec![],
            auth_kind: "openai_compatible_bearer",
            preview_chars: 16_384,
        };

        let invoker = HttpIntelligentLlmInvoker::default();
        let result = invoker.invoke("test prompt", &config).await;

        // All 3 attempts must have been made before giving up.
        mock_429.assert_calls(MAX_HTTP_ATTEMPTS as usize);
        assert!(result.is_err(), "expected Err after exhausting retries");
    }

    /// When the server returns 200 immediately, invoke succeeds on first attempt.
    #[tokio::test]
    async fn invoker_succeeds_on_first_200() {
        use httpmock::prelude::*;
        use reqwest::Url;

        let server = MockServer::start();
        let mock_200 = server.mock(|when, then| {
            when.method(POST).path("/v1/chat/completions");
            then.status(200)
                .header("content-type", "application/json")
                .body(r#"{"choices":[{"message":{"content":"hello"}}]}"#);
        });

        let base_url = Url::parse(&format!("http://{}/v1/", server.address())).unwrap();
        let config = IntelligentLlmConfig {
            row_id: "test".to_string(),
            provider: IntelligentLlmProvider::OpenAiCompatible,
            model: "gpt-test".to_string(),
            base_url,
            api_key: "sk-test".to_string(),
            fingerprint: "sha256:test".to_string(),
            timeout_ms: 5000,
            temperature: 0.0,
            max_tokens_per_call: 128,
            first_token_timeout_seconds: 5,
            stream_timeout_seconds: 10,
            custom_header_names: vec![],
            auth_kind: "openai_compatible_bearer",
            preview_chars: 16_384,
        };

        let invoker = HttpIntelligentLlmInvoker::default();
        let result = invoker.invoke("test prompt", &config).await;

        mock_200.assert_calls(1);
        assert!(result.is_ok(), "expected Ok on 200: {result:?}");
        assert_eq!(result.unwrap().content, "hello");
    }

    #[test]
    fn redact_for_logging_removes_api_key() {
        let config = make_config_with_key("sk-super-secret-key");
        let raw = "error calling https://api.example.com?key=sk-super-secret-key";
        let redacted = redact_for_logging(raw, &config);
        assert!(
            !redacted.contains("sk-super-secret-key"),
            "api_key must not appear in redacted output: {redacted}"
        );
        assert!(redacted.contains("***"));
    }

    #[test]
    fn redact_for_logging_empty_key_is_noop() {
        let config = make_config_with_key("");
        let raw = "some error message";
        let redacted = redact_for_logging(raw, &config);
        assert_eq!(redacted, raw);
    }

    #[test]
    fn build_endpoint_url_preserves_versioned_path_without_trailing_slash() {
        let base = Url::parse("https://gateway.example/v1").unwrap();
        let url = build_endpoint_url(&base, "chat/completions").unwrap();
        assert_eq!(
            url.as_str(),
            "https://gateway.example/v1/chat/completions",
            "base without trailing slash must keep /v1 in the resolved URL",
        );
    }

    #[test]
    fn build_endpoint_url_preserves_versioned_path_with_trailing_slash() {
        let base = Url::parse("https://gateway.example/v1/").unwrap();
        let url = build_endpoint_url(&base, "chat/completions").unwrap();
        assert_eq!(url.as_str(), "https://gateway.example/v1/chat/completions",);
    }

    #[test]
    fn build_endpoint_url_handles_root_base() {
        let base = Url::parse("https://gateway.example").unwrap();
        let url = build_endpoint_url(&base, "chat/completions").unwrap();
        assert_eq!(url.as_str(), "https://gateway.example/chat/completions");
    }

    #[test]
    fn build_endpoint_url_strips_leading_slash_in_endpoint() {
        let base = Url::parse("https://gateway.example/v1").unwrap();
        let url = build_endpoint_url(&base, "/chat/completions").unwrap();
        assert_eq!(
            url.as_str(),
            "https://gateway.example/v1/chat/completions",
            "leading slash in endpoint must not produce a double slash",
        );
    }

    #[test]
    fn build_endpoint_url_matches_preflight_anthropic_messages() {
        let base = Url::parse("https://api.anthropic.com/v1").unwrap();
        let url = build_endpoint_url(&base, "messages").unwrap();
        assert_eq!(url.as_str(), "https://api.anthropic.com/v1/messages");
    }

    // ── Plan Step 10 ───────────────────────────────────────────────────────

    /// Test 1 — `build_text_preview` truncates at the configured cap and
    /// appends the truncation marker so the event log shows the document
    /// was elided rather than misrepresenting it as complete.
    #[test]
    fn build_text_preview_respects_cap() {
        // Under cap: no truncation, no marker.
        assert_eq!(build_text_preview("abc", 10), "abc");

        // Over cap: keep `max_chars` chars, append marker with elided count.
        let out = build_text_preview("abcdefghijklmno", 10);
        assert!(
            out.starts_with("abcdefghij"),
            "first 10 chars must be preserved verbatim, got {out:?}"
        );
        assert!(
            out.contains("…[truncated 5 chars]"),
            "must indicate 5 chars were dropped, got {out:?}"
        );
    }

    /// Test 3 — `build_openai_body` always carries the
    /// `response_format: {"type": "json_object"}` constraint so the upstream
    /// gateway never returns prose around the JSON object.
    #[test]
    fn invoke_openai_body_contains_response_format() {
        let body = build_openai_body("gpt-test", "hello", 100, 0.0);
        assert_eq!(body["response_format"]["type"], "json_object");
        assert_eq!(body["model"], "gpt-test");
        assert_eq!(body["stream"], false);
        assert_eq!(body["max_tokens"], 100);
        assert_eq!(body["messages"][0]["role"], "user");
        assert_eq!(body["messages"][0]["content"], "hello");
    }

    /// Test 4 — `build_anthropic_body` ends `messages` with an assistant
    /// prefill turn whose content is exactly `"{"`, which is what
    /// `stitch_prefill` later relies on to know it must restore the leading
    /// brace if the model continued without echoing it.
    #[test]
    fn invoke_anthropic_body_contains_prefill() {
        let body = build_anthropic_body("claude-test", "hello", 200);
        let messages = body["messages"]
            .as_array()
            .expect("messages must be an array");
        assert_eq!(messages.len(), 2, "expected 2 messages, got {messages:?}");
        assert_eq!(messages[0]["role"], "user");
        assert_eq!(messages[0]["content"], "hello");
        assert_eq!(messages[1]["role"], "assistant");
        assert_eq!(
            messages[1]["content"], "{",
            "prefill content must be exactly the open brace, got {:?}",
            messages[1]["content"]
        );
        assert_eq!(body["model"], "claude-test");
        assert_eq!(body["max_tokens"], 200);
    }

    /// Test 5 — `stitch_prefill` is idempotent across the three shapes the
    /// Anthropic prefill flow produces (refined post-iter2: case (a) below
    /// would have been mis-classified as case (c) under the original
    /// `starts_with('"')` discriminator because Anthropic continuations
    /// after `{` typically open with a key literal `"…`, not a bare key).
    #[test]
    fn prefill_stitch_handles_all_shapes() {
        // Shape (a) — model continued the prefill `{` with `"key":"val"}`
        // (begins with `"`, ends with `}`). The original branch logic mistook
        // this for the string-encoded case and skipped stitching, leaving
        // downstream `parse_json` with `"key":"val"}` which has no leading
        // brace. The refined start+end discriminator restores the brace and
        // yields a parseable object.
        let continuation = "\"key\":\"val\"}".to_string();
        let stitched = stitch_prefill(continuation);
        assert_eq!(stitched, "{\"key\":\"val\"}");
        let value: serde_json::Value =
            serde_json::from_str(&stitched).expect("stitched continuation must parse");
        assert_eq!(value["key"], "val");

        // Shape (b) — content already starts with `{` (model echoed the
        // brace). Pass through unchanged so we do not double-stitch into
        // `{{...`.
        let already_object = "{\"key\":\"val\"}".to_string();
        assert_eq!(
            stitch_prefill(already_object.clone()),
            already_object,
            "already-object shape must round-trip unchanged"
        );

        // Shape (c) — string-encoded JSON literal (starts AND ends with `"`).
        // Pass through unchanged so the downstream `unwrap_stringified_json`
        // path in `parse_json` can unwrap it. Stitching `{` here would yield
        // invalid JSON.
        let stringified = "\"{\\\"k\\\":1}\"".to_string();
        assert_eq!(
            stitch_prefill(stringified.clone()),
            stringified,
            "string-encoded JSON must round-trip unchanged"
        );
    }
}
