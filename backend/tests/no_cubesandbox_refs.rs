//! Guard test: prevent accidental re-introduction of cubesandbox.
//!
//! Post the cubesandbox removal commits (584d16c3..535dc8c9), only a few
//! historical-context comments in `runtime/shutdown.rs` and
//! `bootstrap/mod.rs` retain the substring `cubesandbox`/`CubeSandbox`.
//! Any new references in `backend/src/` outside those two files — or any
//! non-comment line in them — fails this test.
//!
//! Reinterprets plan Steps 14-15 (originally "cubesandbox files frozen"
//! byte-invariant) under the new ground truth that cubesandbox has been
//! fully removed: AC5/AC6 collapse into "do not re-introduce."

use std::process::Command;

#[test]
fn cubesandbox_only_in_historical_comments() {
    // cargo test runs with cwd = the package manifest directory (backend/).
    let output = Command::new("rg")
        .args(["-n", "--no-heading", "cubesandbox|CubeSandbox", "src/"])
        .output();

    let output = match output {
        Ok(o) => o,
        Err(e) => {
            eprintln!(
                "WARNING: rg (ripgrep) not installed; skipping cubesandbox guard test ({e})"
            );
            return;
        }
    };

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut violations: Vec<String> = Vec::new();

    for line in stdout.lines() {
        // rg --no-heading -n format: "path:linenum:content"
        let mut parts = line.splitn(3, ':');
        let path = match parts.next() {
            Some(p) => p,
            None => continue,
        };
        let _linenum = parts.next();
        let content = match parts.next() {
            Some(c) => c.trim_start(),
            None => continue,
        };

        let is_allowed_file =
            path == "src/runtime/shutdown.rs" || path == "src/bootstrap/mod.rs";
        let is_comment = content.starts_with("//")
            || content.starts_with("/*")
            || content.starts_with('*');

        if !(is_allowed_file && is_comment) {
            violations.push(line.to_string());
        }
    }

    assert!(
        violations.is_empty(),
        "Cubesandbox references found outside permitted historical comments.\n\
         The cubesandbox runtime was removed (see commits 584d16c3..535dc8c9).\n\
         New refs in backend/src/ require explicit review and an update to this guard.\n\n\
         Violations:\n{}",
        violations.join("\n")
    );
}
