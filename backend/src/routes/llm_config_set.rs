use serde_json::{json, Map, Value};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::{
    config::AppConfig,
    llm::{
        build_runtime_config, compute_llm_fingerprint, empty_protocol_llm_config,
        is_supported_protocol_provider, normalize_base_url, LlmGateError, RuntimeLlmConfig,
    },
};

pub const LLM_CONFIG_SET_SCHEMA_VERSION: i64 = 2;
pub const REDACTED_SECRET_PLACEHOLDER: &str = "***configured***";

pub const ROW_ADVANCED_FIELDS: &[&str] = &[
    "llmCustomHeaders",
    "llmTimeout",
    "llmTemperature",
    "llmMaxTokens",
    "llmFirstTokenTimeout",
    "llmStreamTimeout",
    "agentTimeout",
    "subAgentTimeout",
    "toolTimeout",
];

#[derive(Clone, Debug)]
pub struct SelectedLlmRow {
    pub row_id: String,
    pub row: Value,
    pub runtime_config: Value,
    pub runtime: RuntimeLlmConfig,
    pub fingerprint: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FallbackCategory {
    Connectivity,
    Auth,
    ModelUnavailable,
    QuotaRateLimit,
    InvalidConfig,
    InvalidResponse,
    Unknown,
}

impl FallbackCategory {
    pub fn reason_code(&self) -> &'static str {
        match self {
            Self::Connectivity => "connectivity",
            Self::Auth => "auth",
            Self::ModelUnavailable => "model_unavailable",
            Self::QuotaRateLimit => "quota_rate_limit",
            Self::InvalidConfig => "invalid_config",
            Self::InvalidResponse => "invalid_response",
            Self::Unknown => "unknown_error",
        }
    }

    pub fn is_fallback_eligible(&self) -> bool {
        matches!(
            self,
            Self::Connectivity | Self::Auth | Self::ModelUnavailable
        )
    }
}

pub fn default_envelope(config: &AppConfig) -> Value {
    json!({
        "schemaVersion": LLM_CONFIG_SET_SCHEMA_VERSION,
        "rows": [default_row(config, 1)],
        "latestPreflightRun": empty_latest_preflight_run(),
        "migration": {
            "status": "not_needed",
            "message": Value::Null,
            "sourceSchemaVersion": Value::Null,
        }
    })
}

pub fn default_row(config: &AppConfig, priority: i64) -> Value {
    let legacy = legacy_defaults(config);
    row_from_legacy(&legacy, priority, Some(stable_row_id()), "not_needed")
}

pub fn legacy_defaults(config: &AppConfig) -> Value {
    let mut value = empty_protocol_llm_config();
    if let Some(map) = value.as_object_mut() {
        map.insert(
            "llmProvider".to_string(),
            Value::String(if is_supported_protocol_provider(&config.llm_provider) {
                config.llm_provider.clone()
            } else {
                "openai_compatible".to_string()
            }),
        );
        map.insert(
            "llmModel".to_string(),
            Value::String(config.llm_model.clone()),
        );
        map.insert(
            "llmBaseUrl".to_string(),
            Value::String(config.llm_base_url.clone()),
        );
        map.insert("llmApiKey".to_string(), Value::String(String::new()));
        map.insert(
            "llmTimeout".to_string(),
            Value::Number((config.llm_timeout_seconds * 1000).into()),
        );
        map.insert(
            "llmTemperature".to_string(),
            serde_json::Number::from_f64(config.llm_temperature)
                .map(Value::Number)
                .unwrap_or(Value::Null),
        );
        map.insert(
            "llmMaxTokens".to_string(),
            Value::Number(config.llm_max_tokens.into()),
        );
        map.insert(
            "llmFirstTokenTimeout".to_string(),
            Value::Number(config.llm_first_token_timeout_seconds.into()),
        );
        map.insert(
            "llmStreamTimeout".to_string(),
            Value::Number(config.llm_stream_timeout_seconds.into()),
        );
        map.insert(
            "agentTimeout".to_string(),
            Value::Number(config.agent_timeout_seconds.into()),
        );
        map.insert(
            "subAgentTimeout".to_string(),
            Value::Number(config.sub_agent_timeout_seconds.into()),
        );
        map.insert(
            "toolTimeout".to_string(),
            Value::Number(config.tool_timeout_seconds.into()),
        );
        map.insert("llmCustomHeaders".to_string(), Value::String(String::new()));
        map.insert(
            "ollamaBaseUrl".to_string(),
            Value::String(config.ollama_base_url.clone()),
        );
    }
    value
}

