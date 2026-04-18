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
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let project_id = create_json["id"].as_str().unwrap().to_string();

    let task_create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "primary codex audit task",
                        "description": "unique primary task body",
                        "verification_level": "standard"
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(task_create_response.status(), StatusCode::OK);
    let task_create_json: Value = serde_json::from_slice(
        &to_bytes(task_create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = task_create_json["id"].as_str().unwrap().to_string();

    let second_task_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "codex search audit follow-up",
                        "description": "search keyword second task body",
                        "verification_level": "standard"
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(second_task_response.status(), StatusCode::OK);

    let static_task_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "opengrep search scan",
                        "target_path": ".",
                        "rule_ids": []
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(static_task_response.status(), StatusCode::OK);

    let seed_findings_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/agent-tasks/{task_id}/start"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(seed_findings_response.status(), StatusCode::OK);

    let global_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/search?keyword=search")
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
    assert_eq!(global_json["keyword"], "search");
    assert!(global_json["projects"].as_array().unwrap().len() >= 1);
    assert!(global_json["tasks"].as_array().unwrap().len() >= 1);
    assert!(global_json["findings"].as_array().unwrap().len() >= 1);
    assert!(global_json["total"]["projects_total"].as_i64().unwrap() >= 1);
    assert!(global_json["total"]["tasks_total"].as_i64().unwrap() >= 1);
    assert!(global_json["total"]["findings_total"].as_i64().unwrap() >= 1);

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
            Request::get("/api/v1/search/tasks/search?keyword=primary")
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
    assert_eq!(task_json["total"].as_i64().unwrap(), 1);
    assert_eq!(task_json["data"].as_array().unwrap().len(), 1);
    assert_eq!(task_json["data"][0]["id"], task_id);

    let paged_task_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/tasks/search?keyword=search&limit=1")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(paged_task_response.status(), StatusCode::OK);
    let paged_task_json: Value = serde_json::from_slice(
        &to_bytes(paged_task_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(paged_task_json["data"].as_array().unwrap().len(), 1);
    assert_eq!(paged_task_json["total"].as_i64().unwrap(), 2);

    let static_task_search_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/tasks/search?keyword=opengrep")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(static_task_search_response.status(), StatusCode::OK);
    let static_task_search_json: Value = serde_json::from_slice(
        &to_bytes(static_task_search_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(static_task_search_json["total"].as_i64().unwrap(), 1);
    assert_eq!(static_task_search_json["data"].as_array().unwrap().len(), 1);
    assert_eq!(static_task_search_json["data"][0]["task_type"], "opengrep");

    let finding_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/search/findings/search?keyword=Reflected%20XSS")
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
    assert_eq!(finding_json["total"].as_i64().unwrap(), 1);
    assert_eq!(finding_json["data"].as_array().unwrap().len(), 1);
    assert_eq!(finding_json["data"][0]["task_id"], task_id);

    let static_finding_response = app
        .oneshot(
            Request::get("/api/v1/search/findings/search?keyword=rust-placeholder-opengrep-rule")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(static_finding_response.status(), StatusCode::OK);
    let static_finding_json: Value = serde_json::from_slice(
        &to_bytes(static_finding_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(static_finding_json["total"].as_i64().unwrap(), 1);
    assert_eq!(static_finding_json["data"].as_array().unwrap().len(), 1);
    assert_eq!(
        static_finding_json["data"][0]["vulnerability_type"],
        "rust-placeholder-opengrep-rule"
    );
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}
