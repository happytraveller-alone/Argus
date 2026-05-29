//! Public model-catalog proxy: `GET /api/v1/models`.
//!
//! Thin pass-through to the Node `agent-engine` sidecar's `/models` endpoint so
//! the frontend can list available models (ids, cost, context window, thinking
//! metadata) without the backend re-implementing pi's provider catalog. The
//! sidecar's `/models` response carries NO keys, and this proxy forwards the
//! body verbatim — it never injects or returns key material.
//!
//! Unlike `/internal/*`, this route is public (no shared-secret bearer): it
//! exposes only the catalog. The bearer token is used solely on the *outbound*
//! call to the sidecar.

use std::time::Duration;

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde_json::{json, Value};

use crate::state::AppState;

/// Outbound timeout for the sidecar `/models` fetch.
const SIDECAR_MODELS_TIMEOUT: Duration = Duration::from_secs(10);

/// Build the public `/api/v1/models` router.
pub fn router() -> Router<AppState> {
    Router::new().route("/", get(get_models))
}

async fn get_models(State(state): State<AppState>) -> Response {
    let Some(base_url) = state
        .config
        .agent_engine_url
        .as_deref()
        .map(str::trim)
        .filter(|url| !url.is_empty())
    else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "error": "sidecar_unconfigured" })),
        )
            .into_response();
    };

    let url = format!("{}/models", base_url.trim_end_matches('/'));
    let mut request = state.http_client.get(url).timeout(SIDECAR_MODELS_TIMEOUT);
    if let Some(secret) = state
        .config
        .agent_engine_shared_secret
        .as_deref()
        .filter(|secret| !secret.is_empty())
    {
        request = request.bearer_auth(secret);
    }

    let response = match request.send().await {
        Ok(response) => response,
        Err(error) => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({
                    "error": "sidecar_unreachable",
                    "message": error.to_string(),
                })),
            )
                .into_response()
        }
    };

    // Forward the sidecar's status + JSON body (catalog only — no keys).
    let status = StatusCode::from_u16(response.status().as_u16())
        .unwrap_or(StatusCode::BAD_GATEWAY);
    match response.json::<Value>().await {
        Ok(body) => (status, Json(body)).into_response(),
        Err(error) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({
                "error": "sidecar_unreachable",
                "message": error.to_string(),
            })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        Router,
    };
    use http_body_util::BodyExt;
    use serde_json::Value;
    use tower::ServiceExt;

    use super::router;
    use crate::{config::AppConfig, state::AppState};

    async fn app_with_config(config: AppConfig) -> Router {
        let state = AppState::from_config(config)
            .await
            .expect("build AppState for tests");
        Router::new()
            .nest("/api/v1/models", router())
            .with_state(state)
    }

    #[tokio::test]
    async fn models_is_service_unavailable_when_sidecar_unconfigured() {
        let config = AppConfig::for_tests(); // agent_engine_url None
        let app = app_with_config(config).await;

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/models")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let bytes = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        let body: Value = serde_json::from_slice(&bytes).expect("json");
        assert_eq!(body["error"], "sidecar_unconfigured");
    }
}
