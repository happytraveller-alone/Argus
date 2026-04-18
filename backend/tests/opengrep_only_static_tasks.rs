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

#[tokio::test]
async fn gitleaks_routes_are_not_owned_when_static_tasks_are_opengrep_only() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let requests = [
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/gitleaks/rules?limit=5")
            .body(Body::empty())
            .unwrap(),
        Request::builder()
            .method(Method::POST)
            .uri("/api/v1/static-tasks/gitleaks/scan")
            .header("content-type", "application/json")
            .body(Body::from(
                serde_json::json!({
                    "project_id": "demo-project",
                    "name": "gitleaks should be retired",
                    "target_path": ".",
                    "no_git": true,
                })
                .to_string(),
            ))
            .unwrap(),
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/gitleaks/tasks/demo/findings?limit=5")
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

#[tokio::test]
async fn phpstan_routes_are_not_owned_when_static_tasks_are_opengrep_only() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let requests = [
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/phpstan/rules?limit=5")
            .body(Body::empty())
            .unwrap(),
        Request::builder()
            .method(Method::POST)
            .uri("/api/v1/static-tasks/phpstan/scan")
            .header("content-type", "application/json")
            .body(Body::from(
                serde_json::json!({
                    "project_id": "demo-project",
                    "name": "phpstan should be retired",
                    "target_path": ".",
                    "level": 5,
                })
                .to_string(),
            ))
            .unwrap(),
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/phpstan/tasks/demo/findings?limit=5")
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

#[tokio::test]
async fn pmd_routes_are_not_owned_when_static_tasks_are_opengrep_only() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let requests = [
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/pmd/presets")
            .body(Body::empty())
            .unwrap(),
        Request::builder()
            .method(Method::POST)
            .uri("/api/v1/static-tasks/pmd/scan")
            .header("content-type", "application/json")
            .body(Body::from(
                serde_json::json!({
                    "project_id": "demo-project",
                    "name": "pmd should be retired",
                    "target_path": ".",
                    "ruleset": "security",
                })
                .to_string(),
            ))
            .unwrap(),
        Request::builder()
            .method(Method::GET)
            .uri("/api/v1/static-tasks/pmd/tasks/demo/findings?limit=5")
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
