use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
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
            body.extend_from_slice(format!("; filename=\"{filename}\"").as_bytes());
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
