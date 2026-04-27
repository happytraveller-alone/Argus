use std::{
    env, fs,
    path::{Path, PathBuf},
};

use serde_json::{Map, Value};

use crate::config::AppConfig;

#[derive(Clone, Copy, Debug)]
enum CodexConfigSource {
    CodexHome,
    HostMount,
}

impl CodexConfigSource {
    fn credential_source(self) -> &'static str {
        match self {
            Self::CodexHome => "codex_home",
            Self::HostMount => "codex_host_dir",
        }
    }

    fn api_key_ref(self) -> &'static str {
        match self {
            Self::CodexHome => "codex_home:auth.json",
            Self::HostMount => "codex_host:auth.json",
        }
    }

    fn allow_unreadable_auth_reference(self) -> bool {
        matches!(self, Self::HostMount)
    }
}

#[derive(Clone, Debug)]
struct CodexConfigCandidate {
    path: PathBuf,
    source: CodexConfigSource,
}

pub fn build_agentflow_llm_config(config: &AppConfig, saved: Option<&Value>) -> Value {
    let codex = load_codex_llm_config(config);
    build_agentflow_llm_config_from_sources(config, saved, codex.as_ref())
}

fn build_agentflow_llm_config_from_sources(
    config: &AppConfig,
    saved: Option<&Value>,
    codex: Option<&Value>,
) -> Value {
    let codex_ref = codex;
    let saved_has_api_key = config_value(saved, "llmApiKey").is_some();
    let codex_has_api_key = config_value(codex_ref, "llmApiKey").is_some();
    let credential_source = if saved_has_api_key {
        "system_config".to_string()
    } else if let Some(source) = config_value(codex_ref, "credentialSource") {
        source
    } else {
        "app_config".to_string()
    };
    let api_key_ref = if saved_has_api_key {
        None
    } else if codex_has_api_key {
        config_value(codex_ref, "llmApiKeyRef")
    } else {
        None
    };

    let mut object = Map::new();
    object.insert(
        "llmProvider".to_string(),
        Value::String(
            config_value(saved, "llmProvider")
                .or_else(|| config_value(codex_ref, "llmProvider"))
                .unwrap_or_else(|| config.llm_provider.clone()),
        ),
    );
    object.insert(
        "llmModel".to_string(),
        Value::String(
            config_value(saved, "llmModel")
                .or_else(|| config_value(codex_ref, "llmModel"))
                .unwrap_or_else(|| config.llm_model.clone()),
        ),
    );
    object.insert(
        "llmBaseUrl".to_string(),
        Value::String(
            config_value(saved, "llmBaseUrl")
                .or_else(|| config_value(codex_ref, "llmBaseUrl"))
                .unwrap_or_else(|| config.llm_base_url.clone()),
        ),
    );
    object.insert(
        "llmApiKey".to_string(),
        Value::String(
            config_value(saved, "llmApiKey")
                .or_else(|| config_value(codex_ref, "llmApiKey"))
                .unwrap_or_else(|| config.llm_api_key.clone()),
        ),
    );
    object.insert(
        "credentialSource".to_string(),
        Value::String(credential_source),
    );
    if let Some(api_key_ref) = api_key_ref {
        object.insert("llmApiKeyRef".to_string(), Value::String(api_key_ref));
    }
    Value::Object(object)
}

fn load_codex_llm_config(config: &AppConfig) -> Option<Value> {
    codex_config_candidates().into_iter().find_map(|candidate| {
        load_codex_llm_config_from_dir(config, &candidate.path, candidate.source)
    })
}

fn codex_config_candidates() -> Vec<CodexConfigCandidate> {
    let mut candidates = Vec::new();
    if let Some(path) = env_trimmed("CODEX_HOME").map(PathBuf::from) {
        candidates.push(CodexConfigCandidate {
            path,
            source: CodexConfigSource::CodexHome,
        });
    }
    if let Some(path) = env_trimmed("ARGUS_CODEX_HOST_DIR").map(PathBuf::from) {
        candidates.push(CodexConfigCandidate {
            path,
            source: CodexConfigSource::HostMount,
        });
    }
    candidates
}

