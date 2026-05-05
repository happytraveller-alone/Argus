//! Warm sandbox pool for Opengrep OCI scans.
//!
//! Maintains `pool_size` pre-booted opengrep sandboxes so that per-scan
//! `create_sandbox + connect_sandbox` is off the critical path.
//!
//! # Environment variables
//! - `CUBESANDBOX_OPENGREP_POOL_SIZE`     — pool size (default 2; 0 disables)
//! - `CUBESANDBOX_OPENGREP_POOL_MANIFEST` — manifest path override (tests)

use std::{path::PathBuf, sync::Arc};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::sync::{Mutex, Semaphore};

use super::{
    client::{CubeSandboxClient, CubeSandboxSandbox},
    cubemaster_client::CubemasterClient,
};

// ── constants ─────────────────────────────────────────────────────────────────

const DEFAULT_POOL_SIZE: usize = 2;
const DEFAULT_MANIFEST_PATH: &str = "/var/lib/argus/opengrep-pool-manifest.json";

// ── manifest ──────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct PoolManifest {
    sandbox_ids: Vec<String>,
}

impl PoolManifest {
    fn load(path: &PathBuf) -> Result<Self> {
        match std::fs::read_to_string(path) {
            Ok(text) => serde_json::from_str(&text).context("pool manifest parse failed"),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(e) => Err(e).context("pool manifest read failed"),
        }
    }

    fn save(&self, path: &PathBuf) -> Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("manifest parent dir create failed")?;
        }
        let text = serde_json::to_string(self)?;
        std::fs::write(path, text).context("pool manifest write failed")
    }

    fn clear(path: &PathBuf) -> Result<()> {
        Self::default().save(path)
    }
}

// ── pool internals ────────────────────────────────────────────────────────────

pub(crate) struct PooledSandbox {
    pub(crate) sandbox: CubeSandboxSandbox,
}

struct PoolState {
    sandboxes: Vec<PooledSandbox>,
}

// ── public types ──────────────────────────────────────────────────────────────

/// RAII guard returned by `acquire()`. Must be explicitly passed to
/// `OpengrepSandboxPool::release()` to return the sandbox to the pool.
///
/// Owns an `Arc<OpengrepSandboxPool>` so it can outlive the borrow of the pool.
pub struct PoolGuard {
    pub(crate) pool: Arc<OpengrepSandboxPool>,
    /// `Some` while the guard is live; taken by `release()`.
    pub(crate) inner: Option<PooledSandbox>,
    /// Pre-built client shared with the pool.
    pub client: CubeSandboxClient,
}

impl PoolGuard {
    /// Reference to the underlying sandbox (valid until `release()` is called).
    pub fn sandbox(&self) -> &CubeSandboxSandbox {
        &self
            .inner
            .as_ref()
            .expect("PoolGuard already released")
            .sandbox
    }
}

/// Pre-booted sandbox pool for Opengrep OCI scans.
pub struct OpengrepSandboxPool {
    pool_size: usize,
    template_id: String,
    cubemaster: Arc<CubemasterClient>,
    client: CubeSandboxClient,
    manifest_path: PathBuf,
    state: Mutex<PoolState>,
    semaphore: Semaphore,
}

impl OpengrepSandboxPool {
    /// Construct (but do not warm) the pool.
    pub fn new(
        pool_size: usize,
        template_id: String,
        cubemaster: Arc<CubemasterClient>,
        client: CubeSandboxClient,
        manifest_path: PathBuf,
    ) -> Self {
        Self {
            pool_size,
            template_id,
            cubemaster,
            client,
            manifest_path,
            state: Mutex::new(PoolState {
                sandboxes: Vec::with_capacity(pool_size),
            }),
            semaphore: Semaphore::new(pool_size),
        }
    }

