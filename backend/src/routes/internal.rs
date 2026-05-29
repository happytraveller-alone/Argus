//! Internal HTTP contract surface consumed by the Node `agent-engine` sidecar.
//!
//! Every route under `/internal` is gated by a **fail-closed** shared-secret
//! bearer check (`Authorization: Bearer <AGENT_ENGINE_SHARED_SECRET>`). The
//! deployment runs the backend with `network_mode: host`, so these endpoints
//! are loopback-reachable by any host-local process — the bearer token is the
//! real access control, not network isolation (see `agent-engine/CONTRACT.md`).
//! Consequently, when no secret is configured the layer rejects **every**
//! request with `401`: an internal endpoint that hands back a resolved API key
//! must never be reachable without an explicitly configured secret (AC12).
//!
//! API keys returned by `/internal/llm-config` are deliberately in the response
//! body — that is the endpoint's entire purpose — but are NEVER logged.

use axum::{
    extract::{FromRequestParts, Query, State},
    http::{header::AUTHORIZATION, request::Parts, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    db::system_config,
    runtime::intelligent::config::{resolve_intelligent_llm_config, IntelligentLlmProvider},
    state::{AppState, StoredSystemConfig},
};

/// Build the bearer-gated `/internal` router.
///
/// Auth is enforced by the [`SidecarAuth`] extractor placed first in every
/// handler signature: it reads the configured secret from [`AppState`] and
/// fails closed. Routes added here MUST keep that extractor.
pub fn router() -> Router<AppState> {
    Router::new().route("/llm-config", get(get_llm_config))
}

/// Fail-closed bearer-auth extractor for `/internal/*`.
///
/// Resolution (AC12):
///   * `agent_engine_shared_secret` unset/empty → `401` for every request
///     (never expose a resolved key without an explicitly configured secret).
///   * missing header, malformed header (no `Bearer ` prefix), or wrong token
///     → `401`.
///
/// The token comparison is constant-time over equal-length inputs (a length
/// mismatch short-circuits, leaking only the length — acceptable, and avoids
/// adding a `subtle` dependency that is not in `Cargo.toml`). The token is
/// never logged.
struct SidecarAuth;

impl FromRequestParts<AppState> for SidecarAuth {
    type Rejection = Response;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let Some(secret) = state
            .config
            .agent_engine_shared_secret
            .as_deref()
            .filter(|secret| !secret.is_empty())
        else {
            return Err(unauthorized());
        };

        let presented = parts
            .headers
            .get(AUTHORIZATION)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.strip_prefix("Bearer "));

        match presented {
            Some(token) if constant_time_eq(token.as_bytes(), secret.as_bytes()) => Ok(Self),
            _ => Err(unauthorized()),
        }
    }
}

fn unauthorized() -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "error": "unauthorized" })),
    )
        .into_response()
}

/// Length-checked, constant-time byte-slice equality. Equal-length inputs are
/// compared in full (no early exit on first mismatch) to avoid leaking how many
/// leading bytes matched.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (lhs, rhs) in a.iter().zip(b.iter()) {
        diff |= lhs ^ rhs;
    }
    diff == 0
}

#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LlmConfigQuery {
    provider: Option<String>,
    model_id: Option<String>,
}

/// `GET /internal/llm-config` — resolve the provider config (incl. API key) the
/// sidecar needs to drive a stage.
///
/// Two modes, selected by the `provider` query param:
///   * **native provider** (`google`, `anthropic`, `openai`, `deepseek`,
///     `qwen`, `zhipu`, `moonshot`, `baidu`, `minimax`, `doubao`, `ollama`):
///     the API key is read from the matching `AppConfig` per-provider env field.
///     `baseUrl` is `null` (the sidecar uses pi defaults) except `ollama`, which
///     gets `ollama_base_url`. An unset/empty key → `404 provider_key_not_configured`.
///   * **compatible** (`provider` absent, or one of `openai_compatible`,
///     `anthropic_compatible`, `compatible`): the single enabled compatible LLM
///     row is resolved via [`resolve_intelligent_llm_config`].
async fn get_llm_config(
    _auth: SidecarAuth,
    State(state): State<AppState>,
    Query(query): Query<LlmConfigQuery>,
) -> Response {
    let provider = query.provider.as_deref().map(str::trim).unwrap_or_default();

    if provider.is_empty() || is_compatible_provider(provider) {
        return resolve_compatible(&state).await;
    }

    if let Some(native) = NativeProvider::from_id(provider) {
        return resolve_native(&state, native, query.model_id.as_deref());
    }

    // An unrecognized provider is neither native nor compatible.
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "error": "unsupported_provider",
            "message": format!("未知的 provider: {provider}"),
        })),
    )
        .into_response()
}

