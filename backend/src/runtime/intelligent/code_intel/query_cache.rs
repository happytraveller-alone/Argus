//! Per-query disk + in-memory cache for codegraph CLI results.
//!
//! Layered on top of [`cache::CodeGraphCache`] (which only caches the SQLite
//! index DB). This module caches the actual CLI query results so repeat lookups
//! within a run (or across runs against the same archive) skip the Podman exec
//! round-trip entirely.
//!
//! # Key shape
//! `(archive_sha256, tool_name, sha256(canonical_args_json))`
//!
//! # Layout under `{codegraph_data_root}/query-cache/`
//! ```text
//! {archive_sha}/{tool}/{args_sha}.json
//! ```
//!
//! In-memory layer: `Mutex<HashMap<String, Arc<String>>>` keyed by the same
//! triple flattened to `"{archive_sha}:{tool}:{args_sha}"`. Memory hits skip
//! the filesystem entirely.
//!
//! Failures are non-fatal — a cache miss just runs the underlying CLI call.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use serde::de::DeserializeOwned;
use serde::Serialize;
use sha2::{Digest, Sha256};
use tokio::sync::Mutex;
use tracing::debug;

/// Soft cap on in-memory cache entries. When exceeded, an arbitrary entry is
/// dropped (HashMap iteration order is effectively random) on each new insert
/// — disk layer remains intact, so this only forces a one-time disk roundtrip
/// for evicted keys on next access. Prevents unbounded memory growth in
/// long-lived scans that query thousands of distinct symbols.
const MEMORY_CAP_ENTRIES: usize = 1024;

/// Per-query result cache. Cheap to clone (all fields are `Arc`).
#[derive(Clone)]
pub struct QueryCache {
    archive_sha: Arc<str>,
    root: Arc<PathBuf>,
    memo: Arc<Mutex<HashMap<String, Arc<String>>>>,
}