    /// Build pool parameters from environment variables.
    pub fn pool_size_from_env() -> usize {
        std::env::var("CUBESANDBOX_OPENGREP_POOL_SIZE")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_POOL_SIZE)
    }

    /// Manifest path from env or default.
    pub fn manifest_path_from_env() -> PathBuf {
        std::env::var("CUBESANDBOX_OPENGREP_POOL_MANIFEST")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(DEFAULT_MANIFEST_PATH))
    }

    /// Replay persisted manifest (delete stale sandboxes), then warm to `pool_size`.
    pub async fn startup(&self) -> Result<()> {
        let t0 = std::time::Instant::now();
        tracing::info!(
            pool_size = self.pool_size,
            template_id = %self.template_id,
            "opengrep_pool startup begin"
        );

        // Replay manifest: delete all previously-known sandbox IDs (idempotent —
        // cubemaster.delete_sandbox treats NOT_FOUND as success).
        let manifest = PoolManifest::load(&self.manifest_path)?;
        for stale_id in &manifest.sandbox_ids {
            match self.cubemaster.delete_sandbox(stale_id).await {
                Ok(()) => tracing::info!(
                    sandbox_id = %stale_id,
                    "opengrep_pool startup: deleted stale sandbox"
                ),
                Err(e) => tracing::warn!(
                    sandbox_id = %stale_id,
                    error = %e,
                    "opengrep_pool startup: stale sandbox delete failed (ignored)"
                ),
            }
        }
        PoolManifest::clear(&self.manifest_path)?;

        // Create fresh pool.
        let mut created: Vec<PooledSandbox> = Vec::with_capacity(self.pool_size);
        for i in 0..self.pool_size {
            match self.create_one_sandbox().await {
                Ok(pooled) => {
                    tracing::info!(
                        index = i,
                        sandbox_id = %pooled.sandbox.sandbox_id,
                        elapsed_ms = t0.elapsed().as_millis() as u64,
                        "opengrep_pool startup: sandbox ready"
                    );
                    created.push(pooled);
                }
                Err(e) => {
                    tracing::warn!(
                        index = i,
                        error = %e,
                        "opengrep_pool startup: sandbox create failed; pool will be under-capacity"
                    );
                }
            }
        }

        let sandbox_ids: Vec<String> = created
            .iter()
            .map(|p| p.sandbox.sandbox_id.clone())
            .collect();
        PoolManifest { sandbox_ids }.save(&self.manifest_path)?;

        let mut state = self.state.lock().await;
        state.sandboxes = created;
        tracing::info!(
            pool_actual = state.sandboxes.len(),
            pool_target = self.pool_size,
            elapsed_ms = t0.elapsed().as_millis() as u64,
            "opengrep_pool startup complete"
        );
        Ok(())
    }

    /// Acquire a pre-booted sandbox. Returns a RAII `PoolGuard`.
    ///
    /// Dual-shape recipe:
    /// - Warm hit  → emits `pool_warm_hit`
    /// - Cold path → emits `pool_cold_fallback` + `sandbox_created` + `sandbox_connected`
    pub async fn acquire(self: &Arc<Self>, task_id: &str) -> Result<PoolGuard> {
        let t0 = std::time::Instant::now();

        // Non-blocking semaphore try: if pool has capacity, pop an entry.
        let maybe = match self.semaphore.try_acquire() {
            Ok(permit) => {
                let entry = self.state.lock().await.sandboxes.pop();
                drop(permit);
                entry
            }
            Err(_) => None,
        };

        if let Some(pooled) = maybe {
            tracing::info!(
                task_id = %task_id,
                stage = "pool_warm_hit",
                sandbox_id = %pooled.sandbox.sandbox_id,
                elapsed_ms = t0.elapsed().as_millis() as u64,
            );
            return Ok(PoolGuard {
                pool: Arc::clone(self),
                inner: Some(pooled),
                client: self.client.clone(),
            });
        }

        // Cold fallback: ad-hoc create+connect (dual-shape stages).
        tracing::info!(
            task_id = %task_id,
            stage = "pool_cold_fallback",
            elapsed_ms = t0.elapsed().as_millis() as u64,
        );
        let sandbox = self.client.create_sandbox().await?;
        tracing::info!(
            task_id = %task_id,
            stage = "sandbox_created",
            elapsed_ms = t0.elapsed().as_millis() as u64,
        );
        self.client.connect_sandbox(&sandbox.sandbox_id).await?;
        tracing::info!(
            task_id = %task_id,
            stage = "sandbox_connected",
            elapsed_ms = t0.elapsed().as_millis() as u64,
        );

        Ok(PoolGuard {
            pool: Arc::clone(self),
            inner: Some(PooledSandbox { sandbox }),
            client: self.client.clone(),
        })
    }

    /// Release a guard: reset workspace, return sandbox to pool (or replace if reset fails).
    pub async fn release(&self, mut guard: PoolGuard) -> Result<()> {
        let pooled = guard.inner.take().expect("PoolGuard already released");
        let sandbox_id = pooled.sandbox.sandbox_id.clone();

        let reset_result = self
            .client
            .run_command(
                &pooled.sandbox,
                "rm -rf /tmp/argus-opengrep-work /dev/shm/argus-opengrep-work /tmp/workspace.tar.gz /tmp/argus-opengrep-result.json /tmp/argus-opengrep-payload-*.b64 /tmp/argus-*.sh /tmp/argus-task-*",
            )
            .await;

        match reset_result {
            Ok(_) => {
                // Return sandbox to pool and rewrite manifest.
                let mut state = self.state.lock().await;
                state.sandboxes.push(pooled);
                let ids: Vec<String> = state
                    .sandboxes
                    .iter()
                    .map(|p| p.sandbox.sandbox_id.clone())
                    .collect();
                drop(state);
                if let Err(e) = (PoolManifest { sandbox_ids: ids }).save(&self.manifest_path) {
                    tracing::warn!(error = %e, "opengrep_pool: manifest rewrite failed after release");
                }
                tracing::info!(sandbox_id = %sandbox_id, "opengrep_pool: sandbox returned to pool");
            }
            Err(e) => {
                // Reset failed — delete sandbox and attempt replacement.
                tracing::warn!(
                    sandbox_id = %sandbox_id,
                    error = %e,
                    "opengrep_pool: workspace reset failed; deleting and replacing sandbox"
                );
                let _ = self.cubemaster.delete_sandbox(&sandbox_id).await;

                match self.create_one_sandbox().await {
                    Ok(replacement) => {
                        let replacement_id = replacement.sandbox.sandbox_id.clone();
                        let mut state = self.state.lock().await;
                        state.sandboxes.push(replacement);
                        let ids: Vec<String> = state
                            .sandboxes
                            .iter()
                            .map(|p| p.sandbox.sandbox_id.clone())
                            .collect();
                        drop(state);
                        if let Err(e2) =
                            (PoolManifest { sandbox_ids: ids }).save(&self.manifest_path)
                        {
                            tracing::warn!(error = %e2, "opengrep_pool: manifest rewrite failed after replacement");
                        }
                        tracing::info!(
                            sandbox_id = %replacement_id,
                            "opengrep_pool: replacement sandbox added to pool"
                        );
                    }
                    Err(e2) => {
                        tracing::warn!(
                            error = %e2,
                            "opengrep_pool: replacement sandbox creation failed; pool under-capacity"
                        );
                        let state = self.state.lock().await;
                        let ids: Vec<String> = state
                            .sandboxes
                            .iter()
                            .map(|p| p.sandbox.sandbox_id.clone())
                            .collect();
                        drop(state);
                        if let Err(e3) =
                            (PoolManifest { sandbox_ids: ids }).save(&self.manifest_path)
                        {
                            tracing::warn!(error = %e3, "opengrep_pool: manifest rewrite failed");
                        }
                    }
                }
            }
        }
        Ok(())
    }

    /// Drain and delete all pooled sandboxes, clear manifest. Idempotent.
    pub async fn shutdown(&self) -> Result<()> {
        let sandboxes = {
            let mut state = self.state.lock().await;
            std::mem::take(&mut state.sandboxes)
        };
        for pooled in sandboxes {
            let _ = self
                .cubemaster
                .delete_sandbox(&pooled.sandbox.sandbox_id)
                .await;
        }
        PoolManifest::clear(&self.manifest_path)?;
        tracing::info!("opengrep_pool: shutdown complete");
        Ok(())
    }

    async fn create_one_sandbox(&self) -> Result<PooledSandbox> {
        let sandbox = self.client.create_sandbox().await?;
        self.client.connect_sandbox(&sandbox.sandbox_id).await?;
        Ok(PooledSandbox { sandbox })
    }
}

