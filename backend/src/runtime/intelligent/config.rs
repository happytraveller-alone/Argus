use reqwest::Url;
use serde::{Serialize, Serializer};
use serde_json::Value;

use crate::{
    config::AppConfig,
    llm::{normalize_base_url, RuntimeLlmConfig},
    routes::llm_config_set,
    runtime::intelligent::audit_pipeline::context::AuditStage,
    state::StoredSystemConfig,
};

const INTELLIGENT_DEFAULT_MODEL: &str = "gpt-5";

/// Execution engine for a single audit-pipeline stage.
///
/// Phase 0.5 seam (per `.omc/plans/ralplan-enhance-llm-agent-framework-pi.md`
/// §0.5): a per-stage flag lets a future Node sidecar own a stage's reasoning
/// while the Rust backend keeps lifecycle/durability/keys. Default is always
/// [`StageEngine::Rust`] — with no `intelligentEngine` config present every
/// stage runs the existing in-process code path unchanged (AC2).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StageEngine {
    /// Run the stage in-process in Rust (the only path wired today).
    Rust,
    /// Route the stage to the out-of-process Node sidecar. Not yet implemented;
    /// selected only when the operator explicitly opts a stage in.
    Sidecar,
}

/// Resolve the execution engine for `stage` from the stored system config.
///
/// The map lives at `other_config_json["intelligentEngine"]` — an optional
/// object of `{ "<stage>": "rust" | "sidecar" }`. Resolution is intentionally
/// lenient and backward-compatible:
///   * absent map, absent key, non-object value, or any unrecognized engine
///     string → [`StageEngine::Rust`] (existing records without the field
///     deserialize and resolve to Rust unchanged).
///   * only an explicit, case-insensitive `"sidecar"` selects
///     [`StageEngine::Sidecar`].
#[must_use]
pub fn stage_engine(stage: AuditStage, stored: &StoredSystemConfig) -> StageEngine {
    stored
        .other_config_json
        .get("intelligentEngine")
        .and_then(Value::as_object)
        .and_then(|map| map.get(stage.as_str()))
        .and_then(Value::as_str)
        .map(parse_stage_engine)
        .unwrap_or(StageEngine::Rust)
}

fn parse_stage_engine(value: &str) -> StageEngine {
    match value.trim().to_ascii_lowercase().as_str() {
        "sidecar" => StageEngine::Sidecar,
        // "rust" and every unknown/empty value fall back to the safe default.
        _ => StageEngine::Rust,
    }
}

/// Operator-chosen model assignment for a single audit-pipeline stage.
///
/// Phase 1B.2 persistence half (AC5): when a stage runs on the Node sidecar the
/// operator may pin which provider/model that stage reasons with, independent of
/// the single enabled compatible LLM row. The map lives at
/// `other_config_json["intelligentStageModels"]` as
/// `{ "<stage>": { "provider": "...", "modelId": "..." } }`.
///
/// `None` from [`stage_model`] means "no per-stage override" — the caller falls
/// back to the default enabled config, preserving current behavior when no
/// `intelligentStageModels` map is present.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StageModelAssignment {
    /// Provider id chosen for this stage (e.g. `google`, `openai_compatible`).
    /// Verbatim from config — interpretation (native vs compatible) is the
    /// caller's / sidecar's job.
    pub provider: String,
    /// Optional model id; `None` when the config omits or blanks `modelId`.
    pub model_id: Option<String>,
}

/// Resolve the per-stage model assignment for `stage` from the stored config.
///
/// Resolution mirrors [`stage_engine`] and is intentionally lenient and
/// backward-compatible:
///   * absent `intelligentStageModels` map, absent stage key, or a non-object
///     value at either level → `None`.
///   * a present stage entry with a non-empty `provider` string →
///     `Some(StageModelAssignment { .. })`. An empty / missing / non-string
///     `provider` yields `None` (an assignment without a provider is
///     meaningless). A missing / blank / non-string `modelId` resolves to
///     `model_id: None`.
#[must_use]
pub fn stage_model(stage: AuditStage, stored: &StoredSystemConfig) -> Option<StageModelAssignment> {
    let entry = stored
        .other_config_json
        .get("intelligentStageModels")
        .and_then(Value::as_object)
        .and_then(|map| map.get(stage.as_str()))
        .and_then(Value::as_object)?;
    let provider = entry
        .get("provider")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|provider| !provider.is_empty())?
        .to_string();
    let model_id = entry
        .get("modelId")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|model| !model.is_empty())
        .map(str::to_string);
    Some(StageModelAssignment { provider, model_id })
}

