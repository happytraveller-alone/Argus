use axum::{routing::any, Router};

use crate::{routes, state::AppState};

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
}
