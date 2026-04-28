use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use std::{env, fs, sync::LazyLock};
use tempfile::TempDir;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    sync::Mutex,
};
use tower::util::ServiceExt;
use uuid::Uuid;

static ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

struct EnvVarGuard {
    key: String,
    original: Option<String>,
}

impl EnvVarGuard {
    fn set(key: &str, value: &str) -> Self {
        let original = env::var(key).ok();
        env::set_var(key, value);
        Self {
            key: key.to_string(),
            original,
        }
    }

    fn remove(key: &str) -> Self {
        let original = env::var(key).ok();
        env::remove_var(key);
        Self {
            key: key.to_string(),
            original,
        }
    }
}

impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        if let Some(original) = &self.original {
            env::set_var(&self.key, original);
        } else {
            env::remove_var(&self.key);
        }
    }
}

async fn spawn_llm_mock_server(body: &'static str) -> String {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind mock llm server");
    let address = listener.local_addr().expect("mock llm address");
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let _ = stream.read(&mut buffer).await;
                let response = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    format!("http://{address}/v1")
}

#[tokio::test]
async fn system_config_crud_roundtrip_stays_deuserized() {
    let config = isolated_test_config("system-config-crud");
    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    let app = build_router(state);

    let defaults_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/system-config/defaults")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(defaults_response.status(), StatusCode::OK);

    let defaults_json: Value = serde_json::from_slice(
        &to_bytes(defaults_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(defaults_json.get("llmConfig").is_some());
    assert!(defaults_json.get("otherConfig").is_some());
    assert!(defaults_json.get("id").is_none());
    assert!(defaults_json.get("user_id").is_none());

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-test",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.openai.com/v1"
        },
        "otherConfig": {
            "llmConcurrency": 3,
            "llmGapMs": 1500
        }
    });

    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let reloaded_state = AppState::from_config(config)
        .await
        .expect("reloaded state should build");
    let reloaded_app = build_router(reloaded_state);

    let current_response = reloaded_app
        .clone()
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(current_response.status(), StatusCode::OK);
    let current_json: Value = serde_json::from_slice(
        &to_bytes(current_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(current_json["llmConfig"]["llmApiKey"], "sk-test");
    assert_eq!(
        current_json["llmConfig"]["llmConfigVersion"],
        "intelligent-engine-v1"
    );
    assert_eq!(current_json["otherConfig"]["llmConcurrency"], 3);
    assert!(current_json.get("id").is_none());
    assert!(current_json.get("user_id").is_none());

    let delete_response = reloaded_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(delete_response.status(), StatusCode::OK);
    let delete_json: Value = serde_json::from_slice(
        &to_bytes(delete_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(delete_json["llmConfig"]["llmApiKey"], "");
}

#[tokio::test]
async fn system_config_save_requires_explicit_llm_key_without_promoting_app_default() {
    let mut config = isolated_test_config("system-config-no-app-key-promotion");
    config.llm_api_key = "sk-app-fallback-secret".to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let save_response = app
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "llmConfig": {
                            "llmProvider": "openai_compatible",
                            "llmModel": "gpt-5",
                            "llmBaseUrl": "https://api.openai.com/v1"
                        },
                        "otherConfig": {}
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(save_response.status(), StatusCode::BAD_REQUEST);
    let error_json: Value = serde_json::from_slice(
        &to_bytes(save_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(error_json.to_string().contains("apiKey"));
    assert!(!error_json.to_string().contains("sk-app-fallback-secret"));
}

#[tokio::test]
async fn system_config_helper_endpoints_are_available() {
    let _env_guard = ENV_LOCK.lock().await;
    let _codex_home_guard = EnvVarGuard::remove("CODEX_HOME");
    let _codex_host_guard = EnvVarGuard::remove("ARGUS_CODEX_HOST_DIR");
    let state = AppState::from_config(isolated_test_config("system-config-helper"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let providers_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/system-config/llm-providers")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(providers_response.status(), StatusCode::OK);
    let providers_json: Value = serde_json::from_slice(
        &to_bytes(providers_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(providers_json["providers"].as_array().unwrap().len(), 2);

    let preflight_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/agent-preflight")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preflight_response.status(), StatusCode::OK);
    let preflight_json: Value = serde_json::from_slice(
        &to_bytes(preflight_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(preflight_json["ok"], false);
    assert_eq!(preflight_json["reasonCode"], "missing_fields");
    assert_eq!(
        preflight_json["metadata"]["runner"]["reason_code"],
        "not_checked"
    );
}

#[tokio::test]
async fn agent_preflight_redacts_credentials_and_reports_runner_stage() {
    let _env_guard = ENV_LOCK.lock().await;
    let _codex_home_guard = EnvVarGuard::remove("CODEX_HOME");
    let _codex_host_guard = EnvVarGuard::remove("ARGUS_CODEX_HOST_DIR");
    let _default_runner_guard = EnvVarGuard::set("AGENTFLOW_DEFAULT_RUNNER_ENABLED", "false");
    let state = AppState::from_config(isolated_test_config("system-config-agent-preflight-runner"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let mock_base_url =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"pong"}}]}"#).await;

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-agentflow-secret",
            "llmModel": "gpt-5",
            "llmBaseUrl": mock_base_url
        },
        "otherConfig": {}
    });

    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let stale_preflight_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/agent-preflight")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(stale_preflight_response.status(), StatusCode::OK);
    let stale_preflight_json: Value = serde_json::from_slice(
        &to_bytes(stale_preflight_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(stale_preflight_json["ok"], false);
    assert_eq!(stale_preflight_json["stage"], "llm_test");
    assert_eq!(stale_preflight_json["reasonCode"], "llm_test_stale");
    assert_eq!(
        stale_preflight_json["savedConfig"]["apiKey"],
        "***configured***"
    );
    assert!(!stale_preflight_json
        .to_string()
        .contains("sk-agentflow-secret"));

    let test_payload = json!({
        "provider": "openai_compatible",
        "apiKey": "sk-agentflow-secret",
        "model": "gpt-5",
        "baseUrl": mock_base_url
    });
    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(test_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);

    let preflight_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/agent-preflight")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preflight_response.status(), StatusCode::OK);
    let preflight_json: Value = serde_json::from_slice(
        &to_bytes(preflight_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    assert_eq!(preflight_json["ok"], false);
    assert_eq!(preflight_json["stage"], "runner");
    assert_eq!(preflight_json["reasonCode"], "runner_missing");
    assert_eq!(preflight_json["savedConfig"]["apiKey"], "***configured***");
    assert!(!preflight_json.to_string().contains("sk-agentflow-secret"));
    assert_eq!(preflight_json["metadata"]["runner"]["ok"], false);
}

#[tokio::test]
async fn agent_preflight_rejects_codex_host_credentials_without_saved_config() {
    let _env_guard = ENV_LOCK.lock().await;
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
        r#"{"OPENAI_API_KEY":"sk-codex-host-secret"}"#,
    )
    .expect("write auth");
    let _codex_home_guard = EnvVarGuard::remove("CODEX_HOME");
    let _codex_host_guard = EnvVarGuard::set(
        "ARGUS_CODEX_HOST_DIR",
        temp_dir.path().to_str().expect("utf8 temp path"),
    );
    let _runner_guard = EnvVarGuard::set("AGENTFLOW_RUNNER_COMMAND", "true");
    let state = AppState::from_config(isolated_test_config("system-config-agent-preflight-codex"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let preflight_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/agent-preflight")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preflight_response.status(), StatusCode::OK);
    let preflight_json: Value = serde_json::from_slice(
        &to_bytes(preflight_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    assert_eq!(preflight_json["ok"], false);
    assert_eq!(preflight_json["reasonCode"], "missing_fields");
    assert_eq!(preflight_json["savedConfig"], Value::Null);
    assert_eq!(preflight_json["effectiveConfig"]["apiKey"], "");
    assert!(!preflight_json.to_string().contains("sk-codex-host-secret"));
}

#[tokio::test]
async fn test_llm_runs_real_openai_compatible_generation_and_persists_metadata() {
    let state = AppState::from_config(isolated_test_config("system-config-real-test-openai"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let base_url = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-real-secret",
            "llmModel": "gpt-5",
            "llmBaseUrl": base_url,
            "llmCustomHeaders": {"X-Trace": "header-secret"}
        },
        "otherConfig": {"llmConcurrency": 2, "llmGapMs": 5}
    });
    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-real-secret",
                        "model": "gpt-5",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"]
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);
    let mismatched_payload: Value = serde_json::from_slice(
        &to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(mismatched_payload["success"], false);
    assert_eq!(
        mismatched_payload["message"],
        "当前测试请求与已保存 LLM 配置不一致，请先保存后再测试。"
    );

    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-real-secret",
                        "model": "gpt-5",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"],
                        "customHeaders": r#"{"X-Trace":"header-secret"}"#
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);
    let payload: Value = serde_json::from_slice(
        &to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["metadata"]["provider"], "openai_compatible");
    assert!(payload["metadata"]["fingerprint"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
    assert!(!payload.to_string().contains("sk-real-secret"));
    assert!(!payload.to_string().contains("header-secret"));

    let current_response = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current: Value = serde_json::from_slice(
        &to_bytes(current_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        current["llmTestMetadata"]["fingerprint"],
        payload["metadata"]["fingerprint"]
    );
}

#[tokio::test]
async fn test_llm_rejects_empty_text_response() {
    let state = AppState::from_config(isolated_test_config("system-config-real-test-empty"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let base_url = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":""}}]}"#).await;

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-empty-secret",
            "llmModel": "gpt-5",
            "llmBaseUrl": base_url
        },
        "otherConfig": {}
    });
    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let test_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-empty-secret",
                        "model": "gpt-5",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"]
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let payload: Value = serde_json::from_slice(
        &to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(payload["success"], false);
    assert!(payload["message"].as_str().unwrap().contains("非空文本"));
}

#[tokio::test]
async fn system_config_llm_provider_catalog_matches_rust_registry_semantics() {
    let state = AppState::from_config(isolated_test_config("system-config-provider-catalog"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let providers_response = app
        .oneshot(
            Request::get("/api/v1/system-config/llm-providers")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(providers_response.status(), StatusCode::OK);

    let providers_json: Value = serde_json::from_slice(
        &to_bytes(providers_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let providers = providers_json["providers"]
        .as_array()
        .expect("providers should be an array");

    let ordered_ids: Vec<&str> = providers
        .iter()
        .map(|item| item["id"].as_str().expect("provider id should be a string"))
        .collect();
    assert_eq!(
        ordered_ids,
        vec!["openai_compatible", "anthropic_compatible"]
    );

    let custom = providers
        .iter()
        .find(|item| item["id"] == "openai_compatible")
        .expect("openai-compatible provider should exist");
    assert_eq!(custom["defaultBaseUrl"], "https://api.openai.com/v1");
    assert_eq!(custom["supportsCustomHeaders"], true);
}

#[tokio::test]
async fn fetch_llm_models_normalizes_provider_and_base_url_via_registry_module() {
    let state = AppState::from_config(isolated_test_config("system-config-fetch-models"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/fetch-llm-models")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-custom",
                        "baseUrl": "https://gateway.example/v1/chat/completions?foo=bar#frag",
                        "customHeaders": "{\" Authorization \": 123, \"\": \"skip\", \"X-Trace\": null}",
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["resolvedProvider"], "openai_compatible");
    assert_eq!(payload["defaultModel"], "gpt-5");
    assert_eq!(payload["baseUrlUsed"], "https://gateway.example/v1");
    assert!(payload["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "gpt-5"));
}

#[tokio::test]
async fn fetch_llm_models_rejects_non_flat_custom_headers() {
    let state = AppState::from_config(isolated_test_config("system-config-fetch-models-errors"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/fetch-llm-models")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-openai",
                        "baseUrl": "https://api.openai.com/v1",
                        "customHeaders": "{\"X-Nested\": {\"bad\": true}}",
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);

    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["error"], "llmCustomHeaders 必须是扁平的 JSON 对象");
}

#[tokio::test]
async fn system_config_defaults_follow_app_config() {
    let mut config = isolated_test_config("system-config-defaults");
    config.llm_provider = "gemini".to_string();
    config.llm_model = "gemini-2.5-pro".to_string();
    config.llm_base_url = "https://example.test/v1".to_string();
    config.llm_timeout_seconds = 123;
    config.max_analyze_files = 88;
    config.llm_concurrency = 5;
    config.llm_gap_ms = 2222;
    config.gemini_api_key = "gemini-default-key".to_string();

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::get("/api/v1/system-config/defaults")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["llmConfig"]["llmProvider"], "openai_compatible");
    assert_eq!(payload["llmConfig"]["llmModel"], "gemini-2.5-pro");
    assert_eq!(
        payload["llmConfig"]["llmBaseUrl"],
        "https://example.test/v1"
    );
    assert_eq!(payload["llmConfig"]["llmTimeout"], 123000);
    assert_eq!(payload["otherConfig"]["maxAnalyzeFiles"], 88);
    assert_eq!(payload["otherConfig"]["llmConcurrency"], 5);
    assert_eq!(payload["otherConfig"]["llmGapMs"], 2222);
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}
