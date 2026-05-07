//! Phase A.2.1 — Concrete `Sandbox` + `SandboxFactory` implementations for cubesandbox.
//!
//! `CubesandboxHandle` wraps a single-use sandbox acquired from the pool.
//! `CubesandboxFactory` calls `create_sandbox` + `connect_sandbox` to provision
//! new standby sandboxes for the pool.
//!
//! Principle 1 (isolation > performance): every sandbox is single-use even when
//! acquired from the pool.  After the scan, `best_effort_delete_sandbox` is
//! called unconditionally — the sandbox is never returned to the pool.

use std::{future::Future, pin::Pin, sync::Arc, time::Instant};

use anyhow::{Context as _, Result};
use tokio::sync::OwnedSemaphorePermit;

use crate::{
    db::cubesandbox_templates::TemplateKind,
    runtime::{
        cubesandbox::{
            best_effort_delete_sandbox,
            client::{CubeSandboxClient, CubeSandboxClientConfig},
        },
        sandbox_pool::{OnShutdownDestroy, Sandbox, SandboxFactory, SandboxId},
    },
    state::AppState,
};

// ── CubesandboxHandle ─────────────────────────────────────────────────────────

/// A pre-warmed cubesandbox ready for source upload + scan.
///
/// Wraps the sandbox ID, template ID, kind, a shared client, and the wall-clock
/// timestamp of creation.  The client is stored here so cleanup code in the
/// scan path can call `best_effort_delete_sandbox` without needing the
/// `AppState`.
pub struct CubesandboxHandle {
    pub sandbox_id: String,
    pub template_id: String,
    pub kind: TemplateKind,
    /// Shared client — the pool keeps one per factory, scan paths borrow it.
    pub client: Arc<CubeSandboxClient>,
    pub created_at: Instant,
    /// Domain returned by `POST /sandboxes` (e.g. `cube.app`). The data-plane
    /// envd routing depends on this — without it `envd_host` bails with
    /// "missing sandbox domain". The cubelet `GET /sandboxes` listing does
    /// NOT include `domain`, so it must be captured at create time and
    /// preserved across the pool until the scan path consumes the handle.
    pub domain: Option<String>,
}

impl Sandbox for CubesandboxHandle {
    type TemplateKind = TemplateKind;

    fn id(&self) -> SandboxId {
        self.sandbox_id.clone()
    }
}

// ── CubesandboxFactory ────────────────────────────────────────────────────────

/// Creates new `CubesandboxHandle` instances on behalf of `SandboxPool`.
///
/// The factory uses `AppState` to resolve the template ID for the requested
/// kind, then calls `create_sandbox` + `connect_sandbox` via the shared client.
/// The `OwnedSemaphorePermit` (creation slot) is held until the sandbox is
/// fully connected, then dropped.
pub struct CubesandboxFactory {
    pub state: AppState,
    pub client: Arc<CubeSandboxClient>,
}

impl SandboxFactory<CubesandboxHandle> for CubesandboxFactory {
    fn create<'a>(
        &'a self,
        kind: TemplateKind,
        permit: OwnedSemaphorePermit,
    ) -> Pin<Box<dyn Future<Output = Result<CubesandboxHandle>> + Send + 'a>> {
        Box::pin(async move {
            // Resolve template_id from the DB for this kind.
            let template_id = resolve_template_id_for_kind(&self.state, kind).await
                .with_context(|| format!("CubesandboxFactory: resolve template_id for {kind:?}"))?;

            let client = Arc::clone(&self.client);

            // Create the sandbox (blocks until the VM is started on cubemaster).
            let sandbox = client
                .create_sandbox()
                .await
                .with_context(|| format!("CubesandboxFactory: create_sandbox for kind={kind:?} template={template_id}"))?;

            let sandbox_id = sandbox.sandbox_id.clone();
            let domain = sandbox.domain.clone();

            // Connect (waits for envd inside the VM to be ready).
            client
                .connect_sandbox(&sandbox_id)
                .await
                .with_context(|| format!("CubesandboxFactory: connect_sandbox {sandbox_id}"))?;

            // Drop the creation-slot permit — VM is ready, slot is freed.
            drop(permit);

            tracing::info!(
                stage = "standby_created",
                kind = ?kind,
                sandbox_id = %sandbox_id,
                template_id = %template_id,
                "new standby sandbox ready"
            );

            Ok(CubesandboxHandle {
                sandbox_id,
                template_id,
                kind,
                client,
                created_at: Instant::now(),
                domain,
            })
        })
    }
}

