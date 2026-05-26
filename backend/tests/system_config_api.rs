use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router, config::AppConfig, runtime::shutdown::ShutdownGate, state::AppState,
};
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
    let app = build_router(state, ShutdownGate::default());

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
    let reloaded_app = build_router(reloaded_state, ShutdownGate::default());

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
    assert_eq!(current_json["llmConfig"]["schemaVersion"], 2);
    assert_eq!(current_json["llmConfig"]["rows"][0]["apiKey"], "");
    assert_eq!(current_json["llmConfig"]["rows"][0]["hasApiKey"], true);
    assert_eq!(
        current_json["llmConfig"]["rows"][0]["secretSource"],
        "saved"
    );
    assert_eq!(
        current_json["llmConfig"]["rows"][0]["provider"],
        "openai_compatible"
    );
    assert_eq!(current_json["llmConfig"]["rows"][0]["model"], "gpt-5");
    assert_eq!(
        current_json["llmConfig"]["rows"][0]["baseUrl"],
        "https://api.openai.com/v1"
    );
    assert!(!current_json.to_string().contains("sk-test"));
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
    assert_eq!(delete_json["llmConfig"]["schemaVersion"], 2);
    assert_eq!(delete_json["llmConfig"]["rows"][0]["apiKey"], "");
}

#[tokio::test]
async fn system_config_save_requires_explicit_llm_key_without_promoting_app_default() {
    let mut config = isolated_test_config("system-config-no-app-key-promotion");
    config.llm_api_key = "sk-app-fallback-secret".to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

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
    let app = build_router(state, ShutdownGate::default());

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
    assert_eq!(preflight_json["reasonCode"], "default_config");
    assert_eq!(
        preflight_json["metadata"]["runner"]["reason_code"],
        "not_checked"
    );
}

