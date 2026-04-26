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
        &ordered_ids[..7],
        &[
            "custom",
            "openai",
            "openrouter",
            "anthropic",
            "azure_openai",
            "moonshot",
            "ollama",
        ]
    );

    let gemini = providers
        .iter()
        .find(|item| item["id"] == "gemini")
        .expect("gemini provider should exist");
    assert_eq!(gemini["defaultModel"], "gemini-3-pro");
    assert!(gemini["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "veo-3.1"));

    let baidu = providers
        .iter()
        .find(|item| item["id"] == "baidu")
        .expect("baidu provider should exist");
    assert_eq!(baidu["fetchStyle"], "native_static");
    assert_eq!(baidu["supportsModelFetch"], false);

    let custom = providers
        .iter()
        .find(|item| item["id"] == "custom")
        .expect("custom provider should exist");
    assert_eq!(custom["defaultBaseUrl"], "");
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
    assert_eq!(payload["resolvedProvider"], "custom");
    assert_eq!(payload["defaultModel"], "gpt-5");
    assert_eq!(payload["baseUrlUsed"], "https://gateway.example/v1");
    assert!(payload["models"]
        .as_array()
        .unwrap()
        .iter()
        .any(|model| model == "gpt-5.1-codex-max"));
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
                        "provider": "openai",
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
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}
