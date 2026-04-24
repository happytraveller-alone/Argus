use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, db::task_state, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

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
    snapshot.agent_tasks.insert(
        "agent-target".to_string(),
        task_state::AgentTaskRecord {
            id: "agent-target".to_string(),
            project_id: target_project_id.clone(),
            task_type: "agent".to_string(),
            status: "running".to_string(),
            created_at: "2026-04-24T00:00:00Z".to_string(),
            ..Default::default()
        },
    );
    snapshot.agent_tasks.insert(
        "agent-other".to_string(),
        task_state::AgentTaskRecord {
            id: "agent-other".to_string(),
            project_id: other_project_id.clone(),
            task_type: "agent".to_string(),
            status: "running".to_string(),
            created_at: "2026-04-24T00:00:00Z".to_string(),
            ..Default::default()
        },
    );
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
    assert!(!snapshot.agent_tasks.contains_key("agent-target"));
    assert!(!snapshot.static_tasks.contains_key("static-target"));
    assert!(snapshot.agent_tasks.contains_key("agent-other"));
    assert!(snapshot.static_tasks.contains_key("static-other"));
}

#[tokio::test]
async fn create_with_zip_and_description_preview_are_available() {
    let state = AppState::from_config(isolated_test_config("projects-create-with-zip"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let preview_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/description/generate")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_zip_preview_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(preview_response.status(), StatusCode::OK);

    let create_with_zip_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects/create-with-zip")
                .header("content-type", "multipart/form-data; boundary=x-boundary")
                .body(Body::from(test_create_with_zip_body()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_with_zip_response.status(), StatusCode::OK);
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

fn test_zip_preview_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![
        ("project_name", None, None, b"demo-preview".to_vec()),
        (
            "file",
            Some("demo.zip"),
            Some("application/zip"),
            test_zip_bytes(),
        ),
    ])
}

fn test_create_with_zip_body() -> Vec<u8> {
    test_zip_multipart_bytes(vec![
        ("name", None, None, b"demo-create-with-zip".to_vec()),
        (
            "file",
            Some("demo.zip"),
            Some("application/zip"),
            test_zip_bytes(),
        ),
    ])
}

fn test_bundle_multipart_body(bundle_bytes: Vec<u8>) -> Vec<u8> {
    test_zip_multipart_bytes(vec![(
        "bundle",
        Some("projects-export.zip"),
        Some("application/zip"),
        bundle_bytes,
    )])
}

fn test_zip_multipart_bytes(fields: Vec<(&str, Option<&str>, Option<&str>, Vec<u8>)>) -> Vec<u8> {
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
    use std::io::Write;

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

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}
