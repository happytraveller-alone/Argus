pub mod client;
pub mod config;
pub mod cubemaster_client;
pub mod helper;
pub mod pool;
pub mod reconcile;
pub mod task;
pub mod template_provisioner;
pub mod types;

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;

/// Gate that submission handlers check before accepting new tasks.
/// Cloned cheaply (Arc inside); `set()` is called by the signal handler
/// before axum begins its graceful-shutdown drain.
#[derive(Clone, Default)]
pub struct ShutdownGate(Arc<AtomicBool>);

impl ShutdownGate {
    pub fn new() -> Self {
        Self(Arc::new(AtomicBool::new(false)))
    }
    pub fn set(&self) {
        self.0.store(true, Ordering::SeqCst);
    }
    pub fn is_set(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

// ── In-flight scan counter ────────────────────────────────────────────────────
//
// Counts opengrep + codeql scan tasks that have been spawned via tokio::spawn
// but have not yet finished their always-cleanup block (best_effort_delete_sandbox).
// Used by wait_for_active_scans_drain to hold shutdown_signal open until all
// in-flight scans complete or the hard timeout is reached.
//
// Option A (global AtomicUsize) was chosen over Option B (live_tasks map) because
// the cubesandbox task.rs live_tasks tracks arbitrary code-execution tasks, not
// opengrep/codeql scans. The scans are dispatched directly via tokio::spawn in
// routes/static_tasks.rs; there is no existing map to reuse.

static ACTIVE_SCAN_COUNT: AtomicUsize = AtomicUsize::new(0);

/// RAII guard: increments ACTIVE_SCAN_COUNT on creation, decrements on drop.
/// Drop runs even on panic, keeping the counter accurate.
///
/// Usage inside the spawned scan future:
///   let _guard = ActiveScanGuard::enter();
#[cfg_attr(not(any(test, feature = "test-helpers")), allow(dead_code))]
pub struct ActiveScanGuard;

impl ActiveScanGuard {
    pub fn enter() -> Self {
        ACTIVE_SCAN_COUNT.fetch_add(1, Ordering::SeqCst);
        Self
    }
}

impl Drop for ActiveScanGuard {
    fn drop(&mut self) {
        ACTIVE_SCAN_COUNT.fetch_sub(1, Ordering::SeqCst);
    }
}

/// Poll until all in-flight scan tasks have finished or `timeout` elapses.
///
/// Called by `shutdown_signal` (main.rs) after the ShutdownGate is set, so
/// axum's graceful-shutdown future does not resolve until every spawned scan
/// future has run its cleanup block (best_effort_delete_sandbox).
///
/// On timeout, logs a warning and returns — remaining sandboxes are reaped by
/// the reconcile orphan checker and argus-shutdown.sh.
pub async fn wait_for_active_scans_drain(timeout: tokio::time::Duration) {
    let deadline = tokio::time::Instant::now() + timeout;
    while ACTIVE_SCAN_COUNT.load(Ordering::SeqCst) > 0 {
        if tokio::time::Instant::now() >= deadline {
            tracing::warn!(
                remaining = ACTIVE_SCAN_COUNT.load(Ordering::SeqCst),
                "shutdown drain timed out; forcing exit. \
                 orphan sandboxes will be reaped by reconcile / argus-shutdown.sh"
            );
            return;
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(200)).await;
    }
    tracing::info!("all in-flight scans drained cleanly");
}

/// Best-effort sandbox deletion: log structured error on failure, never propagate.
///
/// Used by both opengrep and codeql scan paths to satisfy spec constraint 5
/// ("delete_sandbox failure must never poison the business result, but must
/// never be silent"). Log shape is fixed — sandbox_id / task_id / stage / error —
/// so CI grep + dashboards remain stable.
pub async fn best_effort_delete_sandbox(
    client: &client::CubeSandboxClient,
    sandbox_id: &str,
    task_id: &str,
    stage: &'static str,
) {
    if let Err(error) = client.delete_sandbox(sandbox_id).await {
        tracing::error!(
            sandbox_id = %sandbox_id,
            task_id = %task_id,
            stage = %stage,
            %error,
            "delete_sandbox failed; best-effort cleanup"
        );
    }
}
