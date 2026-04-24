use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};
use uuid::Uuid;

use crate::runtime::runner::{self, RunnerSpec, SCANNER_MOUNT_PATH};

const DEFAULT_TIMEOUT_SECONDS: u64 = 120;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum FlowParserOperation {
    DefinitionsBatch,
    LocateEnclosingFunction,
}

impl FlowParserOperation {
    pub fn from_cli(raw: &str) -> Result<Self, String> {
        match raw.trim() {
            "definitions-batch" => Ok(Self::DefinitionsBatch),
            "locate-enclosing-function" => Ok(Self::LocateEnclosingFunction),
            other => Err(format!("unsupported_flow_parser_operation:{other}")),
        }
    }

    pub fn runner_command(&self) -> Vec<String> {
        vec![
            "python3".to_string(),
            "/opt/flow-parser/flow_parser_runner.py".to_string(),
            self.as_cli_name().to_string(),
            "--request".to_string(),
            format!("{SCANNER_MOUNT_PATH}/request.json"),
            "--response".to_string(),
            format!("{SCANNER_MOUNT_PATH}/response.json"),
        ]
    }

    pub fn as_cli_name(&self) -> &'static str {
        match self {
            Self::DefinitionsBatch => "definitions-batch",
            Self::LocateEnclosingFunction => "locate-enclosing-function",
        }
    }
}

pub fn execute_from_request_path(operation: FlowParserOperation, request_path: &Path) -> Value {
    let payload = match fs::read_to_string(request_path) {
        Ok(raw) => match serde_json::from_str::<Value>(&raw) {
            Ok(value) => value,
            Err(error) => {
                return serde_json::json!({
                    "ok": false,
                    "error": format!("invalid_flow_parser_request:{error}"),
                });
            }
        },
        Err(error) => {
            return serde_json::json!({
                "ok": false,
                "error": format!("read_flow_parser_request_failed:{error}"),
            });
        }
    };

    execute(operation, payload)
}

pub fn execute(operation: FlowParserOperation, payload: Value) -> Value {
    let (workspace_dir, workspace_root_override) = match prepare_workspace_dir() {
        Ok(paths) => paths,
        Err(error) => {
            return serde_json::json!({
                "ok": false,
                "error": error,
            });
        }
    };
    if let Err(error) = fs::create_dir_all(&workspace_dir) {
        return serde_json::json!({
            "ok": false,
            "error": format!("create_flow_parser_workspace_failed:{error}"),
        });
    }
    let workspace_guard = WorkspaceGuard::new(workspace_dir.clone());

    let request_path = workspace_dir.join("request.json");
    let response_path = workspace_dir.join("response.json");

    let payload_text = match serde_json::to_string_pretty(&payload) {
        Ok(text) => text,
        Err(error) => {
            return serde_json::json!({
                "ok": false,
                "error": format!("serialize_flow_parser_request_failed:{error}"),
            });
        }
    };

    if let Err(error) = fs::write(&request_path, payload_text) {
        return serde_json::json!({
            "ok": false,
            "error": format!("write_flow_parser_request_failed:{error}"),
        });
    }

    let spec = RunnerSpec {
        scanner_type: "flow_parser".to_string(),
        image: requested_image(&payload).unwrap_or_else(flow_parser_runner_image),
        workspace_dir: workspace_dir.display().to_string(),
        workspace_root_override,
        command: operation.runner_command(),
        timeout_seconds: requested_timeout_seconds(&payload)
            .unwrap_or_else(flow_parser_timeout_seconds)
            .max(1),
        env: BTreeMap::new(),
        expected_exit_codes: vec![0],
        artifact_paths: Vec::new(),
        capture_stdout_path: None,
        capture_stderr_path: None,
        completion_summary_path: None,
        memory_limit_mb: None,
        memory_swap_limit_mb: None,
        cpu_limit: None,
        pids_limit: None,
    };

    let runner_result = runner::execute(spec);
    if !runner_result.success {
        return serde_json::json!({
            "ok": false,
            "error": runner_result.error.unwrap_or_else(|| "flow_parser_runner_failed".to_string()),
        });
    }

    let raw_response = match fs::read_to_string(&response_path) {
        Ok(text) => text,
        Err(_) => {
            return serde_json::json!({
                "ok": false,
                "error": "flow_parser_runner_missing_response",
            });
        }
    };

    let response = match serde_json::from_str::<Value>(&raw_response) {
        Ok(value) => value,
        Err(error) => serde_json::json!({
            "ok": false,
            "error": format!("invalid_flow_parser_response:{error}"),
        }),
    };
    drop(workspace_guard);
    response
}