pub fn normalize_envelope(value: &Value, config: &AppConfig) -> (Value, bool) {
    if value.get("schemaVersion").and_then(Value::as_i64) == Some(LLM_CONFIG_SET_SCHEMA_VERSION)
        && value.get("rows").and_then(Value::as_array).is_some()
    {
        return (normalize_new_envelope(value, config), false);
    }
    migrate_legacy(value, config)
}

pub fn normalize_for_save(
    input: &Value,
    existing: Option<&Value>,
    config: &AppConfig,
) -> Result<Value, LlmGateError> {
    let existing_normalized = existing.map(|value| normalize_envelope(value, config).0);
    let mut envelope = if input.get("schemaVersion").and_then(Value::as_i64)
        == Some(LLM_CONFIG_SET_SCHEMA_VERSION)
    {
        normalize_new_envelope(input, config)
    } else {
        migrate_legacy(input, config).0
    };
    preserve_row_secrets(&mut envelope, existing_normalized.as_ref())?;
    Ok(normalize_new_envelope(&envelope, config))
}

pub fn public_envelope(value: &Value, config: &AppConfig) -> Value {
    let (mut envelope, _) = normalize_envelope(value, config);
    if let Some(rows) = envelope.get_mut("rows").and_then(Value::as_array_mut) {
        for row in rows {
            redact_row(row);
        }
    }
    envelope
}

pub fn selected_enabled_runtime(
    envelope: &Value,
    other_config: &Value,
    config: &AppConfig,
) -> Result<SelectedLlmRow, LlmGateError> {
    let (envelope, _) = normalize_envelope(envelope, config);
    let rows = envelope
        .get("rows")
        .and_then(Value::as_array)
        .ok_or_else(|| LlmGateError::new("invalid_config", "LLM 配置行格式无效。"))?;
    let enabled_rows: Vec<_> = rows.iter().filter(|row| row_enabled(row)).collect();
    if enabled_rows.is_empty() {
        return Err(LlmGateError::new(
            "missing_fields",
            "没有已启用的 LLM 配置行，请在智能引擎设置中添加并启用至少一个 LLM 配置。",
        ));
    }
    let mut last_error: Option<LlmGateError> = None;
    for row in &enabled_rows {
        let runtime_config = row_to_legacy_config(row);
        match build_runtime_config(&runtime_config, other_config) {
            Ok(runtime) => {
                let fingerprint = compute_llm_fingerprint(&runtime);
                return Ok(SelectedLlmRow {
                    row_id: read_string(row, "id"),
                    row: (*row).clone(),
                    runtime_config,
                    runtime,
                    fingerprint,
                });
            }
            Err(error) => {
                last_error = Some(error);
                continue;
            }
        }
    }
    let detail = last_error
        .map(|e| format!("已启用 {} 行均无法加载：{}", enabled_rows.len(), e.message))
        .unwrap_or_else(|| "没有可用的已启用 LLM 配置行。".to_string());
    Err(LlmGateError::new("missing_fields", &detail))
}

pub fn row_to_legacy_config(row: &Value) -> Value {
    let mut map = Map::new();
    map.insert(
        "llmConfigVersion".to_string(),
        Value::String(crate::llm::LLM_CONFIG_VERSION.to_string()),
    );
    map.insert(
        "llmProvider".to_string(),
        Value::String(read_string(row, "provider")),
    );
    map.insert(
        "llmBaseUrl".to_string(),
        Value::String(normalize_base_url(&read_string(row, "baseUrl"))),
    );
    map.insert(
        "llmModel".to_string(),
        Value::String(read_string(row, "model")),
    );
    map.insert(
        "llmApiKey".to_string(),
        Value::String(read_string(row, "apiKey")),
    );
    map.insert(
        "secretSource".to_string(),
        Value::String(read_string(row, "secretSource").if_empty("saved")),
    );
    map.insert(
        "credentialSource".to_string(),
        Value::String("system_config".to_string()),
    );
    map.insert(
        "llmApiKeyRef".to_string(),
        Value::String(format!(
            "system_config:{}:llmApiKey",
            read_string(row, "id")
        )),
    );
    if let Some(advanced) = row.get("advanced").and_then(Value::as_object) {
        for field in ROW_ADVANCED_FIELDS {
            if let Some(value) = advanced.get(*field) {
                map.insert((*field).to_string(), value.clone());
            }
        }
    }
    Value::Object(map)
}

