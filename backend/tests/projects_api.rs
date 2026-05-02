use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, db::task_state, state::AppState};
use serde_json::{json, Value};
use std::io::Write;
use tower::util::ServiceExt;
use uuid::Uuid;

async fn create_project_named(app: &axum::Router, name: &str) -> String {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": name,
                        "source_type": "zip",
                        "default_branch": "main",
                        "programming_languages": []
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
    payload["id"]
        .as_str()
        .expect("project id should exist")
        .to_string()
}

#[tokio::test]
async fn project_crud_and_zip_routes_work_end_to_end() {
    let config = isolated_test_config("projects-crud");
    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_payload = json!({
        "name": "demo-project",
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
    assert!(create_json.get("owner_id").is_none());

    let upload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_multipart_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let reloaded_state = AppState::from_config(config)
        .await
        .expect("reloaded state should build");
    let reloaded_app = build_router(reloaded_state);

    let zip_meta_response = reloaded_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/zip"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(zip_meta_response.status(), StatusCode::OK);
    let zip_meta_json: Value = serde_json::from_slice(
        &to_bytes(zip_meta_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(zip_meta_json["has_file"], true);

    let project_response = reloaded_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}"))
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
    assert!(
        project_json["management_metrics"]["archive_size_bytes"]
            .as_i64()
            .unwrap()
            > 0
    );
    assert!(project_json.get("owner_id").is_none());

    let archive_response = reloaded_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/archive"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(archive_response.status(), StatusCode::OK);
    assert_eq!(
        archive_response.headers()["content-type"],
        "application/zip"
    );

    let info_response = reloaded_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/info/{project_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(info_response.status(), StatusCode::OK);
    let info_json: Value = serde_json::from_slice(
        &to_bytes(info_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(info_json["language_info"]
        .as_str()
        .unwrap()
        .contains("languages"));

    let delete_response = reloaded_app
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri(format!("/api/v1/projects/{project_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(delete_response.status(), StatusCode::NO_CONTENT);
}

#[tokio::test]
async fn deleting_project_removes_related_scan_tasks_from_snapshot() {
    let config = isolated_test_config("projects-delete-cascades-task-state");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone());

    async fn create_project(app: &axum::Router) -> String {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/projects")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "name": "delete-target",
                            "source_type": "zip",
                            "default_branch": "main",
                            "programming_languages": []
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        payload["id"]
            .as_str()
            .expect("project id should exist")
            .to_string()
    }

    let target_project_id = create_project(&app).await;
    let other_project_id = create_project(&app).await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "static-target".to_string(),
        task_state::StaticTaskRecord {
            id: "static-target".to_string(),
            engine: "opengrep".to_string(),
            project_id: target_project_id.clone(),
            name: "static target".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T00:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    snapshot.static_tasks.insert(
        "static-other".to_string(),
        task_state::StaticTaskRecord {
            id: "static-other".to_string(),
            engine: "opengrep".to_string(),
            project_id: other_project_id.clone(),
            name: "static other".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T00:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let delete_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri(format!("/api/v1/projects/{target_project_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(delete_response.status(), StatusCode::NO_CONTENT);

    let snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should reload");
    assert!(!snapshot.static_tasks.contains_key("static-target"));
    assert!(snapshot.static_tasks.contains_key("static-other"));
}

#[tokio::test]
async fn dashboard_snapshot_includes_recent_tasks_from_task_state() {
    let config = isolated_test_config("projects-dashboard-task-state");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone());

    let alpha_project_id = create_project_named(&app, "Alpha Gateway").await;
    let beta_project_id = create_project_named(&app, "Beta API").await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "gitleaks-retired".to_string(),
        task_state::StaticTaskRecord {
            id: "gitleaks-retired".to_string(),
            engine: "gitleaks".to_string(),
            project_id: beta_project_id.clone(),
            name: "retired gitleaks".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T13:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    snapshot.static_tasks.insert(
        "static-new".to_string(),
        task_state::StaticTaskRecord {
            id: "static-new".to_string(),
            engine: "opengrep".to_string(),
            project_id: beta_project_id.clone(),
            name: "static new".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T12:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    snapshot.static_tasks.insert(
        "static-failed".to_string(),
        task_state::StaticTaskRecord {
            id: "static-failed".to_string(),
            engine: "opengrep".to_string(),
            project_id: alpha_project_id.clone(),
            name: "static failed".to_string(),
            status: "failed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T11:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let response = app
        .oneshot(
            Request::get("/api/v1/projects/dashboard-snapshot?top_n=3")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();

    assert_eq!(payload["summary"]["total_projects"], 2);
    assert_eq!(payload["task_status_breakdown"]["completed"], 2);
    assert_eq!(payload["task_status_breakdown"]["failed"], 1);
    assert_eq!(
        payload["task_status_by_scan_type"]["completed"]["static"],
        2
    );
    assert_eq!(payload["task_status_by_scan_type"]["failed"]["static"], 1);

    let recent_tasks = payload["recent_tasks"].as_array().unwrap();
    assert_eq!(recent_tasks.len(), 2);
    assert!(recent_tasks
        .iter()
        .all(|task| task["task_id"] != "gitleaks-retired"));
    assert_eq!(recent_tasks[0]["task_id"], "static-new");
    assert_eq!(recent_tasks[0]["task_type"], "静态审计");
    assert_eq!(recent_tasks[0]["title"], "静态审计 · Beta API");
    assert_eq!(
        recent_tasks[0]["detail_path"],
        "/static-analysis/static-new?opengrepTaskId=static-new"
    );
    assert_eq!(recent_tasks[1]["task_id"], "static-failed");
    assert_eq!(recent_tasks[1]["status"], "failed");
}

#[tokio::test]
async fn dashboard_snapshot_counts_cumulative_vulnerabilities_from_verified_only_findings() {
    let config = isolated_test_config("projects-dashboard-verified-cumulative");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_named(&app, "Verified Dashboard").await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "static-verified".to_string(),
        task_state::StaticTaskRecord {
            id: "static-verified".to_string(),
            engine: "opengrep".to_string(),
            project_id: project_id.clone(),
            name: "static verified".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-04-24T12:00:00Z".to_string(),
            extra: json!({}),
            findings: vec![
                task_state::StaticFindingRecord {
                    id: "static-medium".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "verified".to_string(),
                    payload: json!({"severity": "MEDIUM"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-high".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "verified".to_string(),
                    payload: json!({"severity": "HIGH"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-low-excluded".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "verified".to_string(),
                    payload: json!({"severity": "LOW"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-open-excluded".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "open".to_string(),
                    payload: json!({"severity": "CRITICAL"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-hidden-excluded".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "verified".to_string(),
                    payload: json!({"severity": "CRITICAL", "hidden": true}),
                },
                task_state::StaticFindingRecord {
                    id: "static-false-positive-flag-excluded".to_string(),
                    scan_task_id: "static-verified".to_string(),
                    status: "verified".to_string(),
                    payload: json!({"severity": "HIGH", "is_false_positive": true}),
                },
            ],
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let response = app
        .oneshot(
            Request::get("/api/v1/projects/dashboard-snapshot")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();

    assert_eq!(
        payload["summary"]["current_verified_vulnerability_total"],
        2
    );
    assert_eq!(payload["summary"]["current_effective_findings"], 2);
    assert_eq!(payload["summary"]["current_verified_findings"], 2);
    assert_eq!(payload["verification_funnel"]["verified_findings"], 2);
}

#[tokio::test]
async fn project_management_metrics_include_cumulative_opengrep_findings() {
    let state = AppState::from_config(isolated_test_config("projects-static-metrics"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_named(&app, "Static Metrics").await;

    let upload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_multipart_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "opengrep-cumulative".to_string(),
        task_state::StaticTaskRecord {
            id: "opengrep-cumulative".to_string(),
            engine: "opengrep".to_string(),
            project_id: project_id.clone(),
            name: "static cumulative".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            total_findings: 5,
            scan_duration_ms: 1234,
            files_scanned: 8,
            created_at: "2026-04-26T10:00:00Z".to_string(),
            updated_at: Some("2026-04-26T10:01:00Z".to_string()),
            extra: json!({
                "error_count": 2,
                "warning_count": 1,
                "high_confidence_count": 4,
            }),
            findings: vec![
                task_state::StaticFindingRecord {
                    id: "static-finding-error".to_string(),
                    scan_task_id: "opengrep-cumulative".to_string(),
                    status: "open".to_string(),
                    payload: json!({"id": "static-finding-error", "severity": "ERROR"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-finding-warning".to_string(),
                    scan_task_id: "opengrep-cumulative".to_string(),
                    status: "open".to_string(),
                    payload: json!({"id": "static-finding-warning", "severity": "WARNING"}),
                },
                task_state::StaticFindingRecord {
                    id: "static-finding-medium".to_string(),
                    scan_task_id: "opengrep-cumulative".to_string(),
                    status: "open".to_string(),
                    payload: json!({"id": "static-finding-medium", "severity": "MEDIUM"}),
                },
            ],
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects?include_metrics=true")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let project = payload
        .as_array()
        .unwrap()
        .iter()
        .find(|item| item["id"] == project_id)
        .expect("project should be listed");
    let metrics = &project["management_metrics"];

    assert_eq!(metrics["status"], "ready");
    assert_eq!(metrics["total_tasks"], 2);
    assert_eq!(metrics["completed_tasks"], 2);
    assert_eq!(metrics["opengrep_tasks"], 1);
    assert_eq!(metrics["agent_tasks"], 1);
    assert_eq!(metrics["static_medium"], 0);
    assert_eq!(metrics["static_low"], 3);
    assert_eq!(metrics["intelligent_high"], 1);
    assert_eq!(metrics["high"], 1);
    assert_eq!(metrics["medium"], 0);
    assert_eq!(metrics["low"], 3);
    assert_eq!(metrics["verified_high"], 1);
    assert_eq!(metrics["last_completed_task_at"], "2026-04-26T10:01:00Z");

    let metrics_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/metrics/recalculate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(metrics_response.status(), StatusCode::OK);
    let recalculated: Value = serde_json::from_slice(
        &to_bytes(metrics_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(recalculated["static_medium"], 0);
    assert_eq!(recalculated["low"], 3);
}

#[tokio::test]
async fn project_management_metrics_ignore_static_summary_counts_without_detail_findings() {
    let state = AppState::from_config(isolated_test_config("projects-static-metrics-no-details"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_named(&app, "Static Metrics No Details").await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "opengrep-summary-only".to_string(),
        task_state::StaticTaskRecord {
            id: "opengrep-summary-only".to_string(),
            engine: "opengrep".to_string(),
            project_id: project_id.clone(),
            name: "static summary only".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            total_findings: 7,
            created_at: "2026-04-26T10:00:00Z".to_string(),
            updated_at: Some("2026-04-26T10:01:00Z".to_string()),
            extra: json!({
                "error_count": 4,
                "warning_count": 3,
                "high_confidence_count": 2,
            }),
            findings: Vec::new(),
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let response = app
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let project: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let metrics = &project["management_metrics"];

    assert_eq!(metrics["static_low"], 0);
    assert_eq!(metrics["low"], 0);
}

#[tokio::test]
async fn project_metrics_degrade_when_task_state_snapshot_is_malformed() {
    let config = isolated_test_config("projects-malformed-task-state");
    let state = AppState::from_config(config.clone())
        .await
        .expect("state should build");
    let app = build_router(state);
    let project_id = create_project_named(&app, "Malformed Snapshot").await;
    let snapshot_path = config.zip_storage_path.join("rust-task-state.json");
    tokio::fs::create_dir_all(&config.zip_storage_path)
        .await
        .expect("storage dir should exist");
    tokio::fs::write(&snapshot_path, b"{not-json")
        .await
        .expect("malformed snapshot should be written");

    let detail_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(detail_response.status(), StatusCode::OK);
    let detail: Value = serde_json::from_slice(
        &to_bytes(detail_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(detail["management_metrics"]["total_tasks"], 0);

    let list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects?include_metrics=true")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(list_response.status(), StatusCode::OK);

    let update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri(format!("/api/v1/projects/{project_id}"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Malformed Snapshot Updated"
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(update_response.status(), StatusCode::OK);

    let metrics_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/metrics/recalculate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(metrics_response.status(), StatusCode::OK);
    let metrics: Value = serde_json::from_slice(
        &to_bytes(metrics_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(metrics["total_tasks"], 0);
}

#[tokio::test]
async fn create_with_tar_xz_and_zst_archives_and_description_preview_use_static_analysis() {
    let state = AppState::from_config(isolated_test_config("projects-create-with-archive"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());

    let preview_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/description/generate")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_tar_xz_preview_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preview_response.status(), StatusCode::OK);
    let preview_json: Value = serde_json::from_slice(
        &to_bytes(preview_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(preview_json["source"], "static");

    let create_with_zip_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/create-with-zip")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_create_with_tar_xz_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_with_zip_response.status(), StatusCode::OK);
    let create_with_zip_json: Value = serde_json::from_slice(
        &to_bytes(create_with_zip_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let created_project_id = create_with_zip_json["id"]
        .as_str()
        .expect("created project id should exist");
    assert!(create_with_zip_json["description"]
        .as_str()
        .unwrap_or_default()
        .contains("Detected languages: Rust"));

    let created_file_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/projects/{created_project_id}/files/src/main.rs"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(created_file_response.status(), StatusCode::OK);

    let preview_upload_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/projects/{created_project_id}/upload/preview"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preview_upload_response.status(), StatusCode::OK);
    let preview_upload_json: Value = serde_json::from_slice(
        &to_bytes(preview_upload_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let supported_formats = preview_upload_json["supported_formats"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    assert!(supported_formats
        .iter()
        .any(|item| item.as_str() == Some(".tar.xz")));
    assert!(supported_formats
        .iter()
        .any(|item| item.as_str() == Some(".zst")));

    let create_payload = json!({
        "name": "zst-project",
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
    let zst_project_id = create_json["id"]
        .as_str()
        .expect("zst project id should exist");

    let upload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{zst_project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zst_multipart_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let zst_file_response = app
        .oneshot(
            Request::get(format!(
                "/api/v1/projects/{zst_project_id}/files/src/main.rs"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(zst_file_response.status(), StatusCode::OK);
}

#[tokio::test]
async fn create_with_zip_accepts_multi_megabyte_archives() {
    let state = AppState::from_config(isolated_test_config("projects-create-large-zip"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let body = test_create_with_large_zip_body();
    assert!(
        body.len() > 2 * 1024 * 1024,
        "test payload must exceed axum's default multipart body limit"
    );

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/create-with-zip")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let json: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(
        json["management_metrics"]["archive_size_bytes"]
            .as_i64()
            .unwrap_or_default()
            > 2 * 1024 * 1024,
        "stored archive size should preserve the uploaded multi-megabyte zip"
    );
}

#[tokio::test]
async fn download_project_archive_supports_utf8_filenames() {
    let config = isolated_test_config("projects-utf8-archive-name");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_payload = json!({
        "name": "utf8-project",
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

    let upload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_multipart_bytes(vec![(
                    "file",
                    Some("审计项目\"最终版\".zip"),
                    Some("application/zip"),
                    test_zip_bytes(),
                )])))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let archive_response = app
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/archive"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(archive_response.status(), StatusCode::OK);
    let disposition = archive_response
        .headers()
        .get("content-disposition")
        .expect("content-disposition should exist")
        .to_str()
        .expect("content-disposition should be ASCII-safe");
    assert!(disposition.contains("filename="));
    assert!(disposition.contains("filename*=UTF-8''"));
    assert!(disposition.contains("%E5%AE%A1%E8%AE%A1"));
}

#[tokio::test]
async fn project_file_content_reports_actual_encoding_instead_of_requested_encoding() {
    let config = isolated_test_config("projects-file-content-encoding");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_payload = json!({
        "name": "encoding-project",
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

    let upload_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_multipart_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let latin1_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/projects/{project_id}/files/src/main.rs?encoding=latin1"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(latin1_response.status(), StatusCode::OK);
    let latin1_json: Value = serde_json::from_slice(
        &to_bytes(latin1_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(latin1_json["encoding"], "utf-8");
    assert_eq!(latin1_json["is_cached"], false);

    let cached_response = app
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/files/src/main.rs"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cached_response.status(), StatusCode::OK);
    let cached_json: Value = serde_json::from_slice(
        &to_bytes(cached_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cached_json["encoding"], "utf-8");
    assert_eq!(cached_json["is_cached"], true);
}

#[tokio::test]
async fn projects_domain_endpoints_cover_files_stats_and_transfer() {
    let source_config = isolated_test_config("projects-domain-source");
    let source_state = AppState::from_config(source_config.clone())
        .await
        .expect("source state should build");
    let source_app = build_router(source_state);

    let create_payload = json!({
        "name": "domain-project",
        "source_type": "zip",
        "default_branch": "main",
        "programming_languages": []
    });

    let create_response = source_app
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
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let project_id = create_json["id"].as_str().unwrap().to_string();

    let upload_response = source_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/zip"))
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_multipart_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload_response.status(), StatusCode::OK);

    let files_response = source_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/files"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(files_response.status(), StatusCode::OK);
    let files_json: Value = serde_json::from_slice(
        &to_bytes(files_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(files_json
        .as_array()
        .unwrap()
        .iter()
        .any(|entry| entry["path"] == "src/main.rs"));

    let file_tree_response = source_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/files-tree"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(file_tree_response.status(), StatusCode::OK);
    let file_tree_json: Value = serde_json::from_slice(
        &to_bytes(file_tree_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(file_tree_json["root"]["type"], "directory");

    let file_content_response = source_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/files/src/main.rs"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(file_content_response.status(), StatusCode::OK);
    let file_content_json: Value = serde_json::from_slice(
        &to_bytes(file_content_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(file_content_json["content"]
        .as_str()
        .unwrap()
        .contains("fn main()"));
    assert_eq!(file_content_json["is_cached"], false);

    let cached_file_content_response = source_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/files/src/main.rs"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cached_file_content_response.status(), StatusCode::OK);
    let cached_file_content_json: Value = serde_json::from_slice(
        &to_bytes(cached_file_content_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cached_file_content_json["is_cached"], true);
    assert!(cached_file_content_json["created_at"].is_string());

    let preview_response = source_app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/projects/{project_id}/upload/preview"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preview_response.status(), StatusCode::OK);

    let cache_stats_response = source_app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects/cache/stats")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cache_stats_response.status(), StatusCode::OK);
    let cache_stats_json: Value = serde_json::from_slice(
        &to_bytes(cache_stats_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cache_stats_json["total_entries"], 1);
    assert_eq!(cache_stats_json["hits"], 1);
    assert_eq!(cache_stats_json["misses"], 1);
    assert_eq!(cache_stats_json["evictions"], 0);
    assert!(cache_stats_json["memory_used_mb"].as_f64().unwrap() > 0.0);

    let cache_invalidate_response = source_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/cache/invalidate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cache_invalidate_response.status(), StatusCode::OK);
    let cache_invalidate_json: Value = serde_json::from_slice(
        &to_bytes(cache_invalidate_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cache_invalidate_json["deleted_entries"], 1);

    let cache_clear_response = source_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/cache/clear")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cache_clear_response.status(), StatusCode::OK);
    let cache_clear_json: Value = serde_json::from_slice(
        &to_bytes(cache_clear_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cache_clear_json["deleted_entries"], 0);

    let stats_response = source_app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects/stats")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(stats_response.status(), StatusCode::OK);
    let stats_json: Value = serde_json::from_slice(
        &to_bytes(stats_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(stats_json["total_projects"], 1);

    let dashboard_response = source_app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects/dashboard-snapshot")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(dashboard_response.status(), StatusCode::OK);
    let dashboard_json: Value = serde_json::from_slice(
        &to_bytes(dashboard_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(dashboard_json["summary"]["total_projects"], 1);

    let overview_response = source_app
        .clone()
        .oneshot(
            Request::get("/api/v1/projects/static-scan-overview?page=1&page_size=6")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(overview_response.status(), StatusCode::OK);
    let overview_json: Value = serde_json::from_slice(
        &to_bytes(overview_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(overview_json["page"], 1);

    let metrics_response = source_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/projects/{project_id}/metrics/recalculate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(metrics_response.status(), StatusCode::OK);

    let export_response = source_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/export")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_ids": [project_id],
                        "include_archives": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(export_response.status(), StatusCode::OK);
    assert_eq!(export_response.headers()["content-type"], "application/zip");
    let export_bytes = to_bytes(export_response.into_body(), usize::MAX)
        .await
        .unwrap()
        .to_vec();

    let target_config = isolated_test_config("projects-domain-target");
    let target_state = AppState::from_config(target_config.clone())
        .await
        .expect("target state should build");
    let target_app = build_router(target_state);

    let import_response = target_app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/import")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_bundle_multipart_body(export_bytes)))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(import_response.status(), StatusCode::OK);
    let import_json: Value = serde_json::from_slice(
        &to_bytes(import_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        import_json["imported_projects"].as_array().unwrap().len(),
        1
    );
}

fn test_zip_multipart_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![(
        "file",
        Some("demo.zip"),
        Some("application/zip"),
        test_zip_bytes(),
    )])
}

fn test_tar_xz_preview_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![
        ("project_name", None, None, b"demo-preview".to_vec()),
        (
            "file",
            Some("demo.tar.xz"),
            Some("application/x-xz"),
            test_tar_xz_bytes(),
        ),
    ])
}

fn test_create_with_tar_xz_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![
        ("name", None, None, b"demo-create-with-archive".to_vec()),
        (
            "file",
            Some("demo.tar.xz"),
            Some("application/x-xz"),
            test_tar_xz_bytes(),
        ),
    ])
}

fn test_create_with_large_zip_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![
        ("name", None, None, b"demo-create-with-large-zip".to_vec()),
        (
            "file",
            Some("large-demo.zip"),
            Some("application/zip"),
            test_large_zip_bytes(),
        ),
    ])
}

fn test_zst_multipart_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![(
        "file",
        Some("demo.zst"),
        Some("application/zstd"),
        test_tar_zst_bytes(),
    )])
}

fn test_bundle_multipart_body(bundle_bytes: Vec<u8>) -> Vec<u8> {
    test_zip_multipart_bytes(vec![(
        "bundle",
        Some("projects-export.zip"),
        Some("application/zip"),
        bundle_bytes,
    )])
}

type MultipartField<'a> = (&'a str, Option<&'a str>, Option<&'a str>, Vec<u8>);

fn test_zip_multipart_bytes(fields: Vec<MultipartField<'_>>) -> Vec<u8> {
    let mut body = Vec::new();
    for (name, filename, content_type, bytes) in fields {
        body.extend_from_slice(b"--x-boundary\r\n");
        body.extend_from_slice(
            format!("Content-Disposition: form-data; name=\"{name}\"").as_bytes(),
        );
        if let Some(filename) = filename {
            let escaped = filename.replace('\\', "\\\\").replace('"', "\\\"");
            body.extend_from_slice(format!("; filename=\"{escaped}\"").as_bytes());
        }
        body.extend_from_slice(b"\r\n");
        if let Some(content_type) = content_type {
            body.extend_from_slice(format!("Content-Type: {content_type}\r\n").as_bytes());
        }
        body.extend_from_slice(b"\r\n");
        body.extend_from_slice(&bytes);
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(b"--x-boundary--\r\n");
    body
}

fn test_zip_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    {
        let cursor = std::io::Cursor::new(&mut bytes);
        let mut writer = zip::ZipWriter::new(cursor);
        let options = zip::write::SimpleFileOptions::default();
        writer.start_file("src/main.rs", options).unwrap();
        writer.write_all(b"fn main() {}\n").unwrap();
        writer.finish().unwrap();
    }
    bytes
}

fn test_large_zip_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    {
        let cursor = std::io::Cursor::new(&mut bytes);
        let mut writer = zip::ZipWriter::new(cursor);
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Stored);
        writer.start_file("src/main.rs", options).unwrap();
        writer.write_all(&vec![b'x'; 3 * 1024 * 1024]).unwrap();
        writer.finish().unwrap();
    }
    bytes
}

fn test_tar_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut bytes);
        let content = b"fn main() {}\n";
        let mut header = tar::Header::new_gnu();
        header.set_size(content.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        builder
            .append_data(&mut header, "src/main.rs", &content[..])
            .unwrap();
        builder.finish().unwrap();
    }
    bytes
}

fn test_tar_xz_bytes() -> Vec<u8> {
    let tar_bytes = test_tar_bytes();
    let mut encoded = xz2::write::XzEncoder::new(Vec::new(), 6);
    encoded.write_all(&tar_bytes).unwrap();
    encoded.finish().unwrap()
}

fn test_tar_zst_bytes() -> Vec<u8> {
    let tar_bytes = test_tar_bytes();
    zstd::stream::encode_all(std::io::Cursor::new(tar_bytes), 1).unwrap()
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}
