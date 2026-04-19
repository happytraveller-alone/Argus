use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}

#[tokio::test]
async fn create_generic_rule_normalizes_top_level_yaml_list() {
    let state = AppState::from_config(isolated_test_config("opengrep-generic-create"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/create-generic")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_yaml": r#"
- id: demo-rule-with-dash
  message: Detect demo usage
  severity: ERROR
  languages:
    - generic
  pattern: demo($X)
"#
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
    assert!(payload["id"]
        .as_str()
        .is_some_and(|value| value.starts_with("generic:")));
    assert_eq!(payload["name"], "demo-rule-with-dash");
    assert_eq!(payload["language"], "generic");
    assert_eq!(payload["severity"], "ERROR");
    assert!(payload["pattern_yaml"]
        .as_str()
        .is_some_and(|value| value.starts_with("rules:\n  - id: demo-rule-with-dash")));
}

#[tokio::test]
async fn upload_json_rule_rejects_missing_pattern_fields() {
    let state = AppState::from_config(isolated_test_config("opengrep-upload-validate"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/upload/json")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "missing-pattern",
                        "language": "python",
                        "pattern_yaml": r#"
rules:
  - id: missing-pattern
    message: Missing pattern field
    severity: ERROR
    languages: [python]
"#
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
    assert_eq!(
        payload["error"],
        "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"
    );
}

#[tokio::test]
async fn create_generic_rule_rejects_malformed_yaml() {
    let state = AppState::from_config(isolated_test_config("opengrep-generic-malformed"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/create-generic")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_yaml": r#"
rules:
  - id: malformed-rule
    message: malformed
    severity: ERROR
    languages: [python
    : bad
    pattern: dangerous_call($X)
"#
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
    assert_eq!(payload["error"], "规则YAML解析失败");
}

#[tokio::test]
async fn create_generic_rule_does_not_let_nested_metadata_pattern_satisfy_schema() {
    let state = AppState::from_config(isolated_test_config("opengrep-generic-nested-pattern"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/create-generic")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_yaml": r#"
rules:
  - id: nested-pattern-only
    message: Missing top-level pattern
    severity: ERROR
    languages: [python]
    metadata:
      pattern: should-not-count
"#
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
    assert_eq!(
        payload["error"],
        "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"
    );
}

#[tokio::test]
async fn update_rule_revalidates_pattern_yaml() {
    let state = AppState::from_config(isolated_test_config("opengrep-update-validate"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/create-generic")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_yaml": r#"
rules:
  - id: update-target
    message: Valid rule
    severity: ERROR
    languages: [python]
    pattern: dangerous_call($X)
"#
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_payload: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let storage_id = create_payload["id"]
        .as_str()
        .expect("create should return storage id")
        .to_string();

    let update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PATCH)
                .uri(format!("/api/v1/static-tasks/rules/{storage_id}"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "pattern_yaml": r#"
rules:
  - id: update-target
    message: Invalid replacement
    severity: ERROR
    languages: [python]
"#
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(update_response.status(), StatusCode::BAD_REQUEST);
    let payload: Value = serde_json::from_slice(
        &to_bytes(update_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        payload["error"],
        "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"
    );

    let detail_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(format!("/api/v1/static-tasks/rules/{storage_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(detail_response.status(), StatusCode::OK);
    let detail_payload: Value = serde_json::from_slice(
        &to_bytes(detail_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(detail_payload["id"], storage_id);
    assert_eq!(detail_payload["name"], "update-target");
    assert_eq!(detail_payload["severity"], "ERROR");
    assert!(detail_payload["pattern_yaml"]
        .as_str()
        .is_some_and(|value| value.contains("pattern: dangerous_call($X)")));
}

#[tokio::test]
async fn create_rule_from_patch_uses_patch_metadata_when_available() {
    let state = AppState::from_config(isolated_test_config("opengrep-create-from-patch"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/create")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "repo_owner": "octo",
                        "repo_name": "demo",
                        "commit_hash": "deadbeef",
                        "commit_content": r#"
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@
-dangerous_call(user_input)
+safe_call(user_input)
"#
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
    assert!(payload["id"]
        .as_str()
        .is_some_and(|value| value.starts_with("patch:")));
    assert_eq!(payload["name"], "demo-deadbeef");
    assert_eq!(payload["language"], "python");
    assert_eq!(payload["severity"], "ERROR");
    assert_eq!(payload["source"], "patch");
}
