use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

#[tokio::test]
async fn search_endpoints_are_rust_owned_and_return_project_matches() {
    let config = isolated_test_config("search-api");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_payload = json!({
        "name": "search-demo-project",
        "description": "keyword-codex-search",
        "source_type": "zip",
        "default_branch": "main",
        "programming_languages": []
    });

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects")
                .header("content-type", "application/json")
                .body(Body::from(create_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);

    let global_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/search?keyword=codex")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(global_response.status(), StatusCode::OK);
    let global_json: Value = serde_json::from_slice(
        &to_bytes(global_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(global_json["keyword"], "codex");
    assert!(global_json["projects"].as_array().unwrap().len() >= 1);
    assert!(global_json["total"]["projects_total"].as_i64().unwrap() >= 1);

    let project_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/projects/search?keyword=search-demo")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(project_response.status(), StatusCode::OK);
    let project_json: Value = serde_json::from_slice(
        &to_bytes(project_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(project_json["total"].as_i64().unwrap(), 1);
    assert_eq!(project_json["data"].as_array().unwrap().len(), 1);

    let task_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/tasks/search?keyword=anything")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(task_response.status(), StatusCode::OK);
    let task_json: Value = serde_json::from_slice(
        &to_bytes(task_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(task_json["data"].as_array().unwrap().len(), 0);

    let finding_response = app
        .oneshot(
            Request::get("/api/v1/search/findings/search?keyword=anything")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(finding_response.status(), StatusCode::OK);
    let finding_json: Value = serde_json::from_slice(
        &to_bytes(finding_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(finding_json["data"].as_array().unwrap().len(), 0);
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}