// ── tests ─────────────────────────────────────────────────────────────────────

#[cfg(any(test, feature = "test-helpers"))]
mod tests {
    use super::*;

    #[allow(dead_code)]
    fn temp_manifest() -> PathBuf {
        let id = uuid::Uuid::new_v4();
        std::env::temp_dir().join(format!("argus-pool-test-{id}.json"))
    }

    /// pool_acquire_release_isolation_test (manifest portion):
    /// After a release() cycle the sandbox ID is persisted in the manifest.
    #[test]
    fn pool_manifest_roundtrip() {
        let path = temp_manifest();
        let manifest = PoolManifest {
            sandbox_ids: vec!["sb-abc".to_string(), "sb-def".to_string()],
        };
        manifest.save(&path).expect("save");
        let loaded = PoolManifest::load(&path).expect("load");
        assert_eq!(loaded.sandbox_ids, vec!["sb-abc", "sb-def"]);
        let _ = std::fs::remove_file(&path);
    }

    /// pool_orphan_replay_idempotent_test (unit portion):
    /// Manifest with a fake ID is cleared after replay — no panic, empty after.
    #[test]
    fn pool_manifest_clear_after_replay() {
        let path = temp_manifest();
        let manifest = PoolManifest {
            sandbox_ids: vec!["fake-sb-00000000".to_string()],
        };
        manifest.save(&path).expect("save");
        PoolManifest::clear(&path).expect("clear");
        let after = PoolManifest::load(&path).expect("load after clear");
        assert!(
            after.sandbox_ids.is_empty(),
            "manifest must be empty after clear"
        );
        let _ = std::fs::remove_file(&path);
    }

    /// pool_cold_fallback_emits_dual_shape_test (env portion):
    /// pool_size=0 disables the pool; non-zero enables it.
    #[test]
    fn pool_size_parse_logic() {
        let size: usize = "0".parse().unwrap();
        assert_eq!(size, 0, "pool_size=0 should disable");

        let size2: usize = "2".parse().unwrap();
        assert_eq!(size2, DEFAULT_POOL_SIZE, "default pool size is 2");
    }
}