impl QueryCache {
    pub fn new(root: PathBuf, archive_sha: String) -> Self {
        Self {
            archive_sha: archive_sha.into(),
            root: Arc::new(root),
            memo: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Hash a serializable args value into a stable cache key fragment.
    ///
    /// All current callers pass primitive tuples / `&str`, which `serde_json`
    /// never fails on. Treat that as a hard invariant — a panic here would
    /// indicate a misuse of the cache (e.g., a struct with custom Serialize
    /// that errors), and silently degrading would create cross-key collisions.
    fn args_hash<A: Serialize>(args: &A) -> String {
        let canonical = serde_json::to_string(args)
            .expect("QueryCache args must serialize (callers use primitive tuples)");
        let mut hasher = Sha256::new();
        hasher.update(canonical.as_bytes());
        hex_encode(hasher.finalize().as_slice())
    }

    fn memory_key(&self, tool: &str, args_sha: &str) -> String {
        format!("{}:{}:{}", &*self.archive_sha, tool, args_sha)
    }

    fn disk_path(&self, tool: &str, args_sha: &str) -> PathBuf {
        self.root
            .join(self.archive_sha.as_ref())
            .join(tool)
            .join(format!("{args_sha}.json"))
    }

    /// Look up a cached result, deserializing into `T`. Returns `Ok(None)` on
    /// memory + disk miss. Returns `Ok(None)` (logged) when a stored entry
    /// fails to deserialize — treats stale entries as misses.
    pub async fn get<T: DeserializeOwned, A: Serialize>(
        &self,
        tool: &str,
        args: &A,
    ) -> Option<T> {
        let args_sha = Self::args_hash(args);
        let mem_key = self.memory_key(tool, &args_sha);

        // Memory hit.
        {
            let memo = self.memo.lock().await;
            if let Some(raw) = memo.get(&mem_key) {
                if let Ok(value) = serde_json::from_str::<T>(raw.as_str()) {
                    return Some(value);
                }
            }
        }

        // Disk hit.
        let path = self.disk_path(tool, &args_sha);
        match tokio::fs::read_to_string(&path).await {
            Ok(raw) => match serde_json::from_str::<T>(&raw) {
                Ok(value) => {
                    let mut memo = self.memo.lock().await;
                    memo.insert(mem_key, Arc::new(raw));
                    Some(value)
                }
                Err(e) => {
                    debug!(path = %path.display(), error = %e, "query-cache: stale entry, treating as miss");
                    None
                }
            },
            Err(_) => None,
        }
    }

    /// Store a result in memory + on disk. Best-effort — IO errors only logged.
    pub async fn put<T: Serialize, A: Serialize>(&self, tool: &str, args: &A, value: &T) {
        let args_sha = Self::args_hash(args);
        let mem_key = self.memory_key(tool, &args_sha);
        let raw = match serde_json::to_string(value) {
            Ok(s) => s,
            Err(e) => {
                debug!(error = %e, tool, "query-cache: serialize failed; skipping put");
                return;
            }
        };

        // Memory (with soft cap to prevent unbounded growth).
        {
            let mut memo = self.memo.lock().await;
            if memo.len() >= MEMORY_CAP_ENTRIES && !memo.contains_key(&mem_key) {
                // Drop one arbitrary entry. HashMap iteration order is
                // effectively random which approximates a cheap eviction.
                if let Some(victim_key) = memo.keys().next().cloned() {
                    memo.remove(&victim_key);
                }
            }
            memo.insert(mem_key, Arc::new(raw.clone()));
        }

        // Disk (best-effort).
        let path = self.disk_path(tool, &args_sha);
        if let Some(parent) = path.parent() {
            if let Err(e) = tokio::fs::create_dir_all(parent).await {
                debug!(parent = %parent.display(), error = %e, "query-cache: mkdir failed; skipping disk put");
                return;
            }
        }
        let tmp = path.with_extension("tmp");
        if let Err(e) = tokio::fs::write(&tmp, raw.as_bytes()).await {
            debug!(path = %tmp.display(), error = %e, "query-cache: write tmp failed");
            // Best-effort cleanup; ignore failure (file may not exist).
            let _ = tokio::fs::remove_file(&tmp).await;
            return;
        }
        if let Err(e) = tokio::fs::rename(&tmp, &path).await {
            debug!(path = %path.display(), error = %e, "query-cache: rename failed");
            // Remove the orphaned tmp so it doesn't pile up across runs.
            let _ = tokio::fs::remove_file(&tmp).await;
        }
    }
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Deserialize;

    #[derive(Serialize, Deserialize, PartialEq, Debug)]
    struct Args {
        symbol: String,
        depth: u32,
    }

    #[derive(Serialize, Deserialize, PartialEq, Debug)]
    struct Payload {
        callers: Vec<String>,
    }

    #[tokio::test]
    async fn memory_then_disk_hit() {
        let dir = tempfile::tempdir().unwrap();
        let cache = QueryCache::new(dir.path().to_path_buf(), "sha-abc".to_string());

        let args = Args {
            symbol: "foo".into(),
            depth: 1,
        };
        let payload = Payload {
            callers: vec!["a".into(), "b".into()],
        };

        // Miss on cold cache.
        let miss: Option<Payload> = cache.get("callers", &args).await;
        assert!(miss.is_none());

        // Put.
        cache.put("callers", &args, &payload).await;

        // Hit (memory).
        let hit: Option<Payload> = cache.get("callers", &args).await;
        assert_eq!(hit, Some(payload));

        // Hit (cold memory but warm disk) — simulate by constructing a fresh cache.
        let cache2 = QueryCache::new(dir.path().to_path_buf(), "sha-abc".to_string());
        let disk_hit: Option<Payload> = cache2.get("callers", &args).await;
        assert!(disk_hit.is_some());
    }

    #[test]
    fn args_hash_is_stable() {
        let a1 = Args {
            symbol: "x".into(),
            depth: 2,
        };
        let a2 = Args {
            symbol: "x".into(),
            depth: 2,
        };
        let a3 = Args {
            symbol: "y".into(),
            depth: 2,
        };
        assert_eq!(QueryCache::args_hash(&a1), QueryCache::args_hash(&a2));
        assert_ne!(QueryCache::args_hash(&a1), QueryCache::args_hash(&a3));
    }
}
