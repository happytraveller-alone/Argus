use axum::{routing::any, Router};

use crate::{routes, runtime::cubesandbox::ShutdownGate, state::AppState};

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .merge(routes::owned_routes())
        .fallback(any(|| async {
            (
                axum::http::StatusCode::NOT_FOUND,
                "route not owned by rust gateway",
            )
        }))
        .with_state(state)
        // Default gate so tests calling build_router(state) don't get MissingExtension
        // on POST submission handlers. main.rs overrides this with the production gate
        // (axum 0.8 last-mount-wins).
        .layer(axum::Extension(ShutdownGate::new()))
}
