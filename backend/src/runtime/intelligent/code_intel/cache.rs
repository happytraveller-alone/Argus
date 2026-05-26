//! Flock-based hash-keyed cache for codegraph SQLite indexes.
//!
//! Stores a single `codegraph.db` file per archive SHA256, protected by an
//! advisory POSIX flock so concurrent scans of the same archive cannot corrupt
//! the cache entry.
//!
//! # Layout under `{codegraph_data_root()}/cache/`
//! ```text
//! {sha}.lock             — advisory flock file (shared=read, exclusive=write)
//! {sha}.tmp.{pid}/       — in-progress write staging directory
//! {sha}/codegraph.db     — committed cache entry
//! ```
//!
//! # Eviction
//! Not implemented. The cache grows unbounded until manually pruned.
//! A 10 GB soft cap and LRU eviction are deferred to a follow-up milestone.
//! Operators may run `find {root} -maxdepth 1 -type d -mtime +30 | xargs rm -rf`
//! as an interim measure.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
// fs2::FileExt methods called via fully-qualified syntax to avoid the
// std::os::unix::fs::FileExt name collision introduced in Rust 1.89.
use tokio::task::spawn_blocking;

fn codegraph_data_root() -> PathBuf {
    std::env::var("ARGUS_CODEGRAPH_DATA_DIR")
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| {
            std::env::var("SCAN_WORKSPACE_ROOT")
                .ok()
                .map(|value| PathBuf::from(value.trim()))
                .filter(|value| !value.as_os_str().is_empty())
                .unwrap_or_else(|| PathBuf::from("/tmp/argus-codegraph"))
                .join("codegraph")
        })
}

/// Concurrent-safe cache of codegraph SQLite indexes, keyed by archive SHA256.
pub struct CodeGraphCache {
    root: PathBuf,
}

impl CodeGraphCache {
    /// Create a new cache handle, ensuring the root directory exists.
    ///
    /// Cache root is `${ARGUS_CODEGRAPH_DATA_DIR}/cache/` when explicitly set;
    /// otherwise it defaults under `${SCAN_WORKSPACE_ROOT}/codegraph/cache/` so
    /// host Podman can bind-mount it from backend-container deployments.
    pub fn new() -> Result<Self> {
        let root = codegraph_data_root().join("cache");
        std::fs::create_dir_all(&root)
            .with_context(|| format!("create cache root {}", root.display()))?;
        Ok(Self { root })
    }

    /// Check for a cache hit.
    ///
    /// Acquires a shared flock on `{sha}.lock`, checks whether `{sha}/codegraph.db`
    /// exists, and if so copies it to `dest_dir/codegraph.db` (creating `dest_dir`
    /// if necessary).
    ///
    /// Returns `Some(dest_dir/codegraph.db)` on hit, `None` on miss.
    /// The flock is released when this function returns.
    pub async fn try_load(&self, sha: &str, dest_dir: &Path) -> Result<Option<PathBuf>> {
        let lock_path = self.root.join(format!("{sha}.lock"));
        let cached_db = self.root.join(sha).join("codegraph.db");
        let dest_dir = dest_dir.to_path_buf();

        spawn_blocking(move || -> Result<Option<PathBuf>> {
            // Open (or create) the lock file — shared lock for readers.
            let lock_file = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .open(&lock_path)
                .with_context(|| format!("open lock file {}", lock_path.display()))?;
            fs2::FileExt::lock_shared(&lock_file)
                .with_context(|| format!("acquire shared lock {}", lock_path.display()))?;

            let hit = cached_db.exists();
            if !hit {
                fs2::FileExt::unlock(&lock_file).ok();
                return Ok(None);
            }

            // Copy to dest_dir.
            std::fs::create_dir_all(&dest_dir)
                .with_context(|| format!("create dest_dir {}", dest_dir.display()))?;
            let dest_db = dest_dir.join("codegraph.db");
            std::fs::copy(&cached_db, &dest_db)
                .with_context(|| format!("copy {} → {}", cached_db.display(), dest_db.display()))?;

            fs2::FileExt::unlock(&lock_file).ok();
            Ok(Some(dest_db))
        })
        .await
        .context("try_load spawn_blocking")?
    }

