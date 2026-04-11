use axum::{routing::any, Router};

use crate::{proxy, routes, state::AppState};

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .merge(routes::owned_routes())
        .route("/api/v1/{*path}", any(proxy::proxy_unmigrated_api))
        .fallback(any(|| async { proxy::not_owned_response() }))
        .with_state(state)
}
