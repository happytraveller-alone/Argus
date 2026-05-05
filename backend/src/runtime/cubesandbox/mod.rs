pub mod client;
pub mod config;
pub mod cubemaster_client;
pub mod helper;
pub mod reconcile;
pub mod task;
pub mod template_provisioner;
pub mod types;

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

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
