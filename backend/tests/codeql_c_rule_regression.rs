use std::{
    env,
    path::{Path, PathBuf},
    process::Command,
};

fn codeql_bin() -> Option<PathBuf> {
    if let Some(bin) = env::var_os("CODEQL_BIN").filter(|value| !value.is_empty()) {
        return Some(PathBuf::from(bin));
    }

    let output = Command::new("codeql").arg("version").output().ok()?;
    output.status.success().then(|| PathBuf::from("codeql"))
}

fn infer_codeql_search_path(codeql_bin: &Path) -> Option<PathBuf> {
    if codeql_bin.components().count() <= 1 {
        return None;
    }
    let qlpacks = codeql_bin.parent()?.join("qlpacks");
    qlpacks.is_dir().then_some(qlpacks)
}

#[test]
fn codeql_c_security_rules_detect_expected_regressions() {
    let Some(codeql_bin) = codeql_bin() else {
        eprintln!("skipping: CodeQL CLI is not available; set CODEQL_BIN to run this regression");
        return;
    };

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let script = manifest_dir.join("tests/codeql_c_rule_regression/run-codeql-rule-tests.sh");
    let mut command = Command::new(&script);
    command.env("CODEQL_BIN", &codeql_bin);
    if env::var_os("CODEQL_SEARCH_PATH").is_none() {
        if let Some(search_path) = infer_codeql_search_path(&codeql_bin) {
            command.env("CODEQL_SEARCH_PATH", search_path);
        }
    }

    let output = command.output().expect("run CodeQL C rule regression");
    assert!(
        output.status.success(),
        "CodeQL C rule regression failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
