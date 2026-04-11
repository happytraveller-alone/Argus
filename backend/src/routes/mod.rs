pub mod projects;
pub mod search;
pub mod skills;
pub mod system_config;

use axum::{routing::get, Json, Router};
use serde_json::json;

use crate::state::AppState;

pub fn owned_routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(health))
        .nest("/api/v1/system-config", system_config::router())
        .nest("/api/v1/projects", projects::router())
        .nest("/api/v1/search", search::router())
        .nest("/api/v1/skills", skills::router())
}

async fn health() -> Json<serde_json::Value> {
    Json(json!({
        "status": "ok",
        "service": "backend-rust"
    }))
}