#[tokio::test]
async fn agent_preflight_redacts_credentials_and_reports_native_pipeline_ready() {
    let _env_guard = ENV_LOCK.lock().await;
    let _codex_home_guard = EnvVarGuard::remove("CODEX_HOME");
    let _codex_host_guard = EnvVarGuard::remove("ARGUS_CODEX_HOST_DIR");
    let _default_runner_guard = EnvVarGuard::set("AGENTFLOW_DEFAULT_RUNNER_ENABLED", "false");
    let state = AppState::from_config(isolated_test_config("system-config-agent-preflight-runner"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
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
    assert_eq!(stale_preflight_json["ok"], true);
    assert!(stale_preflight_json["stage"].is_null());
    assert!(stale_preflight_json["reasonCode"].is_null());
    assert_eq!(
        stale_preflight_json["metadata"]["pipeline"]["agent_count"],
        8
    );
    assert_eq!(stale_preflight_json["savedConfig"]["apiKey"], "");
    assert_eq!(stale_preflight_json["savedConfig"]["hasSavedApiKey"], true);
    assert_eq!(stale_preflight_json["savedConfig"]["secretSource"], "saved");
    assert_eq!(
        stale_preflight_json["metadata"]["preflightRows"]["attemptedRowIds"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(stale_preflight_json["metadata"]["preflightRows"]["winningRowId"].is_string());
    assert!(!stale_preflight_json
        .to_string()
        .contains("sk-agentflow-secret"));

    let test_payload = json!({
        "provider": "openai_compatible",
        "secretSource": "saved",
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

    assert_eq!(preflight_json["ok"], true);
    assert!(preflight_json["stage"].is_null());
    assert!(preflight_json["reasonCode"].is_null());
    assert_eq!(preflight_json["savedConfig"]["apiKey"], "");
    assert_eq!(preflight_json["savedConfig"]["hasSavedApiKey"], true);
    assert_eq!(preflight_json["savedConfig"]["secretSource"], "saved");
    assert!(!preflight_json.to_string().contains("sk-agentflow-secret"));
    assert_eq!(preflight_json["metadata"]["runner"]["ok"], true);
    assert_eq!(
        preflight_json["metadata"]["runner"]["reason_code"],
        "native_rust_pipeline"
    );
    assert_eq!(
        preflight_json["metadata"]["pipeline"]["agents"]
            .as_array()
            .unwrap()
            .len(),
        8
    );
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
    let app = build_router(state, ShutdownGate::default());

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
    assert_eq!(preflight_json["reasonCode"], "default_config");
    assert_eq!(preflight_json["savedConfig"], Value::Null);
    assert_eq!(preflight_json["effectiveConfig"]["apiKey"], "");
    assert!(!preflight_json.to_string().contains("sk-codex-host-secret"));
}

#[tokio::test]
async fn agent_preflight_baseline_behavior() {
    // Baseline snapshot of agent_preflight response shape with a 1-row envelope.
    // Must pass unmodified. If Step 1.2's inline import loop drifts from
    // agent_preflight semantics, assertions here will catch it.
    let _env_guard = ENV_LOCK.lock().await;
    let _codex_home_guard = EnvVarGuard::remove("CODEX_HOME");
    let _codex_host_guard = EnvVarGuard::remove("ARGUS_CODEX_HOST_DIR");
    let _default_runner_guard = EnvVarGuard::set("AGENTFLOW_DEFAULT_RUNNER_ENABLED", "false");
    let state =
        AppState::from_config(isolated_test_config("system-config-agent-preflight-baseline"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let mock_base_url =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"preflight baseline"}}]}"#)
            .await;

    // Pre-load a 1-row saved config (mirrors the pattern at line 298)
    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-preflight-baseline-secret",
            "llmModel": "gpt-5-preflight",
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

    // Run test-llm so the row has a fingerprint on record
    let test_payload = json!({
        "provider": "openai_compatible",
        "secretSource": "saved",
        "model": "gpt-5-preflight",
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

    // Call agent-preflight and capture the baseline shape
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

    // v1 baseline contract assertions
    assert_eq!(preflight_json["ok"], true);
    assert!(preflight_json["stage"].is_null());
    assert!(preflight_json["reasonCode"].is_null());
    assert_eq!(preflight_json["savedConfig"]["hasSavedApiKey"], true);
    assert_eq!(preflight_json["savedConfig"]["secretSource"], "saved");
    assert_eq!(preflight_json["savedConfig"]["apiKey"], "");
    // preflightRows: exactly 1 row attempted, winningRowId is a string
    assert_eq!(
        preflight_json["metadata"]["preflightRows"]["attemptedRowIds"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(preflight_json["metadata"]["preflightRows"]["winningRowId"].is_string());
    // fingerprint must be present in metadata
    assert!(
        preflight_json["metadata"]["fingerprint"].is_string()
            || preflight_json["metadata"]["preflightRows"]["winningRowId"].is_string()
    );
    assert!(!preflight_json
        .to_string()
        .contains("sk-preflight-baseline-secret"));
}

#[tokio::test]
async fn test_llm_runs_real_openai_compatible_generation_and_persists_metadata() {
    let state = AppState::from_config(isolated_test_config("system-config-real-test-openai"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
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
        "当前测试请求与已保存 LLM 配置行不一致，请先保存后再测试。"
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
                        "secretSource": "saved",
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
    assert_eq!(current["llmConfig"]["rows"][0]["apiKey"], "");
    assert_eq!(current["llmConfig"]["rows"][0]["hasApiKey"], true);
    assert!(!current.to_string().contains("sk-real-secret"));
    assert_eq!(
        current["llmTestMetadata"]["fingerprint"],
        payload["metadata"]["fingerprint"]
    );
}

#[tokio::test]
async fn test_llm_batch_validates_saved_rows_and_persists_each_status_without_secrets() {
    let state = AppState::from_config(isolated_test_config("system-config-batch-validate"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let fail_base_url = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":""}}]}"#).await;
    let pass_base_url =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;

    let save_payload = json!({
        "llmConfig": {
            "schemaVersion": 2,
            "rows": [
                {
                    "id": "row-disabled",
                    "priority": 1,
                    "enabled": false,
                    "provider": "openai_compatible",
                    "baseUrl": pass_base_url,
                    "model": "gpt-disabled",
                    "apiKey": "sk-disabled-secret",
                    "advanced": {"llmCustomHeaders": {"X-Disabled-Secret": "disabled-header-secret"}},
                    "preflight": {
                        "status": "passed",
                        "reasonCode": null,
                        "message": "keep old disabled preflight",
                        "checkedAt": "2026-01-01T00:00:00Z",
                        "fingerprint": "sha256:old-disabled"
                    }
                },
                {
                    "id": "row-missing",
                    "priority": 2,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": pass_base_url,
                    "model": "",
                    "apiKey": "sk-missing-secret",
                    "advanced": {"llmCustomHeaders": {"X-Missing-Secret": "missing-header-secret"}}
                },
                {
                    "id": "row-fails",
                    "priority": 3,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": fail_base_url,
                    "model": "gpt-fails",
                    "apiKey": "sk-fails-secret",
                    "advanced": {"llmCustomHeaders": {"X-Fails-Secret": "fails-header-secret"}}
                },
                {
                    "id": "row-passes",
                    "priority": 4,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": pass_base_url,
                    "model": "gpt-passes",
                    "apiKey": "sk-passes-secret",
                    "advanced": {"llmCustomHeaders": {"X-Passes-Secret": "passes-header-secret"}}
                }
            ],
            "latestPreflightRun": {
                "runId": null,
                "checkedAt": null,
                "attemptedRowIds": [],
                "winningRowId": null,
                "winningFingerprint": null
            },
            "migration": {"status": "not_needed", "message": null, "sourceSchemaVersion": null}
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

    let rejected_payload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm/batch")
                .header("content-type", "application/json")
                .body(Body::from(json!({"llmConfig": {"rows": []}}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(rejected_payload_response.status(), StatusCode::BAD_REQUEST);

    let batch_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm/batch")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(batch_response.status(), StatusCode::OK);
    let payload: Value = serde_json::from_slice(
        &to_bytes(batch_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let payload_text = payload.to_string();

    assert_eq!(payload["success"], false);
    assert_eq!(payload["reasonCode"], "row_validation_failed");
    assert_eq!(
        payload["attemptedRowIds"],
        json!(["row-fails", "row-passes"])
    );
    assert_eq!(payload["skippedRowIds"], json!(["row-disabled"]));
    assert_eq!(payload["missingFieldRowIds"], json!(["row-missing"]));
    assert_eq!(payload["failedRowIds"], json!(["row-fails"]));
    assert_eq!(payload["passedRowIds"], json!(["row-passes"]));
    let row_statuses: Vec<_> = payload["rows"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            (
                row["rowId"].as_str().unwrap(),
                row["status"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(
        row_statuses,
        vec![
            ("row-disabled", "skipped_disabled"),
            ("row-missing", "missing_fields"),
            ("row-fails", "failed"),
            ("row-passes", "passed"),
        ]
    );
    for secret in [
        "sk-disabled-secret",
        "sk-missing-secret",
        "sk-fails-secret",
        "sk-passes-secret",
        "disabled-header-secret",
        "missing-header-secret",
        "fails-header-secret",
        "passes-header-secret",
        "X-Disabled-Secret",
        "X-Missing-Secret",
        "X-Fails-Secret",
        "X-Passes-Secret",
    ] {
        assert!(
            !payload_text.contains(secret),
            "batch response leaked {secret}"
        );
    }

    let current_response = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(current_response.status(), StatusCode::OK);
    let current: Value = serde_json::from_slice(
        &to_bytes(current_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let rows = current["llmConfig"]["rows"].as_array().unwrap();
    let find = |row_id: &str| rows.iter().find(|row| row["id"] == row_id).unwrap();
    assert_eq!(find("row-disabled")["preflight"]["status"], "passed");
    assert_eq!(
        find("row-disabled")["preflight"]["message"],
        "keep old disabled preflight"
    );
    assert_eq!(find("row-missing")["preflight"]["status"], "missing_fields");
    assert_eq!(
        find("row-missing")["preflight"]["reasonCode"],
        "missing_fields"
    );
    assert_eq!(find("row-fails")["preflight"]["status"], "failed");
    assert_eq!(find("row-passes")["preflight"]["status"], "passed");
    assert_eq!(
        current["llmConfig"]["latestPreflightRun"]["attemptedRowIds"],
        json!(["row-fails", "row-passes"])
    );
    assert_eq!(
        current["llmConfig"]["latestPreflightRun"]["winningRowId"],
        Value::Null
    );
    assert!(!current.to_string().contains("sk-passes-secret"));
}

#[tokio::test]
async fn test_llm_accepts_deepseek_reasoning_empty_content_with_finish_reason() {
    let state = AppState::from_config(isolated_test_config("system-config-deepseek-finish-reason"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let base_url = spawn_llm_mock_server(
        r#"{"choices":[{"index":0,"message":{"role":"assistant","content":"","reasoning_content":"ok"},"finish_reason":"stop"}]}"#,
    )
    .await;

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-deepseek-secret",
            "llmModel": "deepseek-v4-pro",
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
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "secretSource": "saved",
                        "model": "deepseek-v4-pro",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"]
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
    assert_eq!(payload["metadata"]["model"], "deepseek-v4-pro");
    assert!(!payload.to_string().contains("sk-deepseek-secret"));

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
        current["llmConfig"]["rows"][0]["preflight"]["status"],
        "passed"
    );
}

#[tokio::test]
async fn test_llm_still_rejects_malformed_openai_response_without_completion_signal() {
    let state = AppState::from_config(isolated_test_config("system-config-malformed-no-signal"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let base_url = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":""}}]}"#).await;

    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-empty-secret",
            "llmModel": "deepseek-v4-pro",
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
                        "secretSource": "saved",
                        "model": "deepseek-v4-pro",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"]
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
    assert_eq!(payload["success"], false);
    assert_eq!(payload["metadata"]["reasonCode"], "invalid_response");
    assert!(payload["message"]
        .as_str()
        .unwrap()
        .contains("没有可确认完成"));
}

#[tokio::test]
async fn test_llm_batch_reports_no_eligible_rows_for_disabled_or_missing_only_config() {
    let state = AppState::from_config(isolated_test_config("system-config-batch-no-eligible"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let save_payload = json!({
        "llmConfig": {
            "schemaVersion": 2,
            "rows": [
                {
                    "id": "row-disabled",
                    "priority": 1,
                    "enabled": false,
                    "provider": "openai_compatible",
                    "baseUrl": "https://disabled.example/v1",
                    "model": "gpt-disabled",
                    "apiKey": "sk-disabled-secret"
                },
                {
                    "id": "row-missing",
                    "priority": 2,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "https://missing.example/v1",
                    "model": "",
                    "apiKey": "sk-missing-secret"
                }
            ],
            "latestPreflightRun": {"runId": null, "checkedAt": null, "attemptedRowIds": [], "winningRowId": null, "winningFingerprint": null},
            "migration": {"status": "not_needed", "message": null, "sourceSchemaVersion": null}
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

    let batch_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm/batch")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(batch_response.status(), StatusCode::OK);
    let payload: Value = serde_json::from_slice(
        &to_bytes(batch_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    assert_eq!(payload["success"], false);
    assert_eq!(payload["reasonCode"], "no_eligible_rows");
    assert_eq!(payload["attemptedRowIds"], json!([]));
    assert_eq!(payload["skippedRowIds"], json!(["row-disabled"]));
    assert_eq!(payload["missingFieldRowIds"], json!(["row-missing"]));
    assert_eq!(payload["failedRowIds"], json!([]));
    assert_eq!(payload["passedRowIds"], json!([]));
}

#[tokio::test]
async fn import_env_requires_token_and_saves_verified_redacted_system_config() {
    let _env_guard = ENV_LOCK.lock().await;
    let mock_base_url =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"import ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-123");
    let _provider = EnvVarGuard::set("LLM_PROVIDER", "openai_compatible");
    let _api_key = EnvVarGuard::set("LLM_API_KEY", "sk-import-secret");
    let _model = EnvVarGuard::set("LLM_MODEL", "gpt-5");
    let _base_url = EnvVarGuard::set("LLM_BASE_URL", &mock_base_url);

    let state = AppState::from_config(isolated_test_config("system-config-import-env"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let missing_token_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(missing_token_response.status(), StatusCode::BAD_REQUEST);

    let import_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-123")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(import_response.status(), StatusCode::OK);
    let import_payload: Value = serde_json::from_slice(
        &to_bytes(import_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(import_payload["success"], true);
    assert_eq!(import_payload["provider"], "openai_compatible");
    assert_eq!(import_payload["hasSavedApiKey"], true);
    assert_eq!(import_payload["secretSource"], "imported");
    assert!(import_payload["metadata"]["fingerprint"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
    assert!(!import_payload.to_string().contains("sk-import-secret"));

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
    assert_eq!(current["llmConfig"]["rows"][0]["apiKey"], "");
    assert_eq!(current["llmConfig"]["rows"][0]["hasApiKey"], true);
    assert_eq!(current["llmConfig"]["rows"][0]["secretSource"], "imported");
    assert_eq!(
        current["llmTestMetadata"]["fingerprint"],
        import_payload["metadata"]["fingerprint"]
    );
    assert!(!current.to_string().contains("sk-import-secret"));
}

#[tokio::test]
async fn import_env_rejects_legacy_provider_aliases() {
    let _env_guard = ENV_LOCK.lock().await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-legacy");
    let _provider = EnvVarGuard::set("LLM_PROVIDER", "openai");
    let _api_key = EnvVarGuard::set("LLM_API_KEY", "sk-legacy-secret");
    let _model = EnvVarGuard::set("LLM_MODEL", "gpt-5");
    let _base_url = EnvVarGuard::set("LLM_BASE_URL", "https://api.openai.com/v1");

    let state = AppState::from_config(isolated_test_config("system-config-import-legacy"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-legacy")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(payload.to_string().contains("openai_compatible"));
    assert!(!payload.to_string().contains("sk-legacy-secret"));
}

#[tokio::test]
async fn import_env_bare_keys_auto_promotes_to_single_row() {
    // T2 contract: bare LLM_* keys (no numbered prefix) auto-promote to LLM_1_*,
    // producing a single-row envelope. Response has winningRowId == row1.id and
    // rows.len() == 1. (Replaces the v1 baseline test that asserted these fields
    // were ABSENT.)
    let _env_guard = ENV_LOCK.lock().await;
    let mock_base_url =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"baseline ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-baseline");
    let _provider = EnvVarGuard::set("LLM_PROVIDER", "openai_compatible");
    let _api_key = EnvVarGuard::set("LLM_API_KEY", "sk-baseline-secret");
    let _model = EnvVarGuard::set("LLM_MODEL", "gpt-5-baseline");
    let _base_url = EnvVarGuard::set("LLM_BASE_URL", &mock_base_url);
    let _llm_1_unset = EnvVarGuard::remove("LLM_1_PROVIDER");

    let state = AppState::from_config(isolated_test_config("system-config-import-baseline"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let import_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-baseline")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(import_response.status(), StatusCode::OK);
    let import_payload: Value = serde_json::from_slice(
        &to_bytes(import_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    // Top-level fields still populated for the (single) winning row.
    assert_eq!(import_payload["success"], true);
    assert_eq!(import_payload["provider"], "openai_compatible");
    assert_eq!(import_payload["model"], "gpt-5-baseline");
    assert_eq!(import_payload["baseUrl"], mock_base_url);
    assert_eq!(import_payload["hasSavedApiKey"], true);
    assert_eq!(import_payload["secretSource"], "imported");
    // T2 contract: winningRowId is set and rows[] has exactly 1 entry, both passing.
    assert!(
        import_payload["winningRowId"].is_string(),
        "expected winningRowId to be a string, got {:?}",
        import_payload["winningRowId"]
    );
    let rows = import_payload["rows"].as_array().expect("rows[] present");
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["preflight"], "passed");
    assert_eq!(rows[0]["index"], 0);
    assert_eq!(rows[0]["id"], import_payload["winningRowId"]);
    assert!(rows[0]["fingerprint"]
        .as_str()
        .unwrap_or_default()
        .starts_with("sha256:"));
    assert!(!import_payload.to_string().contains("sk-baseline-secret"));
}

// ---------------------------------------------------------------------------
// T2: Multi-row import-env tests
// All tests below MUST use ENV_LOCK + EnvVarGuard to prevent races (AC19).
// ---------------------------------------------------------------------------

/// Helper that clears every LLM_*/AGENT_TIMEOUT env var our import path reads, so a
/// later test's leftover state cannot pollute a subsequent test running serially
/// (the guards drop in scope but `EnvVarGuard::set` to a sibling key leaves N+1
/// keys alive, so we explicitly remove them here for hygiene).
fn unset_all_import_env_vars() -> Vec<EnvVarGuard> {
    let mut guards = Vec::new();
    for key in [
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_TIMEOUT",
        "LLM_TEMPERATURE",
        "LLM_MAX_TOKENS",
        "LLM_FIRST_TOKEN_TIMEOUT",
        "LLM_STREAM_TIMEOUT",
        "LLM_CUSTOM_HEADERS",
        "AGENT_TIMEOUT",
        "AGENT_TIMEOUT_SECONDS",
    ] {
        guards.push(EnvVarGuard::remove(key));
    }
    for n in 1..=5 {
        for suffix in [
            "PROVIDER",
            "API_KEY",
            "MODEL",
            "BASE_URL",
            "TIMEOUT",
            "TEMPERATURE",
            "MAX_TOKENS",
            "FIRST_TOKEN_TIMEOUT",
            "STREAM_TIMEOUT",
            "CUSTOM_HEADERS",
            "AGENT_TIMEOUT",
        ] {
            guards.push(EnvVarGuard::remove(&format!("LLM_{n}_{suffix}")));
        }
    }
    guards
}

#[tokio::test]
async fn import_env_two_numbered_configs_first_passes() {
    // AC1: LLM_1_* + LLM_2_* both reachable -> first-pass-wins, both rows persisted
    // with preflight=passed/untested depending on whether the loop short-circuits.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let mock_base_url_1 =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"row1 ok"}}]}"#).await;
    let mock_base_url_2 =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"row2 ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-multi-1");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-5-row1");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &mock_base_url_1);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-row-2-secret");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-5-row2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &mock_base_url_2);

    let state = AppState::from_config(isolated_test_config("system-config-import-two-numbered"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-multi-1")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    assert!(payload["winningRowId"].is_string());
    // First-pass-wins: only row 1 is attempted.
    let rows = payload["rows"].as_array().expect("rows[] present");
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["preflight"], "passed");
    assert_eq!(rows[0]["index"], 0);
    // Winning row's fields mirror at top level.
    assert_eq!(payload["model"], "gpt-5-row1");
    assert_eq!(payload["baseUrl"], mock_base_url_1);

    // The DB envelope retains both rows (the second carries untested preflight).
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
    let saved_rows = current["llmConfig"]["rows"]
        .as_array()
        .expect("saved rows");
    assert_eq!(saved_rows.len(), 2);
    assert_eq!(saved_rows[0]["model"], "gpt-5-row1");
    assert_eq!(saved_rows[1]["model"], "gpt-5-row2");
    assert_eq!(saved_rows[0]["preflight"]["status"], "passed");
    assert_eq!(saved_rows[1]["preflight"]["status"], "untested");
    assert!(!current.to_string().contains("sk-row-1-secret"));
    assert!(!current.to_string().contains("sk-row-2-secret"));
}

#[tokio::test]
async fn import_env_numbered_wins_over_bare_silently_drops_bare() {
    // AC18: when both bare LLM_* and LLM_1_* present, numbered wins; bare silently dropped.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let bare_mock = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"bare"}}]}"#).await;
    let numbered_mock =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"numbered"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-precedence");
    // bare
    let _bare_provider = EnvVarGuard::set("LLM_PROVIDER", "openai_compatible");
    let _bare_api_key = EnvVarGuard::set("LLM_API_KEY", "sk-bare-secret");
    let _bare_model = EnvVarGuard::set("LLM_MODEL", "gpt-bare");
    let _bare_base = EnvVarGuard::set("LLM_BASE_URL", &bare_mock);
    // numbered
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-numbered-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-numbered");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &numbered_mock);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-precedence"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-precedence")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["model"], "gpt-numbered");
    assert_eq!(payload["baseUrl"], numbered_mock);
    let rows = payload["rows"].as_array().expect("rows[] present");
    assert_eq!(rows.len(), 1, "only the numbered row should be produced");
    assert!(!payload.to_string().contains("sk-bare-secret"));
    assert!(!payload.to_string().contains("sk-numbered-secret"));
}

#[tokio::test]
async fn import_env_per_row_optional_defaults_applied() {
    // Per-row LLM_N_TIMEOUT / LLM_N_TEMPERATURE / LLM_N_MAX_TOKENS land in the row's
    // advanced block. (sanity check covering the per-row read paths.)
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let mock = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-defaults");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-defaults-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-defaults");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &mock);
    let _llm_1_timeout = EnvVarGuard::set("LLM_1_TIMEOUT", "77");
    let _llm_1_temp = EnvVarGuard::set("LLM_1_TEMPERATURE", "0.25");
    let _llm_1_max_tokens = EnvVarGuard::set("LLM_1_MAX_TOKENS", "8192");

    let state = AppState::from_config(isolated_test_config("system-config-import-defaults"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-defaults")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

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
    let advanced = &current["llmConfig"]["rows"][0]["advanced"];
    // 77 seconds * 1000 = 77000 ms (the import path multiplies LLM_TIMEOUT into ms).
    assert_eq!(advanced["llmTimeout"], 77000);
    assert!(
        (advanced["llmTemperature"].as_f64().unwrap_or(-1.0) - 0.25).abs() < 1e-6,
        "expected llmTemperature 0.25, got {:?}",
        advanced["llmTemperature"]
    );
    assert_eq!(advanced["llmMaxTokens"], 8192);
}

#[tokio::test]
async fn import_env_agent_timeout_global_llm_n_agent_timeout_dropped() {
    // AC17: top-level AGENT_TIMEOUT applies globally; per-row LLM_N_AGENT_TIMEOUT is dropped.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let mock = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-agent-timeout");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-agent-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-agent");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &mock);
    let _llm_1_agent_timeout = EnvVarGuard::set("LLM_1_AGENT_TIMEOUT", "999");
    let _agent_timeout = EnvVarGuard::set("AGENT_TIMEOUT", "1800");

    let state = AppState::from_config(isolated_test_config("system-config-import-agent-tmo"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-agent-timeout")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let current = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_json: Value =
        serde_json::from_slice(&to_bytes(current.into_body(), usize::MAX).await.unwrap()).unwrap();
    let advanced = &current_json["llmConfig"]["rows"][0]["advanced"];
    assert_eq!(advanced["agentTimeout"], 1800);
    // 999 must NOT leak into agentTimeout.
    assert_ne!(advanced["agentTimeout"], 999);
}

#[tokio::test]
async fn import_env_codeql_and_fallback_tier_vars_ignored() {
    // AC14: CODEQL_LLM_* and FALLBACK_LLM_* env vars are silently ignored by import.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let mock = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-dead-tier");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-dead-tier-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-dead-tier");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &mock);
    // Dead tier vars set with bogus values; they must be ignored.
    let _codeql_provider =
        EnvVarGuard::set("CODEQL_LLM_PROVIDER", "should_be_ignored_provider");
    let _codeql_api_key = EnvVarGuard::set("CODEQL_LLM_API_KEY", "sk-codeql-leak");
    let _codeql_model = EnvVarGuard::set("CODEQL_LLM_MODEL", "codeql-ghost-model");
    let _codeql_base = EnvVarGuard::set("CODEQL_LLM_BASE_URL", "https://codeql.ghost/v1");
    let _codeql_timeout = EnvVarGuard::set("CODEQL_LLM_TIMEOUT", "9999");
    let _codeql_temp = EnvVarGuard::set("CODEQL_LLM_TEMPERATURE", "9.9");
    let _codeql_max = EnvVarGuard::set("CODEQL_LLM_MAX_TOKENS", "999999");
    let _fb_provider = EnvVarGuard::set("FALLBACK_LLM_PROVIDER", "fallback_ghost");
    let _fb_api_key = EnvVarGuard::set("FALLBACK_LLM_API_KEY", "sk-fallback-leak");
    let _fb_model = EnvVarGuard::set("FALLBACK_LLM_MODEL", "fallback-ghost-model");
    let _fb_base = EnvVarGuard::set("FALLBACK_LLM_BASE_URL", "https://fallback.ghost/v1");
    let _fb_timeout = EnvVarGuard::set("FALLBACK_LLM_TIMEOUT", "8888");
    let _fb_temp = EnvVarGuard::set("FALLBACK_LLM_TEMPERATURE", "8.8");
    let _fb_max = EnvVarGuard::set("FALLBACK_LLM_MAX_TOKENS", "888888");

    let state = AppState::from_config(isolated_test_config("system-config-import-dead-tier"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-dead-tier")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    let rows = payload["rows"].as_array().expect("rows[] present");
    assert_eq!(rows.len(), 1, "only the LLM_1_* row should be produced");
    let current = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_json: Value =
        serde_json::from_slice(&to_bytes(current.into_body(), usize::MAX).await.unwrap()).unwrap();
    let saved_rows = current_json["llmConfig"]["rows"].as_array().expect("rows");
    assert_eq!(saved_rows.len(), 1);
    assert_eq!(saved_rows[0]["model"], "gpt-dead-tier");
    let text = current_json.to_string();
    assert!(!text.contains("codeql-ghost-model"));
    assert!(!text.contains("fallback-ghost-model"));
    assert!(!text.contains("sk-codeql-leak"));
    assert!(!text.contains("sk-fallback-leak"));
}

#[tokio::test]
async fn codeql_llm_allow_source_snippets_loads_from_env() {
    let _lock = ENV_LOCK.lock().await;
    let _guard = EnvVarGuard::set("CODEQL_LLM_ALLOW_SOURCE_SNIPPETS", "false");
    let config = AppConfig::from_env().expect("config load");
    assert_eq!(
        config.codeql_llm_allow_source_snippets,
        false,
        "CODEQL_LLM_ALLOW_SOURCE_SNIPPETS=false should propagate through AppConfig::from_env"
    );
}

#[tokio::test]
async fn import_env_placeholder_rejected_per_row() {
    // Each row independently rejects the REDACTED_SECRET_PLACEHOLDER; the error message
    // names the offending LLM_N_API_KEY key.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-placeholder");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1-good");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-good");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", "https://row-1.example/v1");
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    // Use the placeholder string LITERALLY (matches REDACTED_SECRET_PLACEHOLDER).
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "***configured***");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-row-2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", "https://row-2.example/v1");

    let state =
        AppState::from_config(isolated_test_config("system-config-import-placeholder"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-placeholder")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(payload.to_string().contains("LLM_2_API_KEY"));
}

#[tokio::test]
async fn import_env_winning_row_id_some_mirrors_winner() {
    // AC16 happy path: winningRowId is set and top-level provider/model/baseUrl
    // mirror the winning row's values (row 2 in this test).
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    // Row 1: 404 -> model_unavailable (fallback-eligible); row 2: passes.
    let listener_1 = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr_1 = listener_1.local_addr().unwrap();
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener_1.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let _ = stream.read(&mut buffer).await;
                let body = r#"{"error":"model not found"}"#;
                let response = format!(
                    "HTTP/1.1 404 Not Found\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    let row_1_base = format!("http://{addr_1}/v1");
    let row_2_base =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"row2 wins"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-winner-some");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1-secret");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-row-1");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &row_1_base);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-row-2-secret");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-row-2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &row_2_base);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-winner-some"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-winner-some")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    assert!(payload["winningRowId"].is_string());
    assert_eq!(payload["model"], "gpt-row-2");
    assert_eq!(payload["baseUrl"], row_2_base);
    let rows = payload["rows"].as_array().expect("rows[]");
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["preflight"], "failed");
    assert_eq!(rows[0]["reasonCode"], "model_unavailable");
    assert_eq!(rows[1]["preflight"], "passed");
    assert_eq!(rows[1]["id"], payload["winningRowId"]);
}

#[tokio::test]
async fn import_env_all_rows_fail_winning_row_id_none_mirrors_row_1() {
    // AC16 + AC4: all rows fail (fallback-eligible) -> winningRowId=null,
    // top-level mirrors row 1, noActiveConfig=true in metadata. All rows persisted.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    // Two 404 servers (both fallback-eligible model_unavailable).
    async fn spawn_404() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                let Ok((mut stream, _)) = listener.accept().await else {
                    break;
                };
                tokio::spawn(async move {
                    let mut buffer = [0_u8; 4096];
                    let _ = stream.read(&mut buffer).await;
                    let body = r#"{"error":"model not found"}"#;
                    let response = format!(
                        "HTTP/1.1 404 Not Found\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                    let _ = stream.write_all(response.as_bytes()).await;
                });
            }
        });
        format!("http://{addr}/v1")
    }
    let row_1_base = spawn_404().await;
    let row_2_base = spawn_404().await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-all-fail");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-row-1-fail");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &row_1_base);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-row-2");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-row-2-fail");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &row_2_base);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-all-fail"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-all-fail")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], false);
    assert!(payload["winningRowId"].is_null());
    // top-level mirrors row 1
    assert_eq!(payload["model"], "gpt-row-1-fail");
    assert_eq!(payload["baseUrl"], row_1_base);
    assert_eq!(payload["metadata"]["noActiveConfig"], true);
    let rows = payload["rows"].as_array().expect("rows[]");
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["preflight"], "failed");
    assert_eq!(rows[1]["preflight"], "failed");

    // Both rows persisted in the DB with preflight=failed.
    let current = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_json: Value =
        serde_json::from_slice(&to_bytes(current.into_body(), usize::MAX).await.unwrap()).unwrap();
    let saved_rows = current_json["llmConfig"]["rows"].as_array().expect("rows");
    assert_eq!(saved_rows.len(), 2);
    assert_eq!(saved_rows[0]["preflight"]["status"], "failed");
    assert_eq!(saved_rows[1]["preflight"]["status"], "failed");
    assert!(current_json["llmConfig"]["latestPreflightRun"]["winningRowId"].is_null());
}

/// Helper: spawn a mock server that ALWAYS replies HTTP 429 (rate-limited / quota).
/// Triggers `QuotaRateLimit` in `classify_fallback`, which is a break-class category.
async fn spawn_llm_mock_429() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind 429 mock");
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let _ = stream.read(&mut buffer).await;
                let body = r#"{"error":"rate limit quota exceeded 429"}"#;
                let response = format!(
                    "HTTP/1.1 429 Too Many Requests\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    format!("http://{addr}/v1")
}

#[tokio::test]
async fn import_env_break_class_halt_remaining_rows_untested() {
    // AC11: a break-class error on row 1 halts iteration; row 2 retains preflight=untested.
    // We trigger QuotaRateLimit (break-class, NOT fallback-eligible) via HTTP 429.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let row_1_base = spawn_llm_mock_429().await;
    let row_2_base = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-break");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-row-1");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &row_1_base);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-row-2");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-row-2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &row_2_base);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-break-halt"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-break")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], false);
    assert!(payload["winningRowId"].is_null());
    let rows = payload["rows"].as_array().expect("rows[]");
    // Only row 1 was attempted (per_row_results only contains attempted rows).
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["preflight"], "failed");
    assert_eq!(rows[0]["reasonCode"], "quota_rate_limit");

    // Row 2 in the DB envelope retains preflight=untested (never attempted).
    let current = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_json: Value =
        serde_json::from_slice(&to_bytes(current.into_body(), usize::MAX).await.unwrap()).unwrap();
    let saved_rows = current_json["llmConfig"]["rows"].as_array().expect("rows");
    assert_eq!(saved_rows.len(), 2);
    assert_eq!(saved_rows[0]["preflight"]["status"], "failed");
    assert_eq!(saved_rows[1]["preflight"]["status"], "untested");
}

#[tokio::test]
async fn import_env_break_class_halt_emits_single_log_line() {
    // AC11: when a break-class halt occurs, exactly one log line is emitted.
    // We can't easily intercept tracing from this test harness, so we instead
    // assert behavioural coupling: per_row_results.len() < total rows in the DB.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    let row_1_base = spawn_llm_mock_429().await;
    let row_2_base = spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"ok"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-break-log");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-row-1");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-row-1");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &row_1_base);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-row-2");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-row-2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &row_2_base);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-break-log"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-break-log")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    // success=false because the break halted before any row passed.
    assert_eq!(payload["success"], false);
    // Exactly one entry in rows[] — row 2 was never attempted.
    let rows = payload["rows"].as_array().expect("rows[]");
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["index"], 0);
}

#[tokio::test]
async fn import_env_fallback_eligible_continues_through_chain() {
    // AC11 continue branch: each fallback-eligible failure advances to the next row.
    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();
    async fn spawn_404() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                let Ok((mut stream, _)) = listener.accept().await else {
                    break;
                };
                tokio::spawn(async move {
                    let mut buffer = [0_u8; 4096];
                    let _ = stream.read(&mut buffer).await;
                    let body = r#"{"error":"model not found"}"#;
                    let response = format!(
                        "HTTP/1.1 404 Not Found\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                    let _ = stream.write_all(response.as_bytes()).await;
                });
            }
        });
        format!("http://{addr}/v1")
    }
    let row_1_base = spawn_404().await;
    let row_2_base = spawn_404().await;
    let row_3_base =
        spawn_llm_mock_server(r#"{"choices":[{"message":{"content":"row3 wins"}}]}"#).await;
    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-continue");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-c1");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-c1");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &row_1_base);
    let _llm_2_provider = EnvVarGuard::set("LLM_2_PROVIDER", "openai_compatible");
    let _llm_2_api_key = EnvVarGuard::set("LLM_2_API_KEY", "sk-c2");
    let _llm_2_model = EnvVarGuard::set("LLM_2_MODEL", "gpt-c2");
    let _llm_2_base = EnvVarGuard::set("LLM_2_BASE_URL", &row_2_base);
    let _llm_3_provider = EnvVarGuard::set("LLM_3_PROVIDER", "openai_compatible");
    let _llm_3_api_key = EnvVarGuard::set("LLM_3_API_KEY", "sk-c3");
    let _llm_3_model = EnvVarGuard::set("LLM_3_MODEL", "gpt-c3");
    let _llm_3_base = EnvVarGuard::set("LLM_3_BASE_URL", &row_3_base);

    let state =
        AppState::from_config(isolated_test_config("system-config-import-continue"))
            .await
            .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-continue")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["success"], true);
    assert!(payload["winningRowId"].is_string());
    assert_eq!(payload["model"], "gpt-c3");
    let rows = payload["rows"].as_array().expect("rows[]");
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0]["preflight"], "failed");
    assert_eq!(rows[1]["preflight"], "failed");
    assert_eq!(rows[2]["preflight"], "passed");
    assert_eq!(rows[2]["id"], payload["winningRowId"]);
}

#[tokio::test]
async fn test_llm_rejects_empty_text_response() {
    let state = AppState::from_config(isolated_test_config("system-config-real-test-empty"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
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
    assert!(payload["message"]
        .as_str()
        .unwrap()
        .contains("没有可确认完成"));
}

#[tokio::test]
async fn system_config_llm_provider_catalog_matches_rust_registry_semantics() {
    let state = AppState::from_config(isolated_test_config("system-config-provider-catalog"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

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
async fn system_config_save_allows_empty_model_but_preflight_stays_strict() {
    let state = AppState::from_config(isolated_test_config("system-config-empty-model-save"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "llmConfig": {
                            "llmProvider": "openai_compatible",
                            "llmApiKey": "sk-empty-model",
                            "llmModel": "",
                            "llmBaseUrl": "https://gateway.example/v1",
                            "llmCustomHeaders": {"X-Trace": "saved"}
                        },
                        "otherConfig": {"llmConcurrency": 2, "llmGapMs": 5}
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let save_payload: Value = serde_json::from_slice(
        &to_bytes(save_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(save_payload["llmConfig"]["rows"][0]["model"], "");
    assert_eq!(save_payload["llmConfig"]["rows"][0]["hasApiKey"], true);
    assert!(!save_payload.to_string().contains("sk-empty-model"));

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
    let preflight_payload: Value = serde_json::from_slice(
        &to_bytes(preflight_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(preflight_payload["ok"], false);
    assert_eq!(preflight_payload["reasonCode"], "missing_fields");
    assert_eq!(
        preflight_payload["missingFields"],
        Value::Array(vec![Value::String("llmModel".to_string())])
    );
    assert_eq!(preflight_payload["savedConfig"]["hasSavedApiKey"], true);
}

#[tokio::test]
async fn fetch_llm_models_uses_draft_request_for_online_discovery_without_persisting_secrets() {
    let state = AppState::from_config(isolated_test_config("system-config-fetch-models-draft"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let mock_base_url =
        spawn_llm_mock_server(r#"{"data":[{"id":"z-draft-model"},{"id":"a-draft-model"}]}"#).await;

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/fetch-llm-models")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-unsaved-draft-models",
                        "baseUrl": mock_base_url,
                        "customHeaders": {"X-Draft-Secret": "draft-header-secret"},
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
    let payload_text = payload.to_string();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["source"], "online");
    assert_eq!(payload["resolvedProvider"], "openai_compatible");
    assert_eq!(payload["baseUrlUsed"], mock_base_url);
    assert_eq!(payload["defaultModel"], "a-draft-model");
    assert!(payload["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "z-draft-model"));
    assert!(!payload_text.contains("sk-unsaved-draft-models"));
    assert!(!payload_text.contains("draft-header-secret"));
    assert!(!payload_text.contains("X-Draft-Secret"));

    let current_response = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(current_response.status(), StatusCode::OK);
    let current_payload: Value = serde_json::from_slice(
        &to_bytes(current_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let current_text = current_payload.to_string();
    assert!(!current_text.contains("sk-unsaved-draft-models"));
    assert!(!current_text.contains("draft-header-secret"));
}

#[tokio::test]
async fn fetch_llm_models_saved_path_omits_draft_key_but_draft_base_url_takes_precedence() {
    let state = AppState::from_config(isolated_test_config("system-config-fetch-models-saved"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let saved_base_url = spawn_llm_mock_server(r#"{"data":[{"id":"saved-model"}]}"#).await;
    let draft_base_url = spawn_llm_mock_server(r#"{"data":[{"id":"draft-base-model"}]}"#).await;

    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "llmConfig": {
                            "llmProvider": "openai_compatible",
                            "llmApiKey": "sk-saved-fetch-models",
                            "llmModel": "",
                            "llmBaseUrl": saved_base_url,
                            "llmCustomHeaders": {"X-Trace": "saved"}
                        },
                        "otherConfig": {}
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/fetch-llm-models")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "baseUrl": draft_base_url,
                        "customHeaders": {"X-Draft-Trace": "draft-value"}
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
    let payload_text = payload.to_string();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["source"], "online");
    assert_eq!(payload["baseUrlUsed"], draft_base_url);
    assert!(payload["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "draft-base-model"));
    assert!(!payload_text.contains("sk-saved-fetch-models"));
    assert!(!payload_text.contains("draft-value"));
    assert!(!payload_text.contains("X-Draft-Trace"));

    let current_response = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_payload: Value = serde_json::from_slice(
        &to_bytes(current_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        current_payload["llmConfig"]["rows"][0]["baseUrl"],
        saved_base_url
    );
    assert_ne!(
        current_payload["llmConfig"]["rows"][0]["baseUrl"],
        draft_base_url
    );
}

#[tokio::test]
async fn fetch_llm_models_failure_falls_back_to_static_catalog_without_secret_echo() {
    let state = AppState::from_config(isolated_test_config("system-config-fetch-models-fallback"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/fetch-llm-models")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-unsaved-openai",
                        "baseUrl": "http://127.0.0.1:9/v1",
                        "customHeaders": {"X-Fallback-Secret": "fallback-header-secret"},
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
    let payload_text = payload.to_string();
    assert_eq!(payload["success"], true);
    assert_eq!(payload["source"], "fallback_static");
    assert_eq!(payload["resolvedProvider"], "openai_compatible");
    assert_eq!(payload["baseUrlUsed"], "http://127.0.0.1:9/v1");
    assert!(payload["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "gpt-5"));
    assert!(!payload_text.contains("sk-unsaved-openai"));
    assert!(!payload_text.contains("fallback-header-secret"));
    assert!(!payload_text.contains("X-Fallback-Secret"));
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
    let app = build_router(state, ShutdownGate::default());

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
    assert_eq!(payload["llmConfig"]["schemaVersion"], 2);
    assert_eq!(
        payload["llmConfig"]["rows"][0]["provider"],
        "openai_compatible"
    );
    assert_eq!(payload["llmConfig"]["rows"][0]["model"], "gemini-2.5-pro");
    assert_eq!(
        payload["llmConfig"]["rows"][0]["baseUrl"],
        "https://example.test/v1"
    );
    assert_eq!(
        payload["llmConfig"]["rows"][0]["advanced"]["llmTimeout"],
        123000
    );
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

#[tokio::test]
async fn system_config_multi_row_contract_redacts_and_preserves_row_secret() {
    let state = AppState::from_config(isolated_test_config("system-config-multi-row-contract"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());

    let save_payload = json!({
        "llmConfig": {
            "schemaVersion": 2,
            "rows": [
                {
                    "id": "row-a",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "https://api.example.com/v1",
                    "model": "gpt-5",
                    "apiKey": "sk-row-a",
                    "advanced": {"llmTimeout": 120000, "llmTemperature": 0.1, "llmMaxTokens": 16, "llmFirstTokenTimeout": 180, "llmStreamTimeout": 600, "agentTimeout": 600, "subAgentTimeout": 300, "toolTimeout": 120, "llmCustomHeaders": ""}
                },
                {
                    "id": "row-b",
                    "priority": 2,
                    "enabled": false,
                    "provider": "anthropic_compatible",
                    "baseUrl": "https://api.anthropic.com/v1",
                    "model": "claude-sonnet-4.5",
                    "apiKey": "sk-row-b",
                    "advanced": {"llmTimeout": 120000, "llmTemperature": 0.1, "llmMaxTokens": 16, "llmFirstTokenTimeout": 180, "llmStreamTimeout": 600, "agentTimeout": 600, "subAgentTimeout": 300, "toolTimeout": 120, "llmCustomHeaders": ""}
                }
            ]
        },
        "otherConfig": {"llmConcurrency": 3, "llmGapMs": 1500, "maxAnalyzeFiles": 7}
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
    let saved: Value = serde_json::from_slice(
        &to_bytes(save_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(saved["llmConfig"]["schemaVersion"], 2);
    assert_eq!(saved["llmConfig"]["rows"][0]["apiKey"], "");
    assert_eq!(saved["llmConfig"]["rows"][0]["hasApiKey"], true);
    assert!(!saved.to_string().contains("sk-row-a"));

    let preserve_payload = json!({
        "llmConfig": {
            "schemaVersion": 2,
            "rows": [
                {"id":"row-b","priority":1,"enabled":false,"provider":"anthropic_compatible","baseUrl":"https://api.anthropic.com/v1","model":"claude-sonnet-4.5","apiKey":"","advanced":{"llmTimeout":120000,"llmTemperature":0.1,"llmMaxTokens":16,"llmFirstTokenTimeout":180,"llmStreamTimeout":600,"agentTimeout":600,"subAgentTimeout":300,"toolTimeout":120,"llmCustomHeaders":""}},
                {"id":"row-a","priority":2,"enabled":true,"provider":"openai_compatible","baseUrl":"https://api.example.com/v1","model":"gpt-5-mini","apiKey":"","advanced":{"llmTimeout":120000,"llmTemperature":0.1,"llmMaxTokens":16,"llmFirstTokenTimeout":180,"llmStreamTimeout":600,"agentTimeout":600,"subAgentTimeout":300,"toolTimeout":120,"llmCustomHeaders":""}}
            ]
        },
        "otherConfig": {}
    });
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(preserve_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let current = app
        .oneshot(
            Request::get("/api/v1/system-config")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let current_json: Value =
        serde_json::from_slice(&to_bytes(current.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(current_json["llmConfig"]["rows"][0]["id"], "row-b");
    assert_eq!(current_json["llmConfig"]["rows"][1]["id"], "row-a");
    assert_eq!(current_json["llmConfig"]["rows"][1]["hasApiKey"], true);
    assert!(!current_json.to_string().contains("sk-row-a"));
    assert!(!current_json.to_string().contains("sk-row-b"));
}

#[tokio::test]
async fn import_env_redacts_api_key_from_error_message() {
    // Fix 6: error messages that echo the API key must be redacted before persisting.
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    let _env_guard = ENV_LOCK.lock().await;
    let _clear = unset_all_import_env_vars();

    // Spawn a mock server that returns 401 with the API key echoed in the body.
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let _ = stream.read(&mut buffer).await;
                // Body intentionally echoes the raw API key to simulate a leaky upstream.
                let body = r#"{"error":"Unauthorized: sk-secret-key-leaks-here-1234567890abcdef is invalid"}"#;
                let response = format!(
                    "HTTP/1.1 401 Unauthorized\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    let base_url = format!("http://{addr}/v1");

    let _token = EnvVarGuard::set("ARGUS_RESET_IMPORT_TOKEN", "token-redact");
    let _llm_1_provider = EnvVarGuard::set("LLM_1_PROVIDER", "openai_compatible");
    let _llm_1_api_key = EnvVarGuard::set("LLM_1_API_KEY", "sk-secret-key-leaks-here-1234567890abcdef");
    let _llm_1_model = EnvVarGuard::set("LLM_1_MODEL", "gpt-redact-test");
    let _llm_1_base = EnvVarGuard::set("LLM_1_BASE_URL", &base_url);

    let state = AppState::from_config(isolated_test_config("system-config-import-redact"))
        .await
        .expect("state should build");
    let app = build_router(state, ShutdownGate::default());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/import-env")
                .header("x-argus-reset-import-token", "token-redact")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    let body_bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let payload: Value = serde_json::from_slice(&body_bytes).unwrap();
    let body_str = payload.to_string();

    // The raw API key must never appear in the response (security property).
    assert!(
        !body_str.contains("sk-secret-key-leaks-here-1234567890abcdef"),
        "raw API key must not appear in response; got: {body_str}"
    );
    // The response must indicate failure with auth reason.
    assert_eq!(payload["success"], false, "401 must produce success=false");
    assert_eq!(payload["reasonCode"], "auth", "401 must map to auth reason");
}