    /// Atomically commit a codegraph database into the cache under `sha`.
    ///
    /// Acquires an exclusive flock on `{sha}.lock`, copies `src_db` into a
    /// per-PID staging directory, fsyncs the file, then renames the staging
    /// directory to the final `{sha}/` location. The flock is released on return.
    ///
    /// If the cache entry already exists (another process won the race), this
    /// function returns `Ok(())` without overwriting.
    pub async fn commit(&self, sha: &str, src_db: &Path) -> Result<()> {
        let lock_path = self.root.join(format!("{sha}.lock"));
        let tmp_dir = self.root.join(format!("{sha}.tmp.{}", std::process::id()));
        let final_dir = self.root.join(sha);
        let src_db = src_db.to_path_buf();

        spawn_blocking(move || -> Result<()> {
            let lock_file = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .open(&lock_path)
                .with_context(|| format!("open lock file {}", lock_path.display()))?;
            fs2::FileExt::lock_exclusive(&lock_file)
                .with_context(|| format!("acquire exclusive lock {}", lock_path.display()))?;

            // Another process may have committed while we waited.
            if final_dir.join("codegraph.db").exists() {
                fs2::FileExt::unlock(&lock_file).ok();
                return Ok(());
            }

            // Stage: write into tmp dir.
            if tmp_dir.exists() {
                std::fs::remove_dir_all(&tmp_dir).ok();
            }
            std::fs::create_dir_all(&tmp_dir)
                .with_context(|| format!("create tmp dir {}", tmp_dir.display()))?;

            let staged = tmp_dir.join("codegraph.db");
            std::fs::copy(&src_db, &staged)
                .with_context(|| format!("copy {} → {}", src_db.display(), staged.display()))?;

            // Fsync the file before rename.
            {
                let f = std::fs::File::open(&staged)
                    .with_context(|| format!("open staged {}", staged.display()))?;
                f.sync_all().context("fsync staged db")?;
            }

            // Atomic rename tmp → final.
            std::fs::rename(&tmp_dir, &final_dir).with_context(|| {
                format!("rename {} → {}", tmp_dir.display(), final_dir.display())
            })?;

            fs2::FileExt::unlock(&lock_file).ok();
            Ok(())
        })
        .await
        .context("commit spawn_blocking")?
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn temp_cache() -> (CodeGraphCache, tempfile::TempDir) {
        // Construct CodeGraphCache directly with an isolated tempdir-rooted path
        // — avoids mutating ARGUS_DATA_DIR which would race with parallel cargo
        // test runners (architect review #4 reservation).
        let dir = tempfile::tempdir().expect("tempdir");
        let cache = CodeGraphCache {
            root: dir.path().join("codegraph_cache"),
        };
        std::fs::create_dir_all(&cache.root).unwrap();
        (cache, dir)
    }

    #[tokio::test]
    async fn cache_miss_returns_none() {
        let (cache, _dir) = temp_cache();
        let dest = tempfile::tempdir().expect("dest");
        let result = cache.try_load("deadbeef", dest.path()).await.unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn commit_then_load_returns_path() {
        let (cache, _dir) = temp_cache();

        // Create a fake source db.
        let src_dir = tempfile::tempdir().expect("src");
        let src_db = src_dir.path().join("codegraph.db");
        let mut f = std::fs::File::create(&src_db).unwrap();
        writeln!(f, "fake sqlite content").unwrap();
        drop(f);

        let sha = "abc123";
        cache.commit(sha, &src_db).await.expect("commit");

        let dest = tempfile::tempdir().expect("dest");
        let result = cache.try_load(sha, dest.path()).await.expect("try_load");
        assert!(result.is_some());
        let db_path = result.unwrap();
        assert!(db_path.exists());
        assert_eq!(db_path.file_name().unwrap(), "codegraph.db");
    }

    #[tokio::test]
    async fn commit_idempotent_on_existing_entry() {
        let (cache, _dir) = temp_cache();

        let src_dir = tempfile::tempdir().expect("src");
        let src_db = src_dir.path().join("codegraph.db");
        std::fs::write(&src_db, b"v1").unwrap();

        let sha = "idempotent_sha";
        cache.commit(sha, &src_db).await.expect("first commit");

        // Overwrite src with different content, commit again — should not panic.
        std::fs::write(&src_db, b"v2").unwrap();
        cache.commit(sha, &src_db).await.expect("second commit ok");

        // Cached file still has original content (early-return on existing entry).
        let cached = cache.root.join(sha).join("codegraph.db");
        assert_eq!(std::fs::read(&cached).unwrap(), b"v1");
    }
}
