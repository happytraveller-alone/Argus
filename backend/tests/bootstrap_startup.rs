use axum::{
    body::{to_bytes, Body},
    http::{Request, StatusCode},
};
use backend_rust::{app::build_router, bootstrap, config::AppConfig, state::AppState};
use serde_json::Value;
use tower::util::ServiceExt;

fn isolated_zip_root(test_name: &str) -> std::path::PathBuf {
    let mut root = std::env::temp_dir();
    root.push(format!(
        "backend-rust-bootstrap-{}-{}",
        test_name,
        uuid::Uuid::new_v4()
    ));
    root
}

#[tokio::test]
async fn bootstrap_ensures_zip_storage_root_exists() {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path = isolated_zip_root("zip-root-exists");

    // Sanity: root should not exist yet.
    assert!(!config.zip_storage_path.exists());

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");

    bootstrap::run(&state)
        .await
        .expect("bootstrap should succeed");

    assert!(
        config.zip_storage_path.exists(),
        "zip storage root should be created by bootstrap"
    );

    // Best-effort cleanup, do not fail the test if remove fails on Windows-like semantics.
    let _ = tokio::fs::remove_dir_all(&config.zip_storage_path).await;
}

#[tokio::test]
async fn bootstrap_reports_file_mode_when_database_is_not_configured() {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path = isolated_zip_root("file-mode-skip");

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    let report = bootstrap::run(&state)
        .await
        .expect("bootstrap should succeed");

    assert_eq!(report.database.mode, "file");
    assert_eq!(report.database.status, "skipped");
    assert!(report.database.checked_tables.is_empty());
    assert_eq!(report.init.status, "ok");
    assert!(
        report.init.actions.iter().any(|action| action == "created default rust system config")
    );
    assert!(
        report.init.actions.iter().any(|action| action == "created empty rust project store")
    );
    assert!(
        report
            .init
            .actions
            .iter()
            .any(|action| action == "scan rule asset import skipped without rust db")
    );
    assert_eq!(report.recovery.status, "skipped");
    assert_eq!(report.preflight.status, "skipped");
    assert!(config.zip_storage_path.join("rust-system-config.json").exists());
    assert!(config.zip_storage_path.join("rust-projects.json").exists());

    let _ = tokio::fs::remove_dir_all(&config.zip_storage_path).await;
}

#[tokio::test]
async fn bootstrap_db_check_does_not_hard_fail_when_database_is_unreachable() {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path = isolated_zip_root("db-unreachable");
    // Port 1 should fail fast on localhost, and we also put a timeout in bootstrap.
    config.database_url = Some("postgres://postgres:postgres@127.0.0.1:1/postgres".to_string());

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");

    let report = bootstrap::run(&state)
        .await
        .expect("bootstrap should not error even if DB is down");

    assert_eq!(report.database.mode, "db");
    assert!(
        report.database.status == "error" || report.database.status == "timeout",
        "expected db status to be error/timeout, got {}",
        report.database.status
    );
    assert_eq!(
        report.database.checked_tables,
        vec![
            "system_configs",
            "rust_projects",
            "rust_project_archives",
            "rust_scan_rule_assets"
        ]
    );

    let _ = tokio::fs::remove_dir_all(&config.zip_storage_path).await;
}

#[tokio::test]
async fn health_includes_bootstrap_status() {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path = isolated_zip_root("health-payload");

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    bootstrap::run(&state)
        .await
        .expect("bootstrap should succeed");

    let app = build_router(state);

    let response = app
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .expect("health request should succeed");

    assert_eq!(response.status(), StatusCode::OK);

    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let payload: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(payload["service"], "backend-rust");
    assert!(payload.get("bootstrap").is_some(), "health must include bootstrap");
    assert_eq!(payload["status"], "ok");
    assert_eq!(payload["bootstrap"]["file_store"]["status"], "ok");
    assert_eq!(
        payload["bootstrap"]["database"]["checked_tables"],
        serde_json::json!([])
    );
    assert_eq!(payload["bootstrap"]["init"]["status"], "ok");
    assert_eq!(payload["bootstrap"]["recovery"]["status"], "skipped");
    assert_eq!(payload["bootstrap"]["preflight"]["status"], "skipped");

    let _ = tokio::fs::remove_dir_all(&config.zip_storage_path).await;
}

#[tokio::test]
async fn health_reports_degraded_when_bootstrap_is_degraded() {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path = isolated_zip_root("health-degraded");
    config.database_url = Some("postgres://postgres:postgres@127.0.0.1:1/postgres".to_string());

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    let report = bootstrap::run(&state)
        .await
        .expect("bootstrap should return degraded report for unreachable db");
    assert_eq!(report.overall, "degraded");

    let app = build_router(state);
    let response = app
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .expect("health request should succeed");

    assert_eq!(response.status(), StatusCode::OK);

    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let payload: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(payload["status"], "degraded");
    assert_eq!(payload["bootstrap"]["database"]["mode"], "db");
    assert_eq!(
        payload["bootstrap"]["database"]["checked_tables"],
        serde_json::json!([
            "system_configs",
            "rust_projects",
            "rust_project_archives",
            "rust_scan_rule_assets"
        ])
    );

    let _ = tokio::fs::remove_dir_all(&config.zip_storage_path).await;
}

#[tokio::test]
async fn bootstrap_fails_when_zip_storage_root_cannot_be_created() {
    let mut config = AppConfig::for_tests();
    let blocked_parent = isolated_zip_root("blocked-parent");
    tokio::fs::write(&blocked_parent, b"not-a-directory")
        .await
        .expect("should create blocking file");
    config.zip_storage_path = blocked_parent.join("nested");

    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");

    let error = bootstrap::run(&state)
        .await
        .expect_err("bootstrap should fail if file storage root cannot be created");

    let report = state.bootstrap.read().await.clone();
    assert_eq!(report.file_store.status, "error");
    assert!(error.to_string().contains("bootstrap failed to initialize file storage root"));

    let _ = tokio::fs::remove_file(&blocked_parent).await;
}