fn is_compatible_provider(provider: &str) -> bool {
    matches!(
        provider.to_ascii_lowercase().as_str(),
        "openai_compatible" | "anthropic_compatible" | "compatible"
    )
}

async fn resolve_compatible(state: &AppState) -> Response {
    let stored = match system_config::load_current(state).await {
        Ok(stored) => stored.unwrap_or_else(empty_stored_config),
        Err(error) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({
                    "error": "system_config_load_failed",
                    "message": error.to_string(),
                })),
            )
                .into_response()
        }
    };

    match resolve_intelligent_llm_config(&stored, &state.config) {
        Ok(config) => Json(json!({
            "provider": serialize_provider(&config.provider),
            "modelId": config.model,
            "baseUrl": config.base_url.as_str(),
            "apiKey": config.api_key,
            "headers": {},
        }))
        .into_response(),
        Err(error) => {
            // `invalid_base_url` is a client-side config error (422); every other
            // reason means no usable compatible row is configured (404).
            let status = if error.reason_code == "invalid_base_url" {
                StatusCode::UNPROCESSABLE_ENTITY
            } else {
                StatusCode::NOT_FOUND
            };
            (
                status,
                Json(json!({
                    "error": error.reason_code,
                    "message": error.message,
                })),
            )
                .into_response()
        }
    }
}

fn resolve_native(state: &AppState, native: NativeProvider, model_id: Option<&str>) -> Response {
    let config = state.config.as_ref();
    let model_id = model_id
        .map(str::trim)
        .filter(|model| !model.is_empty())
        .map(str::to_string);

    // `ollama` is keyless and carries a base URL; every other native provider
    // requires a non-empty key and uses pi's default base URL (null here).
    if matches!(native, NativeProvider::Ollama) {
        return Json(json!({
            "provider": native.as_id(),
            "modelId": model_id,
            "baseUrl": config.ollama_base_url,
            "apiKey": Value::Null,
            "headers": {},
        }))
        .into_response();
    }

    let api_key = native.api_key(config).trim();
    if api_key.is_empty() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({
                "error": "provider_key_not_configured",
                "message": format!("provider {} 未配置 API key。", native.as_id()),
            })),
        )
            .into_response();
    }

    Json(json!({
        "provider": native.as_id(),
        "modelId": model_id,
        "baseUrl": Value::Null,
        "apiKey": api_key,
        "headers": {},
    }))
    .into_response()
}

/// pi-native providers whose API key the Rust backend holds in per-provider
/// `AppConfig` env fields.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NativeProvider {
    Google,
    Anthropic,
    Openai,
    Deepseek,
    Qwen,
    Zhipu,
    Moonshot,
    Baidu,
    Minimax,
    Doubao,
    Ollama,
}

impl NativeProvider {
    fn from_id(provider: &str) -> Option<Self> {
        match provider.to_ascii_lowercase().as_str() {
            "google" => Some(Self::Google),
            "anthropic" => Some(Self::Anthropic),
            "openai" => Some(Self::Openai),
            "deepseek" => Some(Self::Deepseek),
            "qwen" => Some(Self::Qwen),
            "zhipu" => Some(Self::Zhipu),
            "moonshot" => Some(Self::Moonshot),
            "baidu" => Some(Self::Baidu),
            "minimax" => Some(Self::Minimax),
            "doubao" => Some(Self::Doubao),
            "ollama" => Some(Self::Ollama),
            _ => None,
        }
    }

    fn as_id(self) -> &'static str {
        match self {
            Self::Google => "google",
            Self::Anthropic => "anthropic",
            Self::Openai => "openai",
            Self::Deepseek => "deepseek",
            Self::Qwen => "qwen",
            Self::Zhipu => "zhipu",
            Self::Moonshot => "moonshot",
            Self::Baidu => "baidu",
            Self::Minimax => "minimax",
            Self::Doubao => "doubao",
            Self::Ollama => "ollama",
        }
    }

    /// API key for this provider from the per-provider `AppConfig` env field.
    /// `Ollama` is keyless and handled by the caller before this is reached.
    fn api_key(self, config: &crate::config::AppConfig) -> &str {
        match self {
            Self::Google => &config.gemini_api_key,
            Self::Anthropic => &config.claude_api_key,
            Self::Openai => &config.openai_api_key,
            Self::Deepseek => &config.deepseek_api_key,
            Self::Qwen => &config.qwen_api_key,
            Self::Zhipu => &config.zhipu_api_key,
            Self::Moonshot => &config.moonshot_api_key,
            Self::Baidu => &config.baidu_api_key,
            Self::Minimax => &config.minimax_api_key,
            Self::Doubao => &config.doubao_api_key,
            Self::Ollama => "",
        }
    }
}