fn load_codex_llm_config_from_dir(
    app_config: &AppConfig,
    codex_dir: &Path,
    source: CodexConfigSource,
) -> Option<Value> {
    let config_text = fs::read_to_string(codex_dir.join("config.toml")).ok();
    let auth_text = fs::read_to_string(codex_dir.join("auth.json")).ok();
    let parsed_config = config_text
        .as_deref()
        .and_then(|text| toml::from_str::<toml::Value>(text).ok());
    let parsed_auth = auth_text
        .as_deref()
        .and_then(|text| serde_json::from_str::<Value>(text).ok());

    let has_auth = parsed_auth.as_ref().is_some_and(codex_auth_has_material)
        || (source.allow_unreadable_auth_reference() && auth_text.is_none());
    let has_config = parsed_config.is_some();
    if !has_auth && !has_config {
        return None;
    }

    let provider_id = parsed_config
        .as_ref()
        .and_then(|value| toml_string(value, &["model_provider"]))
        .unwrap_or_else(|| app_config.llm_provider.clone());
    let model = parsed_config
        .as_ref()
        .and_then(|value| toml_string(value, &["model"]))
        .or_else(|| {
            parsed_config
                .as_ref()
                .and_then(|value| toml_string(value, &["model_context", "model"]))
        })
        .unwrap_or_else(|| app_config.llm_model.clone());
    let base_url = parsed_config
        .as_ref()
        .and_then(|value| toml_string(value, &["model_providers", &provider_id, "base_url"]))
        .or_else(|| {
            parsed_config
                .as_ref()
                .and_then(|value| toml_string(value, &["model_provider", "base_url"]))
        })
        .unwrap_or_else(|| app_config.llm_base_url.clone());

    let mut object = Map::new();
    object.insert("llmProvider".to_string(), Value::String(provider_id));
    object.insert("llmModel".to_string(), Value::String(model));
    object.insert("llmBaseUrl".to_string(), Value::String(base_url));
    object.insert(
        "credentialSource".to_string(),
        Value::String(source.credential_source().to_string()),
    );
    if has_auth {
        object.insert(
            "llmApiKey".to_string(),
            Value::String("codex_auth_ref".to_string()),
        );
        object.insert(
            "llmApiKeyRef".to_string(),
            Value::String(source.api_key_ref().to_string()),
        );
    }
    Some(Value::Object(object))
}

fn env_trimmed(key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn toml_string(value: &toml::Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn codex_auth_has_material(value: &Value) -> bool {
    match value {
        Value::Object(object) => object.iter().any(|(key, child)| {
            let normalized = key.replace('-', "_").to_ascii_lowercase();
            ((normalized.contains("token")
                || normalized.contains("api_key")
                || normalized.contains("auth"))
                && child.as_str().is_some_and(|text| !text.trim().is_empty()))
                || codex_auth_has_material(child)
        }),
        Value::Array(items) => items.iter().any(codex_auth_has_material),
        _ => false,
    }
}

fn config_value(value: Option<&Value>, key: &str) -> Option<String> {
    value?
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::json;
    use tempfile::TempDir;

    use super::{
        build_agentflow_llm_config_from_sources, load_codex_llm_config_from_dir, CodexConfigSource,
    };
    use crate::config::AppConfig;

    #[test]
    fn explicit_codex_home_config_returns_redacted_reference_only() {
        let temp_dir = TempDir::new().expect("temp dir");
        fs::write(
            temp_dir.path().join("config.toml"),
            r#"
model = "gpt-5.1-codex-max"
model_provider = "openai"

[model_providers.openai]
base_url = "https://api.openai.com/v1"
"#,
        )
        .expect("write config");
        fs::write(
            temp_dir.path().join("auth.json"),
            r#"{"OPENAI_API_KEY":"sk-test-secret"}"#,
        )
        .expect("write auth");

        let value = load_codex_llm_config_from_dir(
            &AppConfig::for_tests(),
            temp_dir.path(),
            CodexConfigSource::CodexHome,
        )
        .expect("codex config should load");

        assert_eq!(value["llmModel"], "gpt-5.1-codex-max");
        assert_eq!(value["llmApiKey"], "codex_auth_ref");
        assert_eq!(value["llmApiKeyRef"], "codex_home:auth.json");
        assert!(!value.to_string().contains("sk-test-secret"));
    }

    #[test]
    fn host_mount_reference_can_fill_saved_config_gaps() {
        let temp_dir = TempDir::new().expect("temp dir");
        fs::write(
            temp_dir.path().join("config.toml"),
            r#"
model = "gpt-5.1"
model_provider = "openai"
"#,
        )
        .expect("write config");
        fs::write(
            temp_dir.path().join("auth.json"),
            r#"{"tokens":{"access_token":"opaque-token"}}"#,
        )
        .expect("write auth");

        let codex = load_codex_llm_config_from_dir(
            &AppConfig::for_tests(),
            temp_dir.path(),
            CodexConfigSource::HostMount,
        )
        .expect("host mount reference should load");
        let saved = json!({
            "llmProvider": "openai",
            "llmModel": "",
            "llmBaseUrl": "",
            "llmApiKey": ""
        });
        let merged = build_agentflow_llm_config_from_sources(
            &AppConfig::for_tests(),
            Some(&saved),
            Some(&codex),
        );

        assert_eq!(merged["llmModel"], "gpt-5.1");
        assert_eq!(merged["llmApiKey"], "codex_auth_ref");
        assert_eq!(merged["llmApiKeyRef"], "codex_host:auth.json");
        assert_eq!(merged["credentialSource"], "codex_host_dir");
    }
}