/// Pre-resolved per-stage engine selection, captured once at pipeline entry so
/// the orchestrator does not re-read system config per stage.
///
/// [`StageEngineSelection::all_rust`] is the default used by callers that have
/// no system config (tests, the thin `run_pipeline` wrapper); with it every
/// [`engine`](Self::engine) lookup returns [`StageEngine::Rust`] (AC2).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct StageEngineSelection {
    recon: StageEngine,
    hunt: StageEngine,
    validate: StageEngine,
    gapfill: StageEngine,
    dedupe: StageEngine,
    trace: StageEngine,
    feedback: StageEngine,
    report: StageEngine,
}

impl StageEngineSelection {
    /// All stages on the in-process Rust engine — the identical-to-baseline default.
    #[must_use]
    pub const fn all_rust() -> Self {
        Self {
            recon: StageEngine::Rust,
            hunt: StageEngine::Rust,
            validate: StageEngine::Rust,
            gapfill: StageEngine::Rust,
            dedupe: StageEngine::Rust,
            trace: StageEngine::Rust,
            feedback: StageEngine::Rust,
            report: StageEngine::Rust,
        }
    }

    /// Resolve every stage's engine from the stored system config. Absent /
    /// unknown config resolves each stage to [`StageEngine::Rust`].
    #[must_use]
    pub fn from_stored(stored: &StoredSystemConfig) -> Self {
        Self {
            recon: stage_engine(AuditStage::Recon, stored),
            hunt: stage_engine(AuditStage::Hunt, stored),
            validate: stage_engine(AuditStage::Validate, stored),
            gapfill: stage_engine(AuditStage::Gapfill, stored),
            dedupe: stage_engine(AuditStage::Dedupe, stored),
            trace: stage_engine(AuditStage::Trace, stored),
            feedback: stage_engine(AuditStage::Feedback, stored),
            report: stage_engine(AuditStage::Report, stored),
        }
    }

    /// Engine resolved for `stage`.
    #[must_use]
    pub fn engine(&self, stage: AuditStage) -> StageEngine {
        match stage {
            AuditStage::Recon => self.recon,
            AuditStage::Hunt => self.hunt,
            AuditStage::Validate => self.validate,
            AuditStage::Gapfill => self.gapfill,
            AuditStage::Dedupe => self.dedupe,
            AuditStage::Trace => self.trace,
            AuditStage::Feedback => self.feedback,
            AuditStage::Report => self.report,
        }
    }
}

