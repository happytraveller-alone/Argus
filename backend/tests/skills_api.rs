use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

#[tokio::test]
async fn skills_catalog_and_prompt_skill_crud_are_rust_owned() {
    let config = isolated_test_config("skills-api");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let catalog_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=200")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(catalog_response.status(), StatusCode::OK);
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(catalog_json["items"].as_array().unwrap().len() >= 1);

    let prompt_list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/prompt-skills")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(prompt_list_response.status(), StatusCode::OK);
    let prompt_list_json: Value = serde_json::from_slice(
        &to_bytes(prompt_list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(prompt_list_json["builtin_items"].as_array().unwrap().len() >= 1);

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/skills/prompt-skills")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Custom Prompt",
                        "content": "focus on evidence",
                        "scope": "global",
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let prompt_skill_id = create_json["id"].as_str().unwrap().to_string();

    let update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri(format!("/api/v1/skills/prompt-skills/{prompt_skill_id}"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Custom Prompt Updated",
                        "content": "focus on stronger evidence",
                        "scope": "agent_specific",
                        "agent_key": "analysis",
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(update_response.status(), StatusCode::OK);

    let builtin_update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/skills/prompt-skills/builtin/analysis")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "is_active": false
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(builtin_update_response.status(), StatusCode::OK);

    let resource_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/skills/resources/prompt-custom/{prompt_skill_id}"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resource_response.status(), StatusCode::OK);
    let resource_json: Value = serde_json::from_slice(
        &to_bytes(resource_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(resource_json["tool_type"], "prompt-custom");

    let delete_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri(format!("/api/v1/skills/prompt-skills/{prompt_skill_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(delete_response.status(), StatusCode::OK);
}

#[tokio::test]
async fn skill_detail_and_test_streams_are_available() {
    let config = isolated_test_config("skills-stream");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let catalog_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=20")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let skill_id = catalog_json["items"][0]["skill_id"]
        .as_str()
        .unwrap()
        .to_string();

    let detail_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/skills/{skill_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(detail_response.status(), StatusCode::OK);

    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/skills/{skill_id}/test"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "prompt": "run a smoke test",
                        "max_iterations": 2
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);
    assert_eq!(test_response.headers()["content-type"], "text/event-stream");
    let test_body = String::from_utf8(
        to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    assert!(test_body.contains("\"type\":\"result\""));

    let tool_test_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/skills/{skill_id}/tool-test"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_name": "libplist",
                        "file_path": "src/a.c",
                        "function_name": "main",
                        "line_start": 1,
                        "line_end": 2,
                        "tool_input": {"mode": "smoke"}
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(tool_test_response.status(), StatusCode::OK);
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}