// ── Shutdown destroy callback ─────────────────────────────────────────────────

/// Build the `OnShutdownDestroy` callback used by `SandboxPool::shutdown()`.
///
/// Iterates over all remaining standby handles and calls
/// `best_effort_delete_sandbox` for each.  Errors are logged; the callback
/// never bails early.  The synthetic `task_id` tag ("pool_shutdown") allows
/// dashboards to identify these deletions.
pub fn cubesandbox_on_shutdown_destroy(
    client: Arc<CubeSandboxClient>,
) -> OnShutdownDestroy<CubesandboxHandle> {
    Arc::new(move |handles: Vec<CubesandboxHandle>| {
        let client = Arc::clone(&client);
        Box::pin(async move {
            for h in handles {
                best_effort_delete_sandbox(&client, &h.sandbox_id, "pool_shutdown", "pool_shutdown")
                    .await;
            }
            Ok(())
        })
    })
}

// ── Template resolution helper ────────────────────────────────────────────────

/// Resolve the active template ID for `kind` via the DB.
///
/// Uses `template_provisioner::resolve_existing_template_id` which returns the
/// most-recently-ready template for the given kind.  Returns an error when no
/// ready template exists (the pool will log the error and skip this slot).
async fn resolve_template_id_for_kind(state: &AppState, kind: TemplateKind) -> Result<String> {
    use crate::runtime::cubesandbox::{config::CubeSandboxConfig, template_provisioner};

    let config = CubeSandboxConfig::load_runtime(state)
        .await
        .context("load_runtime config")?
        .for_template_kind(kind, state.config.as_ref());

    let template_id = template_provisioner::resolve_existing_template_id(state, &config, kind)
        .await
        .context("resolve_existing_template_id")?
        .ok_or_else(|| {
            anyhow::anyhow!(
                "no ready template for kind={kind:?}; pool slot skipped until template is built"
            )
        })?;

    Ok(template_id)
}

/// Build a `CubeSandboxClient` from `AppState` config, shared via `Arc`.
///
/// Called once during pool bootstrap (A.3).  The client is shared by the
/// factory and by `cubesandbox_on_shutdown_destroy`.
pub fn build_pool_client(state: &AppState) -> Result<Arc<CubeSandboxClient>> {
    // Use the opengrep template slot as a placeholder template_id in the
    // client config.  The factory always re-resolves the real template_id from
    // the DB before calling create_sandbox, so this value is only used for the
    // health-check call (which doesn't need it).
    let config = state.config.as_ref();
    let client = CubeSandboxClient::new(CubeSandboxClientConfig {
        api_base_url: config.cubesandbox_api_base_url.clone(),
        data_plane_base_url: config.cubesandbox_data_plane_base_url.clone(),
        template_id: config.cubesandbox_opengrep_template_id.clone(),
        execution_timeout_seconds: config.cubesandbox_execution_timeout_seconds,
        cleanup_timeout_seconds: config.cubesandbox_cleanup_timeout_seconds,
        stdout_limit_bytes: config.cubesandbox_stdout_limit_bytes,
        stderr_limit_bytes: config.cubesandbox_stderr_limit_bytes,
    })
    .context("build_pool_client: CubeSandboxClient::new")?;
    Ok(Arc::new(client))
}
