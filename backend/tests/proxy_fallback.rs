use axum::{
    body::{to_bytes, Body},
    extract::Request,
    http::{header, HeaderMap, StatusCode},
    response::IntoResponse,
    routing::any,
    Json, Router,
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tokio::{net::TcpListener, task::JoinHandle};
use tower::util::ServiceExt;

#[tokio::test]
async fn forwards_get_requests_to_python_upstream() {
    let (_task, upstream_base_url) = spawn_upstream().await;
    let state =
        AppState::from_config(AppConfig::for_tests().with_python_upstream(upstream_base_url))
            .await
            .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            axum::http::Request::get("/api/v1/agent-tasks/demo?source=test")
                .header("x-request-id", "req-123")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("proxy request should succeed");

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()["x-upstream"], "python-fake");

    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let payload: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(payload["method"], "GET");
    assert_eq!(payload["path"], "/api/v1/agent-tasks/demo");
    assert_eq!(payload["query"], "source=test");
    assert_eq!(payload["headers"]["x-request-id"], "req-123");
}

#[tokio::test]
async fn forwards_multipart_requests_without_changing_query_or_content_type() {
    let (_task, upstream_base_url) = spawn_upstream().await;
    let state =
        AppState::from_config(AppConfig::for_tests().with_python_upstream(upstream_base_url))
            .await
            .expect("state should build");
    let app = build_router(state);

    let boundary = "codex-boundary";
    let payload = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"demo.txt\"\r\nContent-Type: text/plain\r\n\r\nhello-from-proxy\r\n--{boundary}--\r\n"
    );

    let response = app
        .oneshot(
            axum::http::Request::post("/api/v1/agent-tasks/upload?keep=query")
                .header(
                    header::CONTENT_TYPE,
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .body(Body::from(payload.clone()))
                .unwrap(),
        )
        .await
        .expect("multipart proxy request should succeed");

    assert_eq!(response.status(), StatusCode::OK);
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(json["query"], "keep=query");
    assert!(json["headers"]["content-type"]
        .as_str()
        .unwrap_or_default()
        .contains(boundary));
    assert!(json["bodyText"]
        .as_str()
        .unwrap_or_default()
        .contains("hello-from-proxy"));
}

async fn spawn_upstream() -> (JoinHandle<()>, String) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let app = Router::new().route("/{*path}", any(fake_upstream));
    let task = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    (task, format!("http://{address}"))
}

async fn fake_upstream(request: Request) -> impl IntoResponse {
    let (parts, body) = request.into_parts();
    let body = to_bytes(body, usize::MAX).await.unwrap();
    let headers = lowercase_headers(&parts.headers);

    let response = json!({
        "method": parts.method.to_string(),
        "path": parts.uri.path(),
        "query": parts.uri.query().unwrap_or_default(),
        "headers": headers,
        "bodyText": String::from_utf8_lossy(&body),
    });

    (
        [(
            header::HeaderName::from_static("x-upstream"),
            header::HeaderValue::from_static("python-fake"),
        )],
        Json(response),
    )
}

fn lowercase_headers(headers: &HeaderMap) -> serde_json::Map<String, Value> {
    headers
        .iter()
        .map(|(name, value)| {
            (
                name.as_str().to_ascii_lowercase(),
                Value::String(value.to_str().unwrap_or_default().to_string()),
            )
        })
        .collect()
}