/// Serialize an [`IntelligentLlmProvider`] to its wire string
/// (`openai_compatible` / `anthropic_compatible`).
fn serialize_provider(provider: &IntelligentLlmProvider) -> String {
    serde_json::to_value(provider)
        .ok()
        .and_then(|value| value.as_str().map(str::to_string))
        .unwrap_or_default()
}

fn empty_stored_config() -> StoredSystemConfig {
    StoredSystemConfig {
        llm_config_json: json!({}),
        other_config_json: json!({}),
        llm_test_metadata_json: json!({}),
    }
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        Router,
    };
    use http_body_util::BodyExt;
    use serde_json::Value;
    use tower::ServiceExt;

    use super::router;
    use crate::{config::AppConfig, state::AppState};

    async fn app_with_config(config: AppConfig) -> Router {
        let state = AppState::from_config(config)
            .await
            .expect("build AppState for tests");
        Router::new()
            .nest("/internal", router())
            .with_state(state)
    }

    fn get(uri: &str) -> Request<Body> {
        Request::builder()
            .uri(uri)
            .body(Body::empty())
            .expect("build request")
    }

    fn get_with_auth(uri: &str, token: &str) -> Request<Body> {
        Request::builder()
            .uri(uri)
            .header("Authorization", format!("Bearer {token}"))
            .body(Body::empty())
            .expect("build request")
    }

    async fn body_json(response: axum::response::Response) -> Value {
        let bytes = response
            .into_body()
            .collect()
            .await
            .expect("collect body")
            .to_bytes();
        serde_json::from_slice(&bytes).expect("body is json")
    }

    #[tokio::test]
    async fn llm_config_without_authorization_header_is_unauthorized() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("super-secret".to_string());
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get("/internal/llm-config?provider=google"))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn llm_config_with_wrong_bearer_is_unauthorized() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("super-secret".to_string());
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth("/internal/llm-config?provider=google", "wrong"))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn llm_config_is_unauthorized_when_secret_unconfigured_even_with_bearer() {
        // Secret None → fail closed: even a "correct-looking" bearer is rejected.
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = None;
        config.gemini_api_key = "sk-gem".to_string();
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth(
                "/internal/llm-config?provider=google",
                "anything",
            ))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn llm_config_with_correct_bearer_returns_native_provider_key() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("super-secret".to_string());
        config.gemini_api_key = "sk-gem".to_string();
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth(
                "/internal/llm-config?provider=google&modelId=gemini-2.5-pro",
                "super-secret",
            ))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::OK);
        let body = body_json(response).await;
        assert_eq!(body["provider"], "google");
        assert_eq!(body["modelId"], "gemini-2.5-pro");
        assert_eq!(body["baseUrl"], Value::Null);
        // The key value is present in the body — proves resolution worked.
        assert_eq!(body["apiKey"], "sk-gem");
    }

    #[tokio::test]
    async fn native_provider_with_empty_key_is_not_found() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("super-secret".to_string());
        config.gemini_api_key = String::new();
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth(
                "/internal/llm-config?provider=google",
                "super-secret",
            ))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = body_json(response).await;
        assert_eq!(body["error"], "provider_key_not_configured");
    }

    #[tokio::test]
    async fn native_provider_envkey_map_resolves_per_provider() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("s".to_string());
        config.deepseek_api_key = "sk-deepseek".to_string();
        config.moonshot_api_key = "sk-moon".to_string();
        let app = app_with_config(config).await;

        let deepseek = app
            .clone()
            .oneshot(get_with_auth("/internal/llm-config?provider=deepseek", "s"))
            .await
            .expect("response");
        assert_eq!(deepseek.status(), StatusCode::OK);
        assert_eq!(body_json(deepseek).await["apiKey"], "sk-deepseek");

        let moonshot = app
            .oneshot(get_with_auth("/internal/llm-config?provider=moonshot", "s"))
            .await
            .expect("response");
        assert_eq!(moonshot.status(), StatusCode::OK);
        assert_eq!(body_json(moonshot).await["apiKey"], "sk-moon");
    }

    #[tokio::test]
    async fn ollama_returns_base_url_and_no_key() {
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("s".to_string());
        config.ollama_base_url = "http://ollama.internal/v1".to_string();
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth("/internal/llm-config?provider=ollama", "s"))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::OK);
        let body = body_json(response).await;
        assert_eq!(body["provider"], "ollama");
        assert_eq!(body["baseUrl"], "http://ollama.internal/v1");
        assert_eq!(body["apiKey"], Value::Null);
    }

    #[tokio::test]
    async fn compatible_mode_without_config_is_not_found() {
        // No system config saved (file-backed, db_pool None) → no enabled row.
        let mut config = AppConfig::for_tests();
        config.agent_engine_shared_secret = Some("s".to_string());
        let app = app_with_config(config).await;

        let response = app
            .oneshot(get_with_auth("/internal/llm-config", "s"))
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
