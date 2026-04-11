use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

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
            "llmProvider": "openai",
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
async fn system_config_helper_endpoints_are_available() {
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
    assert!(providers_json["providers"].as_array().unwrap().len() >= 3);

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
    assert_eq!(payload["llmConfig"]["llmProvider"], "gemini");
    assert_eq!(payload["llmConfig"]["llmModel"], "gemini-2.5-pro");
    assert_eq!(
        payload["llmConfig"]["llmBaseUrl"],
        "https://example.test/v1"
    );
    assert_eq!(payload["llmConfig"]["llmTimeout"], 123000);
    assert_eq!(payload["llmConfig"]["geminiApiKey"], "gemini-default-key");
    assert_eq!(payload["otherConfig"]["maxAnalyzeFiles"], 88);
    assert_eq!(payload["otherConfig"]["llmConcurrency"], 5);
    assert_eq!(payload["otherConfig"]["llmGapMs"], 2222);
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}
