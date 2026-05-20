//! Static guard: no opengrep pool residue should remain in backend/ source.
//!
//! Catches regressions where a future change accidentally re-introduces pool
//! references (e.g., revival of removed env var, half-deleted module). Runs in
//! every CI test invocation.
//!
//! Refs:
//!   spec: .omc/specs/deep-dive-opengrep-sandbox-auto-destroy.md (AC5)
//!   plan: .omc/plans/ralplan-opengrep-sandbox-auto-destroy.md (Step 8)

#[test]
fn pool_residue_grep() {
    let forbidden = [
        "OpengrepSandboxPool",
        "opengrep_pool",
        "warm_opengrep_pool",
        "OPENGREP_POOL_SIZE",
        "OPENGREP_POOL_MANIFEST",
        "opengrep-pool-manifest",
    ];

    // Attempt ripgrep first; fall back to walkdir + plain string scan if rg
    // is not in PATH (some CI environments may not have it).
    if try_rg_residue_check(&forbidden) {
        return; // rg handled the check
    }
    walkdir_residue_check(&forbidden);
}

// ─── rg-based check ───────────────────────────────────────────────────────────

/// Returns true if `rg` is available and the check completed (pass or fail).
/// Returns false if `rg` is not found, so the caller can fall back.
fn try_rg_residue_check(forbidden: &[&str]) -> bool {
    let mut args: Vec<String> = vec![
        "-n".into(),
        "--no-heading".into(),
        // Exclude integration test files (they may reference patterns in comments/strings).
        "--glob".into(),
        "!tests/**".into(),
        // Exclude build artifacts.
        "--glob".into(),
        "!**/target/**".into(),
        "--glob".into(),
        "!.git/**".into(),
    ];
    for p in forbidden {
        args.push("-e".into());
        args.push((*p).into());
    }
    // Search backend/ source tree from the workspace root.
    args.push("backend/src".into());

    let result = std::process::Command::new("rg")
        .args(&args)
        // Run from workspace root so the "backend/src" path resolves correctly.
        .current_dir("/home/xyf/argus")
        .output();

    match result {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            // rg not available — signal caller to use fallback.
            false
        }
        Err(e) => {
            panic!("rg invocation failed: {e}");
        }
        Ok(output) => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            assert!(
                stdout.is_empty(),
                "pool residue found in backend/src (excluding bootstrap/mod.rs):\n{}",
                stdout
            );
            true
        }
    }
}

// ─── walkdir fallback ─────────────────────────────────────────────────────────

/// Pure-Rust fallback: walk backend/src/ and scan each .rs file for forbidden
/// patterns using plain string contains().
fn walkdir_residue_check(forbidden: &[&str]) {
    let src_root = std::path::Path::new("/home/xyf/argus/backend/src");
    if !src_root.exists() {
        // Running from a different working directory — skip gracefully.
        eprintln!("[skip] no_pool_residue: src_root not found at {src_root:?}");
        return;
    }

    let mut violations: Vec<String> = Vec::new();

    walk_rs_files(src_root, &mut |path, content| {
        for (lineno, line) in content.lines().enumerate() {
            for pattern in forbidden {
                if line.contains(pattern) {
                    violations.push(format!(
                        "{}:{}: {}",
                        path.display(),
                        lineno + 1,
                        line.trim()
                    ));
                }
            }
        }
    });

    assert!(
        violations.is_empty(),
        "pool residue found in backend/src (excluding bootstrap/mod.rs):\n{}",
        violations.join("\n")
    );
}

fn walk_rs_files(dir: &std::path::Path, callback: &mut dyn FnMut(&std::path::Path, &str)) {
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            // Skip target/ and .git/
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name == "target" || name == ".git" {
                continue;
            }
            walk_rs_files(&path, callback);
        } else if path.extension().and_then(|e| e.to_str()) == Some("rs") {
            if let Ok(content) = std::fs::read_to_string(&path) {
                callback(&path, &content);
            }
        }
    }
}
