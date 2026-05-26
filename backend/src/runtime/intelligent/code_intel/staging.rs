//! Host-side staging directory for codegraph source extraction.
//!
//! Extracts uploaded project archives into a hash-keyed directory that can be
//! bind-mounted read-only into the codegraph container.
//!
//! Layout: `${ARGUS_CODEGRAPH_DATA_DIR:-${SCAN_WORKSPACE_ROOT}/codegraph}/staging/{archive_sha256}/src/`

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use tracing::debug;

use crate::archive::extract_archive_path_to_directory;

/// A prepared staging directory containing extracted source files.
///
/// Removed from disk when dropped (RAII cleanup).
pub struct StagingDir {
    /// Path to the extracted source: `…/codegraph_staging/{sha}/src/`
    pub root: PathBuf,
    /// SHA-256 hex of the archive that was extracted here.
    pub archive_sha256: String,
    /// RAII guard — removes `…/codegraph_staging/{sha}/` on drop.
    _guard: TempCleanupGuard,
}

/// Extracts the archive at `archive_path` into a hash-keyed staging directory.
///
/// **Idempotent**: if the `src/` directory already exists for the given SHA,
/// no re-extraction is performed and the existing path is returned.
///
/// The returned `StagingDir` removes the staging tree when dropped.
pub async fn prepare(
    archive_path: &Path,
    archive_name: &str,
    archive_sha256: &str,
) -> Result<StagingDir> {
    let staging_root = build_staging_root(archive_sha256);
    let src_dir = staging_root.join("src");

    if src_dir.exists() {
        debug!(sha = archive_sha256, path = %src_dir.display(), "staging cache hit — skipping extraction");
        return Ok(StagingDir {
            root: src_dir,
            archive_sha256: archive_sha256.to_owned(),
            _guard: TempCleanupGuard { path: staging_root },
        });
    }

    tokio::fs::create_dir_all(&src_dir)
        .await
        .with_context(|| format!("failed to create staging dir: {}", src_dir.display()))?;

    // The codegraph container runs as a non-root UID (see audit-sandbox.Dockerfile
    // `USER auditor`/uid 1000). When the backend runs in a Docker container while
    // Podman runs on the host (or in a different user namespace), the host UID
    // owning this dir does not align with the UID that container-UID-1000 maps
    // to, so `codegraph init` fails to mkdir `.codegraph/` here with EACCES.
    // Widen permission on this directory only — files written inside remain
    // owned/protected by whichever UID writes them.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let perms = std::fs::Permissions::from_mode(0o777);
        if let Err(e) = tokio::fs::set_permissions(&src_dir, perms).await {
            tracing::warn!(path = %src_dir.display(), error = %e, "chmod staging src dir failed");
        }
    }

    let archive_path = archive_path.to_owned();
    let archive_name = archive_name.to_owned();
    let src_dir_clone = src_dir.clone();

    tokio::task::spawn_blocking(move || {
        extract_archive_path_to_directory(&archive_path, &archive_name, &src_dir_clone)
            .with_context(|| {
                format!(
                    "archive extraction failed: {} -> {}",
                    archive_path.display(),
                    src_dir_clone.display()
                )
            })
    })
    .await
    .context("spawn_blocking panicked during extraction")??;

    debug!(sha = archive_sha256, path = %src_dir.display(), "extraction complete");

    Ok(StagingDir {
        root: src_dir,
        archive_sha256: archive_sha256.to_owned(),
        _guard: TempCleanupGuard { path: staging_root },
    })
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

fn build_staging_root(sha: &str) -> PathBuf {
    codegraph_data_root().join("staging").join(sha)
}

/// Removes the wrapped path from disk when dropped.
struct TempCleanupGuard {
    path: PathBuf,
}

impl Drop for TempCleanupGuard {
    fn drop(&mut self) {
        if !self.path.exists() {
            return;
        }
        // First attempt — typically succeeds when all files share the backend's UID.
        if std::fs::remove_dir_all(&self.path).is_ok() {
            return;
        }
        // Codegraph container writes files under a different UID via the
        // bind-mounted volume; backend can't unlink them on the first pass.
        // Best-effort: recursively widen perms, then retry.
        #[cfg(unix)]
        {
            let _ = chmod_tree_writable(&self.path);
        }
        if std::fs::remove_dir_all(&self.path).is_ok() {
            return;
        }
        // chmod can't help cross-UID files (non-owners can't chmod on Linux).
        // Last resort: remove through Podman's user namespace where the files
        // were originally created.
        #[cfg(unix)]
        {
            if try_podman_unshare_rm(&self.path) {
                return;
            }
        }
        // Non-fatal: hash-keyed staging dirs are re-used safely on next
        // import. Demote to debug so it doesn't drown real warnings.
        tracing::debug!(
            path = %self.path.display(),
            "staging dir cleanup deferred (cross-UID leftovers)"
        );
    }
}

