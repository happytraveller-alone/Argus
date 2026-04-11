use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;

#[tokio::test]
async fn project_crud_and_zip_routes_work_end_to_end() {
    let state = AppState::from_config(AppConfig::for_tests())
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

    let zip_meta_response = app
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

    let project_response = app
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

    let archive_response = app
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

    let info_response = app
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

    let delete_response = app
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
    let state = AppState::from_config(AppConfig::for_tests())
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
