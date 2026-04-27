use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router, bootstrap, config::AppConfig, db::scan_rule_assets, state::AppState,
};
use serde_json::Value;
use tower::util::ServiceExt;
use uuid::Uuid;

fn optional_db_test_config(scope: &str) -> Option<AppConfig> {
    let database_url = std::env::var("RUST_DATABASE_URL")
        .or_else(|_| std::env::var("DATABASE_URL"))
        .ok()?;
    let mut config = AppConfig::for_tests();
    config.rust_database_url = Some(database_url);
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    Some(config)
}

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

#[tokio::test]
async fn opengrep_rule_asset_sync_deactivates_removed_builtin_assets() {
    let Some(config) = optional_db_test_config("opengrep-stale-rule-assets") else {
        eprintln!("skipping db-backed scan rule asset sync test without RUST_DATABASE_URL");
        return;
    };
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    bootstrap::run(&state)
        .await
        .expect("startup bootstrap should create scan rule asset schema");
    let pool = state
        .db_pool
        .as_ref()
        .expect("db-backed test config should create a pool");

    let stale_asset_path = format!(
        "rules_opengrep/c/__removed-test-rule-{}.yml",
        Uuid::new_v4()
    );
    sqlx::query(
        r#"
        insert into rust_scan_rule_assets (
            engine, source_kind, asset_path, file_format, sha256, content, metadata_json, is_active
        )
        values ('opengrep', 'internal_rule', $1, 'yml', 'stale-sha', 'rules: []', '{}'::jsonb, true)
        on conflict (engine, source_kind, asset_path) do update
        set sha256 = excluded.sha256,
            content = excluded.content,
            is_active = true,
            updated_at = now()
        "#,
    )
    .bind(&stale_asset_path)
    .execute(pool)
    .await
    .expect("stale asset row should be insertable");

    let summary = scan_rule_assets::ensure_initialized(&state)
        .await
        .expect("scan rule assets should sync");
    assert!(
        summary.deactivated >= 1,
        "expected removed builtin rule asset rows to be deactivated"
    );

    let is_active = sqlx::query_scalar::<_, bool>(
        r#"
        select is_active
        from rust_scan_rule_assets
        where engine = 'opengrep' and source_kind = 'internal_rule' and asset_path = $1
        "#,
    )
    .bind(&stale_asset_path)
    .fetch_one(pool)
    .await
    .expect("stale asset row should remain queryable");
    assert!(!is_active, "removed builtin rule asset should be inactive");

    let loaded = scan_rule_assets::load_asset_content(
        &state,
        "opengrep",
        "internal_rule",
        &stale_asset_path,
    )
    .await
    .expect("asset lookup should complete");
    assert!(
        loaded.is_none(),
        "inactive stale rule assets must not be materialized for future scans"
    );

    sqlx::query(
        r#"
        delete from rust_scan_rule_assets
        where engine = 'opengrep' and source_kind = 'internal_rule' and asset_path = $1
        "#,
    )
    .bind(&stale_asset_path)
    .execute(pool)
    .await
    .expect("test stale asset row should be removable");
}

#[tokio::test]
async fn opengrep_builtin_rules_only_expose_error_severity_from_assets() {
    let state = AppState::from_config(AppConfig::for_tests())
        .await
        .expect("state should build");
    bootstrap::run(&state)
        .await
        .expect("startup bootstrap should initialize scan rule assets");
    let app = build_router(state);

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/rules?limit=5000")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("request should complete");
    assert_eq!(response.status(), StatusCode::OK);

    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let items = payload["data"]
        .as_array()
        .expect("rules response should expose data array");
    assert_eq!(
        payload.get("total").and_then(Value::as_u64),
        Some(items.len() as u64)
    );
    assert!(
        items.iter().all(|item| {
            item.get("is_active").and_then(Value::as_bool) == Some(true)
                && item.get("severity").and_then(Value::as_str) == Some("ERROR")
                && item.get("source").and_then(Value::as_str) == Some("internal")
        }),
        "expected builtin opengrep assets to expose only active internal ERROR-severity rules"
    );
    assert!(
        items.iter().all(|item| {
            item.get("id").and_then(Value::as_str).is_some_and(|id| {
                !id.rsplit('/')
                    .next()
                    .unwrap_or_default()
                    .starts_with("vuln-")
                    && id != "rules_opengrep/c/vim-double-free-b29f4abc.yml"
            })
        }),
        "expected generated project/CVE-specific opengrep rules to stay pruned"
    );
    let representative_rule = items
        .iter()
        .find(|item| {
            item.get("id").and_then(Value::as_str) == Some("rules_opengrep/java/aes_ecb_mode.yaml")
        })
        .expect("expected representative builtin asset to be present");
    assert_eq!(
        representative_rule.get("severity").and_then(Value::as_str),
        Some("ERROR")
    );
    assert_eq!(
        representative_rule.get("language").and_then(Value::as_str),
        Some("java")
    );

    let java_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/rules?language=java&limit=5000")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("language-filtered rules request should complete");
    assert_eq!(java_response.status(), StatusCode::OK);
    let java_payload: Value = serde_json::from_slice(
        &to_bytes(java_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let java_items = java_payload["data"]
        .as_array()
        .expect("language-filtered rules response should expose data array");
    assert!(
        java_items.iter().any(|item| {
            item.get("id").and_then(Value::as_str) == Some("rules_opengrep/java/aes_ecb_mode.yaml")
        }),
        "java language filter should include language-scoped rules_opengrep assets"
    );
    assert!(
        java_items
            .iter()
            .all(|item| item.get("language").and_then(Value::as_str) == Some("java")),
        "java language filter should only return java rules"
    );

    let stats_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/rules/stats")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("stats request should complete");
    assert_eq!(stats_response.status(), StatusCode::OK);
    let stats_payload: Value = serde_json::from_slice(
        &to_bytes(stats_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        stats_payload.get("total").and_then(Value::as_u64),
        Some(items.len() as u64)
    );
    assert_eq!(
        stats_payload.get("inactive").and_then(Value::as_u64),
        Some(0)
    );
    let stats_languages = stats_payload["languages"]
        .as_array()
        .expect("stats response should include language metadata");
    assert!(
        stats_languages
            .iter()
            .any(|language| language.as_str() == Some("java")),
        "stats response should include language metadata from rules_opengrep directories"
    );
    assert!(
        stats_languages
            .iter()
            .any(|language| language.as_str() == Some("cpp")),
        "stats response should include split cpp rules"
    );
}