fn scan_workspace_root() -> PathBuf {
    env::var("SCAN_WORKSPACE_ROOT")
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("/tmp/vulhunter/scans"))
}

fn flow_parser_runner_image() -> String {
    env::var("FLOW_PARSER_RUNNER_IMAGE")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "vulhunter/flow-parser-runner:latest".to_string())
}

fn prepare_workspace_dir() -> Result<(PathBuf, Option<String>), String> {
    let workspace_name = Uuid::new_v4().to_string();
    let preferred_root = scan_workspace_root().join("flow-parser-runtime");
    if fs::create_dir_all(&preferred_root).is_ok() {
        return Ok((preferred_root.join(workspace_name), None));
    }

    let fallback_root = env::temp_dir();
    Ok((
        fallback_root.join(format!("flow-parser-runtime-{workspace_name}")),
        Some(fallback_root.display().to_string()),
    ))
}

fn flow_parser_timeout_seconds() -> u64 {
    env::var("FLOW_PARSER_RUNNER_TIMEOUT_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .unwrap_or(DEFAULT_TIMEOUT_SECONDS)
        .max(1)
}

fn requested_image(payload: &Value) -> Option<String> {
    payload
        .as_object()
        .and_then(|items| items.get("image"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn requested_timeout_seconds(payload: &Value) -> Option<u64> {
    payload
        .as_object()
        .and_then(|items| items.get("timeout_seconds"))
        .and_then(Value::as_u64)
        .map(|value| value.max(1))
}

struct WorkspaceGuard {
    path: PathBuf,
}

impl WorkspaceGuard {
    fn new(path: PathBuf) -> Self {
        Self { path }
    }
}

impl Drop for WorkspaceGuard {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

#[cfg(test)]
mod tests {
    use super::{execute, execute_from_request_path, FlowParserOperation};
    use serde_json::json;
    use std::{
        env, fs,
        path::PathBuf,
        sync::{Mutex, OnceLock},
    };
    use tempfile::TempDir;

    static ENV_MUTEX: OnceLock<Mutex<()>> = OnceLock::new();

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        ENV_MUTEX
            .get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(|error| error.into_inner())
    }

    fn write_fake_docker(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-docker.sh");
        let script = r#"#!/usr/bin/env bash
set -eu
cmd="${1:-}"
shift || true
case "${cmd}" in
  create)
    printf '%s\n' "$@" > "${FAKE_DOCKER_CREATE_ARGS_FILE}"
    printf '%s' "${FAKE_DOCKER_CONTAINER_ID:-container-xyz}"
    ;;
  start)
    if [ "${1:-}" = "-a" ]; then
      shift
    fi
    if [ -n "${FAKE_DOCKER_START_SLEEP_SECONDS:-}" ]; then
      sleep "${FAKE_DOCKER_START_SLEEP_SECONDS}"
    fi
    printf '%s' "${FAKE_DOCKER_START_STDOUT:-}"
    printf '%s' "${FAKE_DOCKER_START_STDERR:-}" >&2
    ;;
  inspect)
    if [ "${1:-}" = "--format" ]; then
      shift 2
    fi
    printf '%s' "${FAKE_DOCKER_EXIT_CODE:-0}"
    ;;
  wait)
    printf '%s' "${FAKE_DOCKER_WAIT_EXIT_CODE:-${FAKE_DOCKER_EXIT_CODE:-0}}"
    ;;
  stop)
    ;;
  rm)
    ;;
  *)
    echo "unsupported command: ${cmd}" >&2
    exit 1
    ;;