pub fn mark_row_preflight(
    envelope: &Value,
    row_id: &str,
    status: &str,
    reason_code: Option<&str>,
    message: Option<&str>,
    fingerprint: Option<&str>,
) -> Value {
    let mut next = envelope.clone();
    let checked_at = now_rfc3339();
    if let Some(rows) = next.get_mut("rows").and_then(Value::as_array_mut) {
        for row in rows {
            if read_string(row, "id") == row_id {
                row["preflight"] = json!({
                    "status": status,
                    "reasonCode": reason_code,
                    "message": message,
                    "checkedAt": checked_at,
                    "fingerprint": fingerprint,
                });
            }
        }
    }
    next
}

pub fn set_latest_preflight_run(
    envelope: &Value,
    attempted_row_ids: Vec<String>,
    winning_row_id: Option<String>,
    winning_fingerprint: Option<String>,
) -> Value {
    let mut next = envelope.clone();
    if let Some(map) = next.as_object_mut() {
        map.insert(
            "latestPreflightRun".to_string(),
            json!({
                "runId": format!("preflight_{}", Uuid::new_v4().simple()),
                "checkedAt": now_rfc3339(),
                "attemptedRowIds": attempted_row_ids,
                "winningRowId": winning_row_id,
                "winningFingerprint": winning_fingerprint,
            }),
        );
    }
    next
}

pub fn classify_fallback(error: &LlmGateError) -> FallbackCategory {
    let reason = error.reason_code.to_ascii_lowercase();
    let message = error.message.to_ascii_lowercase();
    if reason.contains("missing")
        || reason.contains("invalid_header")
        || reason.contains("invalid_api_key")
        || reason.contains("protected")
        || reason.contains("duplicate")
        || reason.contains("unsupported")
    {
        return FallbackCategory::InvalidConfig;
    }
    if reason.contains("invalid_response") || reason.contains("empty_response") {
        return FallbackCategory::InvalidResponse;
    }
    if message.contains("429")
        || message.contains("rate limit")
        || message.contains("quota")
        || message.contains("insufficient credit")
        || message.contains("billing")
    {
        return FallbackCategory::QuotaRateLimit;
    }
    if message.contains("401")
        || message.contains("403")
        || message.contains("invalid api key")
        || message.contains("invalid key")
        || message.contains("permission")
        || message.contains("authentication")
        || message.contains("unauthorized")
    {
        return FallbackCategory::Auth;
    }
    if message.contains("404")
        || message.contains("model not found")
        || message.contains("unknown model")
        || message.contains("unsupported model")
        || message.contains("model unavailable")
        || message.contains("deployment not found")
    {
        return FallbackCategory::ModelUnavailable;
    }
    if reason.contains("request_failed")
        || reason.contains("upstream_status")
        || message.contains("timeout")
        || message.contains("connection refused")
        || message.contains("dns")
        || message.contains("transport")
        || message.contains("5")
    {
        return FallbackCategory::Connectivity;
    }
    FallbackCategory::Unknown
}

pub fn metadata_matches_row(envelope: &Value, row_id: &str, fingerprint: &str) -> bool {
    envelope
        .get("rows")
        .and_then(Value::as_array)
        .and_then(|rows| rows.iter().find(|row| read_string(row, "id") == row_id))
        .and_then(|row| row.get("preflight"))
        .is_some_and(|preflight| {
            preflight.get("status").and_then(Value::as_str) == Some("passed")
                && preflight.get("fingerprint").and_then(Value::as_str) == Some(fingerprint)
        })
        || envelope.get("latestPreflightRun").is_some_and(|run| {
            run.get("winningRowId").and_then(Value::as_str) == Some(row_id)
                && run.get("winningFingerprint").and_then(Value::as_str) == Some(fingerprint)
        })
}

