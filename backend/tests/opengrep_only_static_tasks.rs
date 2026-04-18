use axum::{
    body::Body,
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use tower::util::ServiceExt;

#[tokio::test]
async fn bandit_routes_are_not_owned_when_static_tasks_are_opengrep_only() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let requests = [
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/bandit/rules?limit=5")
            .body(Body::empty())
            .unwrap(),
        Request::builder()
            .method(Method::POST)
            .uri("/api/v1/static-tasks/bandit/scan")
            .header("content-type", "application/json")
            .body(Body::from(
                serde_json::json!({
                    "project_id": "demo-project",
                    "name": "bandit should be retired",
                    "target_path": ".",
                })
                .to_string(),
            ))
            .unwrap(),
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/bandit/tasks/demo/findings?limit=5")
            .body(Body::empty())
            .unwrap(),
    ];

    for request in requests {
        let response = app
            .clone()
            .oneshot(request)
            .await
            .expect("request should complete");
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
