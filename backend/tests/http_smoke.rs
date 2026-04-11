use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use tower::util::ServiceExt;

#[tokio::test]
async fn health_returns_ok() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .expect("health request should succeed");

    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn unknown_api_route_is_not_owned_locally_yet() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::get("/api/v1/unknown-route")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("unknown route request should complete");

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn system_config_defaults_returns_ok() {
    let state = AppState::from_config(AppConfig::for_tests())
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
        .expect("defaults request should succeed");

    assert_eq!(response.status(), StatusCode::OK);
}