pub fn quick_snapshot(row: &Value) -> Value {
    json!({
        "provider": read_string(row, "provider"),
        "model": read_string(row, "model"),
        "baseUrl": read_string(row, "baseUrl"),
        "apiKey": "",
        "hasSavedApiKey": has_api_key(row),
        "secretSource": read_string(row, "secretSource").if_empty(if has_api_key(row) { "saved" } else { "none" }),
        "rowId": read_string(row, "id"),
        "priority": row.get("priority").and_then(Value::as_i64).unwrap_or(1),
    })
}

pub fn missing_fields_for_row(row: &Value) -> Vec<String> {
    let mut missing = Vec::new();
    if read_string(row, "model").is_empty() {
        missing.push("llmModel".to_string());
    }
    if read_string(row, "baseUrl").is_empty() {
        missing.push("llmBaseUrl".to_string());
    }
    if read_string(row, "apiKey").is_empty() {
        missing.push("llmApiKey".to_string());
    }
    missing
}

fn migrate_legacy(value: &Value, config: &AppConfig) -> (Value, bool) {
    let source_version = value
        .get("schemaVersion")
        .and_then(Value::as_i64)
        .unwrap_or(1);
    let mut row = row_from_legacy(value, 1, Some("llmcfg_legacy_1".to_string()), "migrated");
    if value.is_object() {
        row["preflight"] = json!({
            "status": if missing_fields_for_row(&row).is_empty() { "untested" } else { "missing_fields" },
            "reasonCode": if missing_fields_for_row(&row).is_empty() { Value::Null } else { Value::String("missing_fields".to_string()) },
            "message": Value::Null,
            "checkedAt": Value::Null,
            "fingerprint": Value::Null,
        });
        (
            json!({
                "schemaVersion": LLM_CONFIG_SET_SCHEMA_VERSION,
                "rows": [row],
                "latestPreflightRun": empty_latest_preflight_run(),
                "migration": {
                    "status": "migrated",
                    "message": "已将旧版单 LLM 配置迁移为第 1 行。",
                    "sourceSchemaVersion": source_version,
                }
            }),
            true,
        )
    } else {
        let mut envelope = default_envelope(config);
        envelope["migration"] = json!({
            "status": "reset",
            "message": "旧版 LLM 配置无法解析，已重置为一条空白默认配置，请重新配置。",
            "sourceSchemaVersion": source_version,
        });
        (envelope, true)
    }
}

fn normalize_new_envelope(value: &Value, config: &AppConfig) -> Value {
    let mut envelope = match value.as_object() {
        Some(map) => Value::Object(map.clone()),
        None => default_envelope(config),
    };
    if let Some(map) = envelope.as_object_mut() {
        map.insert(
            "schemaVersion".to_string(),
            Value::Number(LLM_CONFIG_SET_SCHEMA_VERSION.into()),
        );
        if !map.contains_key("latestPreflightRun") {
            map.insert(
                "latestPreflightRun".to_string(),
                empty_latest_preflight_run(),
            );
        }
        if !map.contains_key("migration") {
            map.insert("migration".to_string(), json!({"status":"not_needed","message":Value::Null,"sourceSchemaVersion":Value::Null}));
        }
    }
    let input_rows = value
        .get("rows")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut rows: Vec<Value> = input_rows
        .into_iter()
        .enumerate()
        .map(|(index, row)| normalize_row(&row, (index + 1) as i64, config))
        .collect();
    if rows.is_empty() {
        rows.push(default_row(config, 1));
    }
    rows.sort_by_key(|row| {
        row.get("priority")
            .and_then(Value::as_i64)
            .unwrap_or(i64::MAX)
    });
    for (index, row) in rows.iter_mut().enumerate() {
        row["priority"] = Value::Number(((index + 1) as i64).into());
    }
    envelope["rows"] = Value::Array(rows);
    envelope
}