esac
"#;
        fs::write(&script_path, script).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(&script_path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(&script_path, permissions).unwrap();
        }
        script_path
    }

    #[test]
    fn flow_parser_operation_builds_runner_command() {
        let command = FlowParserOperation::DefinitionsBatch.runner_command();
        assert_eq!(
            command,
            vec![
                "python3".to_string(),
                "/opt/flow-parser/flow_parser_runner.py".to_string(),
                "definitions-batch".to_string(),
                "--request".to_string(),
                "/scan/request.json".to_string(),
                "--response".to_string(),
                "/scan/response.json".to_string(),
            ]
        );
    }

    #[test]
    fn flow_parser_operation_requires_known_selector() {
        assert_eq!(
            serde_json::to_value(FlowParserOperation::from_cli("definitions-batch").unwrap())
                .unwrap(),
            json!("definitions-batch")
        );
        assert!(FlowParserOperation::from_cli("unknown").is_err());
    }

    #[test]
    fn execute_from_request_path_rejects_invalid_json() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().expect("temp dir");
        let request_path = temp_dir.path().join("request.json");
        fs::write(&request_path, "{invalid").expect("write request");

        let result =
            execute_from_request_path(FlowParserOperation::DefinitionsBatch, &request_path);

        assert_eq!(result["ok"], false);
        assert!(result["error"]
            .as_str()
            .unwrap_or_default()
            .contains("invalid_flow_parser_request"));
    }

    #[test]
    fn execute_reports_runner_failures() {
        let _guard = env_lock();
        env::set_var("BACKEND_DOCKER_BIN", "/definitely/missing/docker");
        env::remove_var("SCAN_WORKSPACE_ROOT");
        let result = execute(
            FlowParserOperation::DefinitionsBatch,
            json!({"items": [{"file_path": "demo.py", "content": "print(1)"}]}),
        );

        assert_eq!(result["ok"], false);
        assert!(result["error"]
            .as_str()
            .unwrap_or_default()
            .contains("run docker command"));
    }

    #[test]
    fn prepare_workspace_dir_falls_back_to_system_tempdir_when_scan_root_is_unwritable() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().expect("temp dir");
        let blocking_file = temp_dir.path().join("not-a-dir");
        fs::write(&blocking_file, "block").expect("write blocking file");
        env::set_var("SCAN_WORKSPACE_ROOT", &blocking_file);

        let (workspace, workspace_root_override) =
            super::prepare_workspace_dir().expect("workspace should resolve");

        assert!(workspace.starts_with(std::env::temp_dir()));
        assert!(!workspace.starts_with(blocking_file));
        assert_eq!(
            workspace_root_override,
            Some(std::env::temp_dir().display().to_string())
        );
    }

    #[test]
    fn requested_runner_fields_override_environment_defaults() {
        let payload = json!({
            "image": "vulhunter/flow-parser-runner-custom:latest",
            "timeout_seconds": 77
        });

        assert_eq!(
            super::requested_image(&payload).as_deref(),
            Some("vulhunter/flow-parser-runner-custom:latest")
        );
        assert_eq!(super::requested_timeout_seconds(&payload), Some(77));
    }

    #[test]
    fn execute_honors_request_image_and_timeout_and_cleans_workspace_on_failure() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().expect("temp dir");
        let fake_docker = write_fake_docker(&temp_dir);
        let args_file = temp_dir.path().join("create-args.txt");
        let scan_root = temp_dir.path().join("scan-root");
        fs::create_dir_all(&scan_root).expect("scan root");

        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_CREATE_ARGS_FILE", &args_file);
        env::set_var("FAKE_DOCKER_START_SLEEP_SECONDS", "2");
        env::set_var("FAKE_DOCKER_EXIT_CODE", "0");
        env::set_var("FAKE_DOCKER_WAIT_EXIT_CODE", "0");
        env::set_var("SCAN_WORKSPACE_ROOT", &scan_root);

        let result = execute(
            FlowParserOperation::DefinitionsBatch,
            json!({
                "items": [{"file_path": "demo.py", "content": "print(1)"}],
                "image": "vulhunter/flow-parser-runner-custom:latest",
                "timeout_seconds": 1
            }),
        );

        let create_args = fs::read_to_string(&args_file).expect("create args");
        assert!(create_args.contains("vulhunter/flow-parser-runner-custom:latest"));
        assert_eq!(result["ok"], false);
        assert!(result["error"]
            .as_str()
            .unwrap_or_default()
            .contains("timed out after 1s"));

        let runtime_root = scan_root.join("flow-parser-runtime");
        let entries = fs::read_dir(&runtime_root)
            .map(|items| items.filter_map(Result::ok).collect::<Vec<_>>())
            .unwrap_or_default();
        assert!(
            entries.is_empty(),
            "workspace directories should be cleaned up"
        );
    }

    #[test]
    fn execute_uses_tempdir_fallback_end_to_end_when_scan_root_is_unwritable() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().expect("temp dir");
        let fake_docker = write_fake_docker(&temp_dir);
        let args_file = temp_dir.path().join("create-args.txt");
        let blocking_file = temp_dir.path().join("not-a-dir");
        fs::write(&blocking_file, "block").expect("write blocking file");

        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_CREATE_ARGS_FILE", &args_file);
        env::set_var("SCAN_WORKSPACE_ROOT", &blocking_file);

        let result = execute(
            FlowParserOperation::DefinitionsBatch,
            json!({"items": [{"file_path": "demo.py", "content": "print(1)"}]}),
        );

        let create_args = fs::read_to_string(&args_file).expect("create args");
        assert!(create_args.contains(std::env::temp_dir().display().to_string().as_str()));
        assert_eq!(result["ok"], false);
        assert_eq!(result["error"], "flow_parser_runner_missing_response");
    }
}
