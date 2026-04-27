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
    assert!(fs::read_to_string(fixture.stdout_capture_path())
        .expect("stdout capture")
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

#[test]
fn opengrep_scan_recovers_results_from_json_stdout_when_output_file_is_missing() {
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
        .env("FAKE_OPENGREP_SKIP_OUTPUT", "1")
        .env("FAKE_OPENGREP_STDOUT_JSON_ONLY", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should recover valid JSON stdout\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    assert!(fs::read_to_string(&fixture.output_path)
        .expect("recovered results")
        .contains("\"results\""));
    assert!(fs::read_to_string(&fixture.log_path)
        .expect("log")
        .contains("recovered opengrep JSON results from stdout"));
}

#[test]
fn opengrep_scan_recovers_results_from_mixed_stdout_when_output_file_is_missing() {
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
        .env("FAKE_OPENGREP_SKIP_OUTPUT", "1")
        .env("FAKE_OPENGREP_MIXED_STDOUT_JSON", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should recover valid JSON embedded in stdout\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    assert!(fs::read_to_string(&fixture.output_path)
        .expect("recovered results")
        .contains("\"results\""));
    assert!(fs::read_to_string(&fixture.log_path)
        .expect("log")
        .contains("recovered opengrep JSON results from stdout"));
}

#[test]
fn opengrep_scan_recovers_results_from_log_when_output_file_is_missing() {
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
        .env("FAKE_OPENGREP_SKIP_OUTPUT", "1")
        .env("FAKE_OPENGREP_LOG_JSON_ONLY", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should recover valid JSON embedded in the log\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    assert!(fs::read_to_string(&fixture.output_path)
        .expect("recovered results")
        .contains("\"results\""));
    assert!(fs::read_to_string(&fixture.log_path)
        .expect("log")
        .contains("recovered opengrep JSON results from log"));
}

#[test]
fn opengrep_scan_recovers_results_from_mixed_output_file() {
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
        .env("FAKE_OPENGREP_MIXED_OUTPUT_FILE", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should normalize valid JSON embedded in the output file\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    let recovered_results = fs::read_to_string(&fixture.output_path).expect("recovered results");
    assert!(recovered_results.starts_with('{'));
    assert!(recovered_results.contains("\"results\""));
    assert!(fs::read_to_string(&fixture.log_path)
        .expect("log")
        .contains("recovered opengrep JSON results from output file"));
}

#[test]
fn opengrep_scan_synthesizes_empty_results_from_zero_finding_log() {
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
        .env("FAKE_OPENGREP_SKIP_OUTPUT", "1")
        .env("FAKE_OPENGREP_ZERO_FINDINGS_STDERR", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should treat a completed zero-finding scan as success\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    assert_eq!(
        fs::read_to_string(&fixture.output_path).expect("empty results"),
        "{\"results\":[]}\n"
    );
}

#[test]
fn opengrep_scan_splits_rule_batches_after_missing_output_failure() {
    let fixture = ScriptFixture::new();
    fixture.write_rule("rules_opengrep/one.yml");
    fixture.write_rule("rules_opengrep/two.yml");
    fixture.write_rule("rules_opengrep/three.yml");

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
        .env("OPENGREP_SCAN_BATCH_SIZE", "2")
        .env("FAKE_OPENGREP_BATCH_FAIL_ON_MULTI", "1")
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should recover by splitting failed rule batches\nstatus={:?}\nsummary={}\nlog={}\nstdout={}\nstderr={}",
        output.status.code(),
        fs::read_to_string(&fixture.summary_path).unwrap_or_default(),
        fs::read_to_string(&fixture.log_path).unwrap_or_default(),
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read_to_string(&fixture.summary_path)
        .expect("summary")
        .contains("\"status\":\"scan_completed\""));
    let results = fs::read_to_string(&fixture.output_path).expect("merged results");
    assert_eq!(results.matches("\"check_id\"").count(), 3, "{results}");
    let log = fs::read_to_string(&fixture.log_path).expect("log");
    assert!(
        log.contains("retrying opengrep scan in rule batches"),
        "{log}"
    );
    assert!(
        log.contains("merged opengrep JSON results from 3 rule batches"),
        "{log}"
    );
}

#[test]
fn opengrep_scan_rule_batch_staging_does_not_depend_on_shutil() {
    let fixture = ScriptFixture::new();
    let script = fs::read_to_string(&fixture.script_path).expect("script");

    assert!(
        !script.contains("import shutil"),
        "rule batch staging must not depend on Python shutil in the minimal runner image"
    );
    assert!(
        script.contains("stage_rule_range \"$stage_list\" 1 2"),
        "self-test should exercise non-zero-start rule batch staging"
    );
    assert!(
        script.contains("cp -p -- \"$source\" \"$target\""),
        "rule batch staging should copy paths safely even if a source starts with '-'"
    );
}

#[test]
fn opengrep_scan_self_test_exercises_rule_batch_staging() {
    let fixture = ScriptFixture::new();

    let output = Command::new("bash")
        .arg(&fixture.script_path)
        .arg("--self-test")
        .env("PATH", &fixture.path_env)
        .env("OPENGREP_RULES_ROOT", &fixture.rules_root)
        .output()
        .expect("run opengrep-scan self-test");

    assert!(
        output.status.success(),
        "self-test should pass and exercise rule staging\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn opengrep_scan_uses_primary_output_file_contract() {
    let fixture = ScriptFixture::new();
    let args_path = fixture._temp_dir.path().join("args.txt");

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
        .env("FAKE_OPENGREP_ARGS_PATH", &args_path)
        .output()
        .expect("run opengrep-scan");

    assert!(
        output.status.success(),
        "script should complete successfully\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let args = fs::read_to_string(args_path).expect("args");
    assert!(
        args.contains(" --output "),
        "wrapper should ask opengrep to write the primary result file with --output\nargs={args}"
    );
    assert!(
        !args.contains(" --json-output "),
        "wrapper should avoid duplicate JSON stdout/file contracts\nargs={args}"
    );
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
        fs::create_dir_all(rules_root.join("rules_opengrep")).expect("mkdir builtin rules");

        let fake_opengrep = fake_bin.join("opengrep");
        fs::write(
            &fake_opengrep,
            r#"#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--version" ]; then
  printf 'opengrep fake\n'
  exit 0
fi
if [ -n "${FAKE_OPENGREP_ARGS_PATH:-}" ]; then
  printf ' %s ' "$*" > "$FAKE_OPENGREP_ARGS_PATH"
fi
output_path=""
config_paths=()
prev=""
while [ "$#" -gt 0 ]; do
  case "$prev" in
    output)
      output_path="$1"
      prev=""
      ;;
    config)
      config_paths+=("$1")
      prev=""
      ;;
  esac
  case "$1" in
    --output|--json-output) prev="output" ;;
    --config) prev="config" ;;
  esac
  shift
done
rule_file_count=0
for config_path in "${config_paths[@]}"; do
  if [ -d "$config_path" ]; then
    while IFS= read -r _rule_file; do
      rule_file_count=$((rule_file_count + 1))
    done < <(find "$config_path" -type f \( -name '*.yml' -o -name '*.yaml' \))
  elif [ -f "$config_path" ]; then
    rule_file_count=$((rule_file_count + 1))
  fi
done
if [ "${FAKE_OPENGREP_BATCH_FAIL_ON_MULTI:-0}" = "1" ] && [ "$rule_file_count" -gt 1 ]; then
  printf '%s\n' 'opengrep-core exited with -9!' >&2
  exit 2
fi
if [ "${FAKE_OPENGREP_STDOUT_JSON_ONLY:-0}" = "1" ]; then
  printf '%s\n' '{"results":[]}'
elif [ "${FAKE_OPENGREP_MIXED_STDOUT_JSON:-0}" = "1" ]; then
  printf '%s\n' 'scan banner before json'
  printf '%s\n' '{"results":[]}'
  printf '%s\n' 'scan summary after json'
elif [ "${FAKE_OPENGREP_LOG_JSON_ONLY:-0}" = "1" ]; then
  printf '%s\n' 'scan banner before json' >&2
  printf '%s\n' '{"results":[]}' >&2
  printf '%s\n' 'scan summary after json' >&2
elif [ "${FAKE_OPENGREP_ZERO_FINDINGS_STDERR:-0}" = "1" ]; then
  printf '%s\n' 'Ran 1 rule on 1 file: 0 findings.' >&2
else
  for i in $(seq 1 5000); do
    printf 'scanner line %s\n' "$i"
  done
fi
if [ "${FAKE_OPENGREP_SKIP_OUTPUT:-0}" != "1" ]; then
  mkdir -p "$(dirname "$output_path")"
  if [ "${FAKE_OPENGREP_MIXED_OUTPUT_FILE:-0}" = "1" ]; then
    printf '%s\n' 'scan banner before json' > "$output_path"
    printf '%s\n' '{"results":[]}' >> "$output_path"
    printf '%s\n' 'scan summary after json' >> "$output_path"
  elif [ "${FAKE_OPENGREP_BATCH_FAIL_ON_MULTI:-0}" = "1" ]; then
    mkdir -p "$(dirname "$output_path")"
    printf '{"results":[{"check_id":"fake-rule-%s","path":"src/main.py","start":{"line":1},"end":{"line":1},"extra":{"message":"demo","severity":"WARNING"}}]}\n' "$rule_file_count" > "$output_path"
  else
    printf '%s\n' '{"results":[]}' > "$output_path"
  fi
fi
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

    fn stdout_capture_path(&self) -> std::path::PathBuf {
        std::path::PathBuf::from(format!("{}.stdout", self.output_path.display()))
    }

    fn write_rule(&self, relative_path: &str) {
        let path = self.rules_root.join(relative_path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("mkdir rule parent");
        }
        fs::write(
            path,
            "rules:\n  - id: fake\n    languages: [python]\n    message: fake\n    severity: WARNING\n    pattern: dangerous_call($X)\n",
        )
        .expect("write rule");
    }
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}
