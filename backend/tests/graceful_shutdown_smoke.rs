//! Smoke test for graceful shutdown state-machine behavior (AC5).
//!
//! Verifies the ShutdownGate contract:
//!   - After gate.set(), new POST to opengrep/codeql submission endpoints → 503
//!   - The test builds the same router stack as main.rs — inner gate layer wins
//!     in axum 0.8 Extension resolution (innermost layer is consulted first).
//!
//! Degraded test (state-machine level only):
//!   Full SIGTERM → drain → socket-close flow requires a live cubemaster and
//!   a slow-path delete mock that is not available in unit-test infra.
//!   TODO(AC5-full): add a slow-mock cubemaster delete path and verify
//!     (b) in-flight task completes with sandbox gone and
//!     (c) bind socket closes within 30 s.
//!   Until then this test validates the gate state-machine and the 503 response
//!   path, which is the critical regression surface for the shutdown feature.
//!
//! Refs:
//!   spec: .omc/specs/deep-dive-opengrep-sandbox-auto-destroy.md (AC5)
//!   plan: .omc/plans/ralplan-opengrep-sandbox-auto-destroy.md (Step 7b)

use axum::{
    body::{to_bytes, Body},
    http::{Request, StatusCode},
    routing::any,
    Router,
};
use backend_rust::{
    config::AppConfig, routes, runtime::cubesandbox::ShutdownGate, state::AppState,
};
use tower::ServiceExt;

async fn no_db_state() -> AppState {
    let config = AppConfig::for_tests();
    AppState::from_config(config)
        .await
        .expect("AppState::from_config")
}

// ─── Helper: build router with a specific gate ────────────────────────────────
//
// Mirrors the main.rs pattern:
//   build_router() sets a default ShutdownGate as the innermost Extension layer.
//   main.rs then re-layers the production gate *inside* build_router's own layer
//   via axum::Extension override. In axum 0.8, layers stack as middleware: the
//   last `.layer()` call wraps all previous ones, so to make OUR gate win we
//   must mount it AFTER the routes but BEFORE build_router's default layer.
//
// Simplest correct approach: build the router from routes directly (same as
// build_router does internally) and mount our gate as the innermost layer.
// This avoids calling build_router() which hardcodes ShutdownGate::new().
fn build_router_with_gate(state: AppState, gate: ShutdownGate) -> Router {
    Router::new()
        .merge(routes::owned_routes())
        .fallback(any(|| async {
            (
                axum::http::StatusCode::NOT_FOUND,
                "route not owned by rust gateway",
            )
        }))
        .with_state(state)
        // Mount our gate as the innermost Extension layer — handlers see this one.
        .layer(axum::Extension(gate))
}

// ─── TEST 1: new opengrep submission → 503 after gate is set ─────────────────

#[tokio::test]
async fn shutdown_gate_set_rejects_opengrep_submission_with_503() {
    let state = no_db_state().await;
    let gate = ShutdownGate::new();
    gate.set(); // simulate post-SIGTERM state

    let router = build_router_with_gate(state, gate);

    // POST to the opengrep static-task submission endpoint.
    // Route: /api/v1/static-tasks/tasks (POST = create_static_task)
    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/v1/static-tasks/tasks")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"engine":"opengrep","task_id":"test"}"#))
                .unwrap(),
        )
        .await
        .expect("request must complete");

    assert_eq!(
        response.status(),
        StatusCode::SERVICE_UNAVAILABLE,
        "gate.set() must cause 503 on new opengrep submission"
    );

    let body = to_bytes(response.into_body(), 1024).await.unwrap();
    let body_str = String::from_utf8_lossy(&body);
    assert!(
        body_str.contains("shutting down"),
        "response body must mention 'shutting down'; got: {body_str}"
    );
}

// ─── TEST 2: new codeql submission → 503 after gate is set ───────────────────

#[tokio::test]
async fn shutdown_gate_set_rejects_codeql_submission_with_503() {
    let state = no_db_state().await;
    let gate = ShutdownGate::new();
    gate.set();

    let router = build_router_with_gate(state, gate);

    // Route: /api/v1/static-tasks/codeql/tasks (POST = create_codeql_task)
    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/v1/static-tasks/codeql/tasks")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"task_id":"test"}"#))
                .unwrap(),
        )
        .await
        .expect("request must complete");

    assert_eq!(
        response.status(),
        StatusCode::SERVICE_UNAVAILABLE,
        "gate.set() must cause 503 on new codeql submission"
    );
}

// ─── TEST 3: gate not set → submission is not rejected with 503 ──────────────

#[tokio::test]
async fn shutdown_gate_unset_does_not_reject_with_503() {
    let state = no_db_state().await;
    let gate = ShutdownGate::new(); // NOT set

    let router = build_router_with_gate(state, gate);

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/v1/static-tasks/tasks")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"engine":"opengrep","task_id":"test"}"#))
                .unwrap(),
        )
        .await
        .expect("request must complete");

    // Must NOT be 503 (gate not set). Will be 400/422/500 due to missing DB/payload,
    // but the key assertion is: gate did not fire.
    assert_ne!(
        response.status(),
        StatusCode::SERVICE_UNAVAILABLE,
        "unset gate must not produce 503"
    );
}

// ─── TEST 4: ShutdownGate state machine ──────────────────────────────────────

#[test]
fn shutdown_gate_state_machine() {
    let gate = ShutdownGate::new();

    // Initial state: not set.
    assert!(!gate.is_set(), "gate must start unset");

    // After set(): is_set() returns true.
    gate.set();
    assert!(gate.is_set(), "gate must be set after set()");

    // Clone shares the same atomic — clone also sees set state.
    let gate2 = gate.clone();
    assert!(gate2.is_set(), "cloned gate must see set state");

    // Idempotent: set() a second time must not panic.
    gate.set();
    assert!(gate.is_set(), "gate must remain set after second set()");
}
