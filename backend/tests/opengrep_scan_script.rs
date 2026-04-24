use std::{fs, process::Command};

use tempfile::TempDir;

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;

#[cfg(unix)]
fn make_executable(path: &std::path::Path) {
    let mut permissions = fs::metadata(path).expect("metadata").permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).expect("chmod");
}

#[cfg(not(unix))]
fn make_executable(_path: &std::path::Path) {}

#[test]
fn opengrep_scan_does_not_pipe_scanner_stdout_to_caller_stdout() {
    let fixture = ScriptFixture::new();
    let command = format!(
        "PATH={} OPENGREP_RULES_ROOT={} bash {} --target {} --output {} --summary {} --log {} | head -n 0",
        shell_quote(&fixture.path_env),
        shell_quote(fixture.rules_root.to_string_lossy().as_ref()),
        shell_quote(fixture.script_path.to_string_lossy().as_ref()),
        shell_quote(fixture.target_dir.to_string_lossy().as_ref()),
        shell_quote(fixture.output_path.to_string_lossy().as_ref()),
        shell_quote(fixture.summary_path.to_string_lossy().as_ref()),
        shell_quote(fixture.log_path.to_string_lossy().as_ref()),
    );

    let output = Command::new("bash")
        .arg("-o")
        .arg("pipefail")
        .arg("-c")
        .arg(command)
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should not fail when caller stdout closes\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    assert!(fs::read_to_string(&fixture.log_path)
        .expect("log")
        .contains("scanner line 5000"));
}

#[test]
fn opengrep_scan_writes_summary_for_accepted_nonzero_scan_exit() {
    let fixture = ScriptFixture::new();

    let output = Command::new("bash")
        .arg(&fixture.script_path)
        .arg("--target")
        .arg(&fixture.target_dir)
        .arg("--output")
        .arg(&fixture.output_path)
        .arg("--summary")
        .arg(&fixture.summary_path)
        .arg("--log")
        .arg(&fixture.log_path)
        .env("PATH", &fixture.path_env)
        .env("OPENGREP_RULES_ROOT", &fixture.rules_root)
        .env("FAKE_OPENGREP_EXIT", "1")
        .output()
        .expect("run opengrep-scan");

    assert_eq!(output.status.code(), Some(1), "{output:?}");
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
}

struct ScriptFixture {
    _temp_dir: TempDir,
    path_env: String,
    rules_root: std::path::PathBuf,
    script_path: std::path::PathBuf,
    target_dir: std::path::PathBuf,
    output_path: std::path::PathBuf,
    summary_path: std::path::PathBuf,
    log_path: std::path::PathBuf,
}

impl ScriptFixture {
    fn new() -> Self {
        let temp_dir = TempDir::new().expect("temp dir");
        let fake_bin = temp_dir.path().join("bin");
        let target_dir = temp_dir.path().join("target");
        let output_path = temp_dir.path().join("results.json");
        let summary_path = temp_dir.path().join("summary.json");
        let log_path = temp_dir.path().join("opengrep.log");
        let rules_root = temp_dir.path().join("rules");
        fs::create_dir_all(&fake_bin).expect("mkdir bin");
        fs::create_dir_all(&target_dir).expect("mkdir target");
        fs::create_dir_all(&rules_root).expect("mkdir rules");

        let fake_opengrep = fake_bin.join("opengrep");
        fs::write(
            &fake_opengrep,
            r#"#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--version" ]; then
  printf 'opengrep fake\n'
  exit 0
fi
output_path=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      output_path="${2:?missing output}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
for i in $(seq 1 5000); do
  printf 'scanner line %s\n' "$i"
done
mkdir -p "$(dirname "$output_path")"
printf '%s\n' '{"results":[]}' > "$output_path"
exit "${FAKE_OPENGREP_EXIT:-0}"
"#,
        )
        .expect("write fake opengrep");
        make_executable(&fake_opengrep);

        let script_path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("repo root")
            .join("docker/opengrep-scan.sh");
        let path_env = format!(
            "{}:{}",
            fake_bin.display(),
            std::env::var("PATH").unwrap_or_default()
        );

        Self {
            _temp_dir: temp_dir,
            path_env,
            rules_root,
            script_path,
            target_dir,
            output_path,
            summary_path,
            log_path,
        }
    }
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}