fn normalize_row(row: &Value, priority: i64, config: &AppConfig) -> Value {
    let defaults = default_row(config, priority);
    let id = read_string(row, "id").if_empty(&stable_row_id());
    let provider = read_string(row, "provider").if_empty(&read_string(&defaults, "provider"));
    let mut normalized = json!({
        "id": id,
        "priority": row.get("priority").and_then(Value::as_i64).unwrap_or(priority),
        "enabled": row.get("enabled").and_then(Value::as_bool).unwrap_or(true),
        "provider": provider,
        "baseUrl": read_string(row, "baseUrl"),
        "model": read_string(row, "model"),
        "apiKey": read_string(row, "apiKey"),
        "hasApiKey": false,
        "secretSource": read_string(row, "secretSource"),
        "advanced": defaults.get("advanced").cloned().unwrap_or_else(|| json!({})),
        "modelStatus": row.get("modelStatus").cloned().unwrap_or_else(empty_model_status),
        "preflight": row.get("preflight").cloned().unwrap_or_else(empty_preflight),
    });
    if let Some(input_adv) = row.get("advanced").and_then(Value::as_object) {
        if let Some(adv) = normalized
            .get_mut("advanced")
            .and_then(Value::as_object_mut)
        {
            for field in ROW_ADVANCED_FIELDS {
                if let Some(value) = input_adv.get(*field) {
                    adv.insert((*field).to_string(), value.clone());
                }
            }
        }
    }
    let has_key = has_api_key(&normalized);
    normalized["hasApiKey"] = Value::Bool(has_key);
    if read_string(&normalized, "secretSource").is_empty() {
        normalized["secretSource"] =
            Value::String(if has_key { "saved" } else { "none" }.to_string());
    }
    normalized
}

fn row_from_legacy(
    legacy: &Value,
    priority: i64,
    id: Option<String>,
    migration_status: &str,
) -> Value {
    let mut advanced = Map::new();
    for field in ROW_ADVANCED_FIELDS {
        if let Some(value) = legacy.get(*field) {
            advanced.insert((*field).to_string(), value.clone());
        }
    }
    let api_key = read_string(legacy, "llmApiKey");
    json!({
        "id": id.unwrap_or_else(stable_row_id),
        "priority": priority,
        "enabled": true,
        "provider": read_string(legacy, "llmProvider").if_empty("openai_compatible"),
        "baseUrl": read_string(legacy, "llmBaseUrl"),
        "model": read_string(legacy, "llmModel"),
        "apiKey": api_key,
        "hasApiKey": !read_string(legacy, "llmApiKey").is_empty(),
        "secretSource": read_string(legacy, "secretSource").if_empty(if read_string(legacy, "llmApiKey").is_empty() { "none" } else { "saved" }),
        "advanced": Value::Object(advanced),
        "modelStatus": empty_model_status(),
        "preflight": empty_preflight(),
        "migrationStatus": migration_status,
    })
}

fn preserve_row_secrets(
    envelope: &mut Value,
    existing: Option<&Value>,
) -> Result<(), LlmGateError> {
    let existing_rows = existing
        .and_then(|value| value.get("rows"))
        .and_then(Value::as_array);
    let Some(rows) = envelope.get_mut("rows").and_then(Value::as_array_mut) else {
        return Ok(());
    };
    for row in rows {
        let api_key = read_string(row, "apiKey");
        if api_key.trim() == REDACTED_SECRET_PLACEHOLDER {
            return Err(LlmGateError::new(
                "redacted_secret_placeholder",
                "不能提交脱敏 API Key 占位符。",
            ));
        }
        if api_key.trim().is_empty() {
            let row_id = read_string(row, "id");
            if let Some(existing_key) = existing_rows
                .into_iter()
                .flatten()
                .find(|candidate| read_string(candidate, "id") == row_id)
                .map(|candidate| read_string(candidate, "apiKey"))
                .filter(|value| !value.trim().is_empty())
            {
                row["apiKey"] = Value::String(existing_key);
                row["hasApiKey"] = Value::Bool(true);
                if read_string(row, "secretSource").is_empty()
                    || read_string(row, "secretSource") == "none"
                {
                    row["secretSource"] = Value::String("saved".to_string());
                }
            } else if read_string(row, "model").trim().is_empty() {
                row["hasApiKey"] = Value::Bool(false);
            } else if read_string(row, "provider") == "openai_compatible"
                || read_string(row, "provider") == "anthropic_compatible"
                || read_string(row, "provider") == "kimi_compatible"
                || read_string(row, "provider") == "pi_compatible"
            {
                return Err(LlmGateError::new(
                    "missing_fields",
                    "LLM 配置缺失：`apiKey` 必填。",
                ));
            }
        } else {
            row["hasApiKey"] = Value::Bool(true);
            if read_string(row, "secretSource").is_empty()
                || read_string(row, "secretSource") == "none"
            {
                row["secretSource"] = Value::String("saved".to_string());
            }
        }
    }
    Ok(())
}

