//! Phase C.1 — Concrete `Sandbox` + `SandboxFactory` implementations for a3s-box.
//!
//! ## Design (Option C.β — image-cache-only standby)
//!
//! The a3s-box runtime model is single-shot: `a3s-box run` boots the microVM,
//! executes the entrypoint, and exits (with `--rm`).  There is no separate
//! `start`/`pause`/`resume`/`exec` lifecycle, so a pre-booted idle VM cannot
//! be maintained in the pool.
//!
//! Instead, the pool's "standby" unit is a **warm image cache entry**: the
//! Docker→OCI conversion run by `ensure_a3s_box_image_cached` (which takes
//! 30–60 s on a cache miss) is pre-executed by the factory.  Each scan still
//! starts a fresh `a3s-box run` process, but skips the conversion entirely.
//!
//! See `.omc/reports/autopilot-phase-c0-probe.md` for the full C.0 probe
//! outcome and AC1 impact analysis.

use std::{path::PathBuf, pin::Pin, sync::Arc, time::Instant};

use anyhow::{Context, Result};
use tokio::sync::OwnedSemaphorePermit;

use crate::runtime::{
    a3s_box_runner,
    sandbox_pool::{OnShutdownDestroy, Sandbox, SandboxFactory, SandboxId},
};

// ── A3sBoxTemplateKind ────────────────────────────────────────────────────────

/// Discriminant for a3s-box pool slots.
///
/// a3s-box is a distinct runtime with its own image namespace.
#[derive(Clone, Copy, Eq, PartialEq, Hash, Debug)]
pub enum A3sBoxTemplateKind {
    /// opengrep scanner running on a3s-box (the only variant today).
    OpengrepDedicated,
}

// ── A3sBoxHandle ──────────────────────────────────────────────────────────────

/// A pre-warmed a3s-box pool entry.
///
/// Represents proof that the OCI image cache is warm for `image`.  Holding
/// this handle means `ensure_a3s_box_image_cached` has already run
/// successfully, so the next `execute()` call skips the Docker→OCI conversion.
///
/// This is an image-cache-only standby (Option C.β).  No running microVM is
/// held; the VM is started fresh at scan dispatch time.
pub struct A3sBoxHandle {
    /// a3s-box image name that is pre-warmed in the cache.
    pub image: String,
    /// Template kind this handle belongs to.
    pub kind: A3sBoxTemplateKind,
    /// Absolute path to the marker file written by `ensure_a3s_box_image_cached`.
    /// Present means the cache is valid.
    pub cache_marker_path: PathBuf,
    /// Wall-clock time this handle was created (for observability).
    pub created_at: Instant,
}

impl Sandbox for A3sBoxHandle {
    type TemplateKind = A3sBoxTemplateKind;

    fn id(&self) -> SandboxId {
        // Use the image name as the "id" — there is no running VM to identify.
        self.image.clone()
    }
}

// ── A3sBoxFactory ─────────────────────────────────────────────────────────────

/// Creates new `A3sBoxHandle` instances on behalf of `SandboxPool`.
///
/// `create()` calls `ensure_a3s_box_image_cached` on a blocking thread, holds
/// the creation-slot permit until the conversion completes, then returns a
/// handle with proof of cache warmth.
pub struct A3sBoxFactory {
    /// a3s-box image name to pre-warm (e.g. "argus/opengrep-runner:latest").
    pub image: String,
}

impl SandboxFactory<A3sBoxHandle> for A3sBoxFactory {
    fn create<'a>(
        &'a self,
        kind: A3sBoxTemplateKind,
        permit: OwnedSemaphorePermit,
    ) -> Pin<Box<dyn std::future::Future<Output = Result<A3sBoxHandle>> + Send + 'a>> {
        let image = self.image.clone();
        Box::pin(async move {
            // Run the blocking Docker→OCI conversion off the async executor.
            // The permit is held for the duration and dropped at the end of
            // this async block, releasing the creation slot.
            let image_clone = image.clone();
            let cache_marker_path = tokio::task::spawn_blocking(move || -> Result<PathBuf> {
                a3s_box_runner::ensure_image_cached_for_pool(&image_clone).with_context(|| {
                    format!("A3sBoxFactory: ensure image cached for {image_clone}")
                })
            })
            .await
            .context("A3sBoxFactory: spawn_blocking panicked")?
            .with_context(|| format!("A3sBoxFactory: image cache warmup failed for {image}"))?;

            // Permit is intentionally kept alive until here so the semaphore
            // slot is not released before the work is done.
            drop(permit);

            tracing::info!(
                stage = "standby_created",
                kind = ?kind,
                image = %image,
                cache_marker = %cache_marker_path.display(),
                "a3s-box image cache warmed (Option C.β standby ready)"
            );

            Ok(A3sBoxHandle {
                image,
                kind,
                cache_marker_path,
                created_at: Instant::now(),
            })
        })
    }
}

// ── Shutdown destroy callback ─────────────────────────────────────────────────

/// Build the `OnShutdownDestroy` callback for the a3s-box pool.
///
/// Option C.β standby entries are just warm cache markers — there are no
/// running VMs to destroy.  The callback is a no-op but logs for observability.
pub fn a3s_box_on_shutdown_destroy() -> OnShutdownDestroy<A3sBoxHandle> {
    Arc::new(|handles: Vec<A3sBoxHandle>| {
        Box::pin(async move {
            if !handles.is_empty() {
                tracing::info!(
                    count = handles.len(),
                    "a3s-box pool shutdown: discarding {} warm-cache standby handle(s) \
                     (no VMs to destroy — Option C.β image-cache-only)",
                    handles.len()
                );
            }
            Ok(())
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a3s_box_template_kind_eq_hash() {
        use std::collections::HashMap;
        let mut map = HashMap::new();
        map.insert(A3sBoxTemplateKind::OpengrepDedicated, 1usize);
        assert_eq!(map[&A3sBoxTemplateKind::OpengrepDedicated], 1);
    }

    #[test]
    fn a3s_box_handle_id_is_image_name() {
        let handle = A3sBoxHandle {
            image: "argus/opengrep-runner:test".to_string(),
            kind: A3sBoxTemplateKind::OpengrepDedicated,
            cache_marker_path: PathBuf::from("/tmp/marker"),
            created_at: Instant::now(),
        };
        assert_eq!(handle.id(), "argus/opengrep-runner:test");
    }
}
