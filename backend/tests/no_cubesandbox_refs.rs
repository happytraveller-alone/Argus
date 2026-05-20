//! Guard test: prevent accidental re-introduction of the retired sandbox runtime.
//!
//! Current product code must not contain active references to the retired
//! implementation. Archive docs and this guard test may still name it, but
//! `backend/src/` should stay clean.

use std::process::Command;

#[test]
fn retired_sandbox_runtime_is_absent_from_backend_src() {
    // cargo test runs with cwd = the package manifest directory (backend/).
    let output = Command::new("rg")
        .args(["-n", "--no-heading", "cubesandbox|CubeSandbox", "src/"])
        .output();

    let output = match output {
        Ok(o) => o,
        Err(e) => {
            eprintln!(
                "WARNING: rg (ripgrep) not installed; skipping retired sandbox guard test ({e})"
            );
            return;
        }
    };

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.trim().is_empty(),
        "Retired sandbox runtime references found in backend/src. \
         Product code should stay clean; put history in docs/archive/cubesandbox/.\n\n{}",
        stdout
    );
}