fn redact_row(row: &mut Value) {
    let has_key = has_api_key(row);
    row["apiKey"] = Value::String(String::new());
    row["hasApiKey"] = Value::Bool(has_key);
    if read_string(row, "secretSource").is_empty() {
        row["secretSource"] = Value::String(if has_key { "saved" } else { "none" }.to_string());
    }
}

fn empty_latest_preflight_run() -> Value {
    json!({
        "runId": Value::Null,
        "checkedAt": Value::Null,
        "attemptedRowIds": [],
        "winningRowId": Value::Null,
        "winningFingerprint": Value::Null,
    })
}

fn empty_model_status() -> Value {
    json!({"available": Value::Null, "lastCheckedAt": Value::Null, "reasonCode": Value::Null})
}

fn empty_preflight() -> Value {
    json!({"status": "untested", "reasonCode": Value::Null, "message": Value::Null, "checkedAt": Value::Null, "fingerprint": Value::Null})
}

fn row_enabled(row: &Value) -> bool {
    row.get("enabled").and_then(Value::as_bool).unwrap_or(true)
}

fn has_api_key(row: &Value) -> bool {
    !read_string(row, "apiKey").trim().is_empty()
}

fn read_string(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_string()
}

fn stable_row_id() -> String {
    format!("llmcfg_{}", Uuid::new_v4().simple())
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

trait EmptyStringExt {
    fn if_empty(self, fallback: &str) -> String;
}

impl EmptyStringExt for String {
    fn if_empty(self, fallback: &str) -> String {
        if self.trim().is_empty() {
            fallback.to_string()
        } else {
            self
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::AppConfig;

    #[test]
    fn migrates_legacy_config_to_schema_v2_row() {
        let config = AppConfig::for_tests();
        let legacy = json!({
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-old",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.example.com/v1",
            "llmTimeout": 99
        });
        let (envelope, migrated) = normalize_envelope(&legacy, &config);
        assert!(migrated);
        assert_eq!(envelope["schemaVersion"], 2);
        assert_eq!(envelope["rows"][0]["priority"], 1);
        assert_eq!(envelope["rows"][0]["advanced"]["llmTimeout"], 99);
        assert_eq!(envelope["migration"]["status"], "migrated");
    }

    #[test]
    fn preserves_secrets_by_row_id_after_reorder() {
        let config = AppConfig::for_tests();
        let existing = json!({
            "schemaVersion": 2,
            "rows": [
                {"id":"a","priority":1,"enabled":true,"provider":"openai_compatible","baseUrl":"u","model":"m","apiKey":"sk-a","advanced":{}},
                {"id":"b","priority":2,"enabled":true,"provider":"openai_compatible","baseUrl":"u","model":"m","apiKey":"sk-b","advanced":{}}
            ]
        });
        let input = json!({
            "schemaVersion": 2,
            "rows": [
                {"id":"b","priority":1,"enabled":true,"provider":"openai_compatible","baseUrl":"u","model":"m2","apiKey":"","advanced":{}},
                {"id":"a","priority":2,"enabled":true,"provider":"openai_compatible","baseUrl":"u","model":"m1","apiKey":"","advanced":{}}
            ]
        });
        let saved = normalize_for_save(&input, Some(&existing), &config).unwrap();
        assert_eq!(saved["rows"][0]["id"], "b");
        assert_eq!(saved["rows"][0]["apiKey"], "sk-b");
        assert_eq!(saved["rows"][1]["apiKey"], "sk-a");
    }

    #[test]
    fn fallback_classifier_respects_allowed_and_blocked_categories() {
        assert_eq!(
            classify_fallback(&LlmGateError::new("request_failed", "connection refused")),
            FallbackCategory::Connectivity
        );
        assert!(classify_fallback(&LlmGateError::new(
            "upstream_status",
            "HTTP 401 invalid api key"
        ))
        .is_fallback_eligible());
        assert_eq!(
            classify_fallback(&LlmGateError::new(
                "upstream_status",
                "HTTP 429 quota exceeded"
            )),
            FallbackCategory::QuotaRateLimit
        );
        assert!(
            !classify_fallback(&LlmGateError::new("invalid_headers", "bad json"))
                .is_fallback_eligible()
        );
    }
}