#[cfg(unix)]
fn chmod_tree_writable(root: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let meta = std::fs::symlink_metadata(root)?;
    let mut perms = meta.permissions();
    perms.set_mode(0o777);
    let _ = std::fs::set_permissions(root, perms);
    if meta.is_dir() && !meta.file_type().is_symlink() {
        if let Ok(entries) = std::fs::read_dir(root) {
            for entry in entries.flatten() {
                let _ = chmod_tree_writable(&entry.path());
            }
        }
    }
    Ok(())
}

/// Try to remove `path` via `podman unshare rm -rf`.
///
/// Files created by the codegraph container on a bind-mounted volume are owned
/// by the container's mapped UID — the host-side backend cannot chmod or unlink
/// them. `podman unshare` enters the same user namespace as rootless Podman,
/// where those UIDs are valid. Returns `true` on success.
#[cfg(unix)]
fn try_podman_unshare_rm(path: &Path) -> bool {
    use std::process::Command;
    match Command::new("podman")
        .args(["unshare", "rm", "-rf"])
        .arg(path)
        .output()
    {
        Ok(output) if output.status.success() => {
            tracing::debug!(path = %path.display(), "cleaned up staging dir via podman unshare");
            true
        }
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            tracing::debug!(
                path = %path.display(),
                code = ?output.status.code(),
                stderr = %stderr.trim(),
                "podman unshare rm failed"
            );
            false
        }
        Err(e) => {
            tracing::debug!(path = %path.display(), error = %e, "podman unshare not available");
            false
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;
    use zip::write::SimpleFileOptions;

    /// Build a minimal valid zip archive in a temp file, return its path.
    fn make_test_zip() -> NamedTempFile {
        let mut tmp = NamedTempFile::new().expect("tempfile");
        let mut zip = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
        zip.start_file("hello.txt", SimpleFileOptions::default())
            .unwrap();
        zip.write_all(b"hello codegraph\n").unwrap();
        let finished = zip.finish().unwrap();
        tmp.write_all(finished.get_ref()).unwrap();
        tmp.flush().unwrap();
        tmp
    }

    #[tokio::test]
    async fn test_prepare_extracts_and_cleanup_on_drop() {
        let zip = make_test_zip();
        let sha = "deadbeef1234";

        // Override ARGUS_CODEGRAPH_DATA_DIR to a temp dir so we don't pollute /tmp.
        let base = tempfile::tempdir().expect("tempdir");
        std::env::set_var("ARGUS_CODEGRAPH_DATA_DIR", base.path());

        let staging = prepare(zip.path(), "test.zip", sha)
            .await
            .expect("prepare failed");

        // File extracted into root.
        assert!(staging.root.join("hello.txt").exists(), "hello.txt missing");

        // Record the parent dir (the sha-keyed dir above src/).
        let sha_dir = staging.root.parent().unwrap().to_owned();
        assert!(sha_dir.exists());

        // Drop triggers RAII cleanup.
        drop(staging);
        assert!(!sha_dir.exists(), "staging dir should have been removed");
    }

    #[tokio::test]
    async fn test_prepare_idempotent_on_existing_dir() {
        let zip = make_test_zip();
        let sha = "cafebabe5678";

        let base = tempfile::tempdir().expect("tempdir");
        std::env::set_var("ARGUS_CODEGRAPH_DATA_DIR", base.path());

        // First call — extracts.
        let s1 = prepare(zip.path(), "test.zip", sha).await.expect("first");
        let root1 = s1.root.clone();

        // Manually drop s1 guard to release, but keep the dir for the test by
        // using std::mem::forget (we want idempotency, not cleanup here).
        // Instead: pre-create the src/ dir without the guard.
        drop(s1); // cleans up; recreate manually for idempotency test.

        let src_dir = build_staging_root(sha).join("src");
        std::fs::create_dir_all(&src_dir).unwrap();
        std::fs::write(src_dir.join("marker.txt"), b"exists").unwrap();

        let s2 = prepare(zip.path(), "test.zip", sha).await.expect("second");
        // Must re-use existing path (no re-extraction wipes marker).
        assert_eq!(s2.root, src_dir);
        assert!(
            s2.root.join("marker.txt").exists(),
            "idempotent: should not re-extract"
        );
        assert_eq!(root1, src_dir);
    }
}
