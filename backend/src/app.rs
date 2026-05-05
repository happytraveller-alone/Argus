use axum::{routing::any, Router};

use crate::{routes, runtime::cubesandbox::ShutdownGate, state::AppState};

/// Build the application router.
///
/// The caller is responsible for providing the `shutdown_gate` that submission
/// handlers extract via `Extension<ShutdownGate>`. A single Extension mount
/// here ensures there is no layer-ordering ambiguity (axum 0.8 onion model).
pub fn build_router(state: AppState, shutdown_gate: ShutdownGate) -> Router {
    Router::new()
        .merge(routes::owned_routes())
        .fallback(any(|| async {
            (
                axum::http::StatusCode::NOT_FOUND,
                "route not owned by rust gateway",
            )
        }))
        .with_state(state)
        .layer(axum::Extension(shutdown_gate))
}
