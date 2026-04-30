pub mod agent_tasks;
pub mod agent_test;
pub mod projects;
pub mod search;
pub mod skills;
pub mod static_tasks;
pub mod system_config;

use axum::extract::State;
use axum::{routing::get, Json, Router};
use serde_json::json;

use crate::state::AppState;

pub fn owned_routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(health))
        .route(
            "/api/v1/agent-tasks/",
            axum::routing::post(agent_tasks::create_agent_task).get(agent_tasks::list_agent_tasks),
        )
        .nest("/api/v1/agent-tasks", agent_tasks::router())
        .nest("/api/v1/agent-test", agent_test::router())
        .nest("/api/v1/system-config", system_config::router())
        .nest("/api/v1/projects", projects::router())
        .nest("/api/v1/search", search::router())
        .nest("/api/v1/skills", skills::router())
        .nest("/api/v1/static-tasks", static_tasks::router())
}

async fn health(State(state): State<AppState>) -> Json<serde_json::Value> {
    // Keep the legacy top-level keys stable, but include richer startup state.
    // Bootstrap is stored in AppState and set from main.rs (and in tests).
    // If bootstrap hasn't run yet, we still return the "not_run" report.
    //
    // NOTE: This handler currently does not perform any checks itself, it only
    // reports the last known bootstrap state.
    //
    // We don't need to lock file_store_lock here, as this is just a report.
    // Reads are cheap.
    let bootstrap = state.bootstrap.read().await.clone();

    Json(json!({
        "status": bootstrap.overall,
        "service": "backend-rust",
        "bootstrap": bootstrap,
    }))
}