impl Default for StageEngineSelection {
    fn default() -> Self {
        Self::all_rust()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub enum IntelligentLlmProvider {
    #[serde(rename = "anthropic_compatible")]
    AnthropicCompatible,
    #[serde(rename = "openai_compatible")]
    OpenAiCompatible,
}

impl IntelligentLlmProvider {
    #[must_use]
    pub fn auth_kind(&self) -> &'static str {
        match self {
            Self::AnthropicCompatible => "anthropic_api_key",
            Self::OpenAiCompatible => "openai_compatible_bearer",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentLlmConfig {
    pub row_id: String,
    pub provider: IntelligentLlmProvider,
    pub model: String,
    #[serde(serialize_with = "serialize_url")]
    pub base_url: Url,
    #[serde(skip_serializing)]
    pub api_key: String,
    pub fingerprint: String,
    pub timeout_ms: i64,
    pub temperature: f64,
    pub max_tokens_per_call: i64,
    pub first_token_timeout_seconds: i64,
    pub stream_timeout_seconds: i64,
    pub custom_header_names: Vec<String>,
    pub auth_kind: &'static str,
    /// Per-call preview cap for prompt/response text embedded in
    /// `llm_attempt` events. Threaded from `AppConfig.intelligent_llm_preview_chars`.
    pub preview_chars: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IntelligentLlmConfigError {
    pub reason_code: &'static str,
    pub message: String,
}

impl IntelligentLlmConfigError {
    fn new(reason_code: &'static str, message: impl Into<String>) -> Self {
        Self {
            reason_code,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for IntelligentLlmConfigError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for IntelligentLlmConfigError {}

pub fn resolve_intelligent_llm_config(
    stored: &StoredSystemConfig,
    app_config: &AppConfig,
) -> Result<IntelligentLlmConfig, IntelligentLlmConfigError> {
    let selected = llm_config_set::selected_enabled_runtime(
        &stored.llm_config_json,
        &stored.other_config_json,
        app_config,
    )
    .map_err(|error| IntelligentLlmConfigError::new(error.reason_code, error.message))?;
    let provider = provider_from_runtime(&selected.runtime.provider)?;
    config_from_runtime(
        selected.row_id,
        selected.runtime,
        selected.fingerprint,
        provider,
        app_config.intelligent_llm_preview_chars,
    )
}

#[must_use]
pub fn is_llm_configured(stored: &StoredSystemConfig, app_config: &AppConfig) -> bool {
    resolve_intelligent_llm_config(stored, app_config).is_ok()
}

pub fn llm_api_key(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<String> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.api_key)
}

pub fn llm_base_url(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<Url> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.base_url)
}

pub fn llm_model_default(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<String> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.model)
}

pub fn config_from_runtime(
    row_id: String,
    runtime: RuntimeLlmConfig,
    fingerprint: String,
    provider: IntelligentLlmProvider,
    preview_chars: usize,
) -> Result<IntelligentLlmConfig, IntelligentLlmConfigError> {
    let base_url = parse_absolute_base_url(&runtime.base_url, &provider)?;
    let model = if runtime.model.trim().is_empty() {
        INTELLIGENT_DEFAULT_MODEL.to_string()
    } else {
        runtime.model
    };
    let mut custom_header_names: Vec<String> = runtime.custom_headers.keys().cloned().collect();
    custom_header_names.sort();
    let auth_kind = provider.auth_kind();
    Ok(IntelligentLlmConfig {
        row_id,
        provider,
        model,
        base_url,
        api_key: runtime.api_key,
        fingerprint,
        timeout_ms: runtime.llm_timeout,
        temperature: runtime.llm_temperature,
        max_tokens_per_call: runtime.llm_max_tokens,
        first_token_timeout_seconds: runtime.llm_first_token_timeout,
        stream_timeout_seconds: runtime.llm_stream_timeout,
        custom_header_names,
        auth_kind,
        preview_chars,
    })
}

fn provider_from_runtime(
    provider: &str,
) -> Result<IntelligentLlmProvider, IntelligentLlmConfigError> {
    match provider.trim().to_ascii_lowercase().as_str() {
        "anthropic_compatible" => Ok(IntelligentLlmProvider::AnthropicCompatible),
        "openai_compatible" => Ok(IntelligentLlmProvider::OpenAiCompatible),
        _ => Err(IntelligentLlmConfigError::new(
            "unsupported_provider",
            "智能审计 LLM 配置仅支持 OpenAI-compatible 或 Anthropic-compatible 协议。",
        )),
    }
}

fn parse_absolute_base_url(
    value: &str,
    provider: &IntelligentLlmProvider,
) -> Result<Url, IntelligentLlmConfigError> {
    let mut normalized = normalize_base_url(value);
    normalized = match provider {
        IntelligentLlmProvider::AnthropicCompatible => {
            let trimmed = normalized.trim_end_matches('/');
            trimmed
                .strip_suffix("/v1/messages")
                .unwrap_or(trimmed)
                .to_string()
        }
        IntelligentLlmProvider::OpenAiCompatible => normalized,
    };
    let parsed = Url::parse(&normalized).map_err(|_| {
        IntelligentLlmConfigError::new(
            "invalid_base_url",
            "智能审计 LLM 配置的 baseUrl 必须是包含 http/https scheme 的绝对 URL。",
        )
    })?;
    match parsed.scheme() {
        "http" | "https" if parsed.has_host() => Ok(parsed),
        _ => Err(IntelligentLlmConfigError::new(
            "invalid_base_url",
            "智能审计 LLM 配置的 baseUrl 必须是包含 http/https scheme 的绝对 URL。",
        )),
    }
}

fn serialize_url<S>(url: &Url, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(url.as_str())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::{
        config::AppConfig, llm::compute_llm_fingerprint, routes::llm_config_set,
        state::StoredSystemConfig,
    };

    #[test]
    fn resolves_enabled_schema_v2_row_into_provider_neutral_snapshot() {
        let app_config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [
                    {
                        "id": "disabled",
                        "priority": 1,
                        "enabled": false,
                        "provider": "openai_compatible",
                        "baseUrl": "https://disabled.example/v1",
                        "model": "gpt-disabled",
                        "apiKey": "sk-disabled",
                        "advanced": {}
                    },
                    {
                        "id": "anthropic-row",
                        "priority": 2,
                        "enabled": true,
                        "provider": "anthropic_compatible",
                        "baseUrl": "https://api.anthropic.example/v1/messages",
                        "model": "claude-sonnet-4.5",
                        "apiKey": "sk-ant-secret",
                        "advanced": {
                            "llmTimeout": 123000,
                            "llmTemperature": 0.2,
                            "llmMaxTokens": 4096,
                            "llmFirstTokenTimeout": 31,
                            "llmStreamTimeout": 122,
                            "llmCustomHeaders": {"X-Trace": "secret-header"}
                        }
                    }
                ]
            }),
            other_config_json: json!({"llmConcurrency": 2, "llmGapMs": 5}),
            llm_test_metadata_json: json!({}),
        };

        let config = resolve_intelligent_llm_config(&stored, &app_config).unwrap();

        assert_eq!(config.row_id, "anthropic-row");
        assert_eq!(config.provider, IntelligentLlmProvider::AnthropicCompatible);
        assert_eq!(config.auth_kind, "anthropic_api_key");
        assert_eq!(config.model, "claude-sonnet-4.5");
        assert_eq!(config.base_url.as_str(), "https://api.anthropic.example/");
        assert_eq!(config.api_key, "sk-ant-secret");
        assert_eq!(config.timeout_ms, 123000);
        assert_eq!(config.temperature, 0.2);
        assert_eq!(config.max_tokens_per_call, 4096);
        assert_eq!(config.first_token_timeout_seconds, 31);
        assert_eq!(config.stream_timeout_seconds, 122);
        assert_eq!(config.custom_header_names, vec!["x-trace"]);
        assert!(config.fingerprint.starts_with("sha256:"));
    }

    #[test]
    fn rejects_missing_malformed_or_relative_configs_without_panicking() {
        let app_config = AppConfig::for_tests();
        let empty = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        assert!(!is_llm_configured(&empty, &app_config));
        assert!(llm_api_key(&empty, &app_config).is_none());
        assert!(llm_base_url(&empty, &app_config).is_none());
        assert!(llm_model_default(&empty, &app_config).is_none());

        let relative_url = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [{
                    "id": "bad-url",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "/local/v1",
                    "model": "gpt-5",
                    "apiKey": "sk-test",
                    "advanced": {}
                }]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        let error = resolve_intelligent_llm_config(&relative_url, &app_config).unwrap_err();
        assert_eq!(error.reason_code, "invalid_base_url");
    }

    #[test]
    fn exposes_openai_compatible_runtime_for_native_pipeline() {
        let app_config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [{
                    "id": "openai-row",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "https://gateway.example/v1/chat/completions",
                    "model": "gpt-5",
                    "apiKey": "sk-openai-secret",
                    "advanced": {}
                }]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };

        let config = resolve_intelligent_llm_config(&stored, &app_config).unwrap();

        assert_eq!(config.provider, IntelligentLlmProvider::OpenAiCompatible);
        assert_eq!(config.auth_kind, "openai_compatible_bearer");
        assert_eq!(config.base_url.as_str(), "https://gateway.example/v1");
        assert_eq!(
            llm_api_key(&stored, &app_config).as_deref(),
            Some("sk-openai-secret")
        );
        assert_eq!(
            llm_base_url(&stored, &app_config).map(|url| url.to_string()),
            Some("https://gateway.example/v1".to_string())
        );
        assert_eq!(
            llm_model_default(&stored, &app_config).as_deref(),
            Some("gpt-5")
        );
    }

    #[test]
    fn stage_engine_defaults_to_rust_when_config_absent_or_unknown() {
        use crate::runtime::intelligent::audit_pipeline::context::AuditStage;

        // No `intelligentEngine` key at all → every stage resolves to Rust (AC2).
        let bare = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        for stage in [
            AuditStage::Recon,
            AuditStage::Hunt,
            AuditStage::Validate,
            AuditStage::Gapfill,
            AuditStage::Dedupe,
            AuditStage::Trace,
            AuditStage::Feedback,
            AuditStage::Report,
        ] {
            assert_eq!(stage_engine(stage, &bare), StageEngine::Rust);
        }

        // Unknown engine string, non-object value, and absent stage key all
        // fall back to Rust; only an explicit "sidecar" opts a stage in.
        let mixed = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({
                "intelligentEngine": {
                    "hunt": "sidecar",
                    "recon": "RUST",
                    "validate": "experimental",
                    "trace": "",
                }
            }),
            llm_test_metadata_json: json!({}),
        };
        assert_eq!(stage_engine(AuditStage::Hunt, &mixed), StageEngine::Sidecar);
        assert_eq!(stage_engine(AuditStage::Recon, &mixed), StageEngine::Rust);
        assert_eq!(stage_engine(AuditStage::Validate, &mixed), StageEngine::Rust);
        assert_eq!(stage_engine(AuditStage::Trace, &mixed), StageEngine::Rust);
        // Absent key → Rust.
        assert_eq!(stage_engine(AuditStage::Report, &mixed), StageEngine::Rust);

        // Non-object `intelligentEngine` value is ignored → Rust.
        let malformed = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({ "intelligentEngine": "sidecar" }),
            llm_test_metadata_json: json!({}),
        };
        assert_eq!(stage_engine(AuditStage::Hunt, &malformed), StageEngine::Rust);
    }

    #[test]
    fn stage_model_defaults_to_none_when_config_absent_or_malformed() {
        use crate::runtime::intelligent::audit_pipeline::context::AuditStage;

        const ALL_STAGES: [AuditStage; 8] = [
            AuditStage::Recon,
            AuditStage::Hunt,
            AuditStage::Validate,
            AuditStage::Gapfill,
            AuditStage::Dedupe,
            AuditStage::Trace,
            AuditStage::Feedback,
            AuditStage::Report,
        ];

        // No `intelligentStageModels` key → every stage resolves to None
        // (use the default enabled config — current behavior preserved).
        let bare = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        for stage in ALL_STAGES {
            assert_eq!(stage_model(stage, &bare), None);
        }

        // Non-object `intelligentStageModels` value is ignored → None.
        let non_object = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({ "intelligentStageModels": "google" }),
            llm_test_metadata_json: json!({}),
        };
        for stage in ALL_STAGES {
            assert_eq!(stage_model(stage, &non_object), None);
        }

        // Populated map resolves the right stages; absent / malformed /
        // provider-less entries resolve to None.
        let populated = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({
                "intelligentStageModels": {
                    "hunt": { "provider": "google", "modelId": "gemini-2.5-pro" },
                    // modelId absent → model_id None.
                    "recon": { "provider": "anthropic" },
                    // blank modelId → model_id None.
                    "validate": { "provider": "openai_compatible", "modelId": "   " },
                    // empty provider → whole entry None (meaningless override).
                    "gapfill": { "provider": "", "modelId": "x" },
                    // non-object entry → None.
                    "dedupe": "google",
                }
            }),
            llm_test_metadata_json: json!({}),
        };
        assert_eq!(
            stage_model(AuditStage::Hunt, &populated),
            Some(StageModelAssignment {
                provider: "google".to_string(),
                model_id: Some("gemini-2.5-pro".to_string()),
            })
        );
        assert_eq!(
            stage_model(AuditStage::Recon, &populated),
            Some(StageModelAssignment {
                provider: "anthropic".to_string(),
                model_id: None,
            })
        );
        assert_eq!(
            stage_model(AuditStage::Validate, &populated),
            Some(StageModelAssignment {
                provider: "openai_compatible".to_string(),
                model_id: None,
            })
        );
        assert_eq!(stage_model(AuditStage::Gapfill, &populated), None);
        assert_eq!(stage_model(AuditStage::Dedupe, &populated), None);
        // Absent stage key → None.
        assert_eq!(stage_model(AuditStage::Report, &populated), None);
    }

    #[test]
    fn serialized_config_never_exposes_secret_material() {
        let app_config = AppConfig::for_tests();
        let row = json!({
            "id": "row-secret",
            "priority": 1,
            "enabled": true,
            "provider": "openai_compatible",
            "baseUrl": "https://gateway.example/v1",
            "model": "gpt-5",
            "apiKey": "sk-secret",
            "advanced": {"llmCustomHeaders": {"X-Secret": "header-secret"}}
        });
        let runtime = llm_config_set::selected_enabled_runtime(
            &json!({"schemaVersion": 2, "rows": [row]}),
            &json!({}),
            &app_config,
        )
        .unwrap();
        let fingerprint = compute_llm_fingerprint(&runtime.runtime);
        let config = config_from_runtime(
            runtime.row_id,
            runtime.runtime,
            fingerprint,
            IntelligentLlmProvider::OpenAiCompatible,
            16_384,
        )
        .unwrap();

        let serialized = serde_json::to_string(&config).unwrap();

        assert!(!serialized.contains("sk-secret"));
        assert!(!serialized.contains("header-secret"));
        assert!(serialized.contains("customHeaderNames"));
        assert!(serialized.contains("x-secret"));
    }
}
