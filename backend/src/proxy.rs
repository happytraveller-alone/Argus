use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{header::HOST, HeaderMap, HeaderName, HeaderValue, Request, Response, StatusCode},
};

use crate::{error::ApiError, state::AppState};

const HOP_BY_HOP_HEADERS: &[&str] = &[
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
];

pub async fn proxy_unmigrated_api(
    State(state): State<AppState>,
    request: Request<Body>,
) -> Result<Response<Body>, ApiError> {
    let Some(base_url) = &state.config.python_upstream_base_url else {
        return Err(ApiError::NotFound(
            "route not owned by rust gateway".to_string(),
        ));
    };

    let (parts, body) = request.into_parts();
    let path_and_query = parts
        .uri
        .path_and_query()
        .map(|value| value.as_str())
        .unwrap_or(parts.uri.path());
    let upstream_url = format!("{}{}", base_url.trim_end_matches('/'), path_and_query);
    let body_bytes = to_bytes(body, usize::MAX)
        .await
        .map_err(|error| ApiError::BadRequest(format!("failed to read request body: {error}")))?;

    let mut upstream_request = state
        .http_client
        .request(parts.method.clone(), upstream_url);
    upstream_request = upstream_request.body(body_bytes);
    upstream_request = upstream_request.headers(filtered_request_headers(&parts.headers));

    let upstream_response = upstream_request
        .send()
        .await
        .map_err(|error| ApiError::Upstream(format!("failed to reach python upstream: {error}")))?;

    let status = upstream_response.status();
    let headers = upstream_response.headers().clone();
    let stream = upstream_response.bytes_stream();

    let mut response = Response::new(Body::from_stream(stream));
    *response.status_mut() = status;
    copy_response_headers(response.headers_mut(), &headers);
    Ok(response)
}

fn filtered_request_headers(headers: &HeaderMap) -> HeaderMap {
    let mut filtered = HeaderMap::new();
    for (name, value) in headers {
        if name == HOST || is_hop_by_hop(name) {
            continue;
        }
        filtered.append(name.clone(), value.clone());
    }
    filtered
}

fn copy_response_headers(target: &mut HeaderMap<HeaderValue>, source: &HeaderMap<HeaderValue>) {
    for (name, value) in source {
        if is_hop_by_hop(name) {
            continue;
        }
        target.append(name.clone(), value.clone());
    }
}

fn is_hop_by_hop(name: &HeaderName) -> bool {
    HOP_BY_HOP_HEADERS
        .iter()
        .any(|candidate| name.as_str().eq_ignore_ascii_case(candidate))
}

pub fn not_owned_response() -> Response<Body> {
    let mut response = Response::new(Body::from("route not owned by rust gateway"));
    *response.status_mut() = StatusCode::NOT_FOUND;
    response
}
