use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};
use uuid::Uuid;

use crate::runtime::runner::{self, RunnerSpec, SCANNER_MOUNT_PATH};

const DEFAULT_TIMEOUT_SECONDS: u64 = 40;
const DEFAULT_MAX_FILES: usize = 400;
const SUPPORTED_EXTENSIONS: &[&str] = &[
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp",
    ".hxx",
];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Code2FlowRequest {
    pub project_root: String,
    #[serde(default)]
    pub target_files: Vec<String>,
    #[serde(default = "default_timeout_seconds")]
    pub timeout_seconds: u64,
    #[serde(default = "default_max_files")]
    pub max_files: usize,
    pub image: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Code2FlowResponse {
    pub ok: bool,
    pub edges: BTreeMap<String, Vec<String>>,
    pub blocked_reasons: Vec<String>,
    pub used_engine: String,
    #[serde(default)]
    pub diagnostics: BTreeMap<String, String>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct Code2FlowFilePayload {
    file_path: String,
    content: String,
}

#[derive(Debug, Clone, Serialize)]
struct Code2FlowRunnerPayload {
    files: Vec<Code2FlowFilePayload>,
}

fn default_timeout_seconds() -> u64 {
    DEFAULT_TIMEOUT_SECONDS
}

fn default_max_files() -> usize {
    DEFAULT_MAX_FILES
}

pub fn execute_from_request_path(request_path: &Path) -> Code2FlowResponse {
    match fs::read_to_string(request_path)
        .ok()
        .and_then(|raw| serde_json::from_str::<Code2FlowRequest>(&raw).ok())
    {
        Some(request) => execute(request),
        None => failure_response("code2flow_exec_failed", "invalid_code2flow_request"),
    }
}

pub fn execute(request: Code2FlowRequest) -> Code2FlowResponse {
    let project_root = PathBuf::from(&request.project_root);

    let candidate_files = match iter_candidate_files(
        &project_root,
        &request.target_files,
        request.max_files.max(1),
    ) {
        Ok(paths) => paths,
        Err(error) => return failure_response("code2flow_exec_failed", &error),
    };
    if candidate_files.is_empty() {
        return Code2FlowResponse {
            ok: false,
            edges: BTreeMap::new(),
            blocked_reasons: vec!["code2flow_no_candidate_files".to_string()],
            used_engine: "fallback".to_string(),
            diagnostics: BTreeMap::new(),
            error: None,
        };
    }

    let files = match build_files_payload(&project_root, &candidate_files) {
        Ok(payload) => payload,
        Err(error) => return failure_response("code2flow_exec_failed", &error),
    };
    if files.is_empty() {
        return Code2FlowResponse {
            ok: false,
            edges: BTreeMap::new(),
            blocked_reasons: vec!["code2flow_no_candidate_files".to_string()],
            used_engine: "fallback".to_string(),
            diagnostics: BTreeMap::new(),
            error: None,
        };
    }

    let workspace_dir = scan_workspace_root()
        .join("code2flow-runtime")
        .join(Uuid::new_v4().to_string());
    if let Err(error) = fs::create_dir_all(&workspace_dir) {
        return failure_response(
            "code2flow_exec_failed",
            &format!("create_code2flow_workspace_failed:{error}"),
        );
    }

    let request_path = workspace_dir.join("request.json");
    let response_path = workspace_dir.join("response.json");
    let payload = Code2FlowRunnerPayload { files };
    let payload_text = match serde_json::to_string_pretty(&payload) {
        Ok(text) => text,
        Err(error) => return failure_response("code2flow_exec_failed", &error.to_string()),
    };
    if let Err(error) = fs::write(&request_path, payload_text) {
        return failure_response(
            "code2flow_exec_failed",
            &format!("write_request_failed:{error}"),
        );
    }

    let spec = RunnerSpec {
        scanner_type: "flow_parser".to_string(),
        image: request.image.unwrap_or_else(flow_parser_runner_image),
        workspace_dir: workspace_dir.display().to_string(),
        workspace_root_override: None,
        command: vec![
            "python3".to_string(),
            "/opt/flow-parser/flow_parser_runner.py".to_string(),
            "code2flow-callgraph".to_string(),
            "--request".to_string(),
            format!("{SCANNER_MOUNT_PATH}/request.json"),
            "--response".to_string(),
            format!("{SCANNER_MOUNT_PATH}/response.json"),
        ],
        timeout_seconds: request.timeout_seconds.max(1),
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
        return failure_response(
            "code2flow_exec_failed",
            runner_result
                .error
                .as_deref()
                .unwrap_or("code2flow_exec_failed"),
        );
    }

    let raw_response = match fs::read_to_string(&response_path) {
        Ok(text) => text,
        Err(_) => return failure_response("code2flow_exec_failed", "code2flow_missing_response"),
    };

    let response = normalize_runner_response(&raw_response);
    if response.ok {
        let _ = fs::remove_dir_all(&workspace_dir);
    }
    response
}

fn iter_candidate_files(
    project_root: &Path,
    target_files: &[String],
    max_files: usize,
) -> Result<Vec<PathBuf>, String> {
    if !project_root.is_dir() {
        return Err(format!("project_root_not_found:{}", project_root.display()));
    }

    if !target_files.is_empty() {
        let mut files = Vec::new();
        let rel_paths = target_files
            .iter()
            .map(|raw| normalize_rel_path(raw))
            .filter(|rel| !rel.is_empty())
            .collect::<BTreeSet<_>>();
        for rel in rel_paths {
            let path = project_root.join(&rel);
            if path.is_file() && is_supported_extension(&path) {
                files.push(path);
            }
            if files.len() >= max_files {
                break;
            }
        }
        return Ok(files);
    }

    let mut files = Vec::new();
    let mut stack = vec![project_root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let read_dir = fs::read_dir(&dir)
            .map_err(|error| format!("read_dir_failed:{}:{error}", dir.display()))?;
        for entry in read_dir.flatten() {
            let path = entry.path();
            let rel = path
                .strip_prefix(project_root)
                .ok()
                .map(|value| value.to_string_lossy().replace('\\', "/"))
                .unwrap_or_default();
            if rel.contains("/.git/") || rel.starts_with(".git/") {
                continue;
            }
            if rel.contains("/node_modules/") || rel.starts_with("node_modules/") {
                continue;
            }
            if path.is_dir() {
                stack.push(path);
            } else if path.is_file() && is_supported_extension(&path) {
                files.push(path);
                if files.len() >= max_files {
                    return Ok(files);
                }
            }
        }
    }

    Ok(files)
}

fn build_files_payload(
    project_root: &Path,
    files: &[PathBuf],
) -> Result<Vec<Code2FlowFilePayload>, String> {
    let mut payload = Vec::new();
    for path in files {
        let content = match fs::read(path) {
            Ok(bytes) => String::from_utf8_lossy(&bytes).to_string(),
            Err(_) => continue,
        };
        let rel = path
            .strip_prefix(project_root)
            .ok()
            .map(|value| value.to_string_lossy().replace('\\', "/"))
            .unwrap_or_else(|| path.to_string_lossy().replace('\\', "/"));
        payload.push(Code2FlowFilePayload {
            file_path: rel,
            content,
        });
    }
    Ok(payload)
}

fn normalize_runner_response(raw: &str) -> Code2FlowResponse {
    let parsed: serde_json::Value = match serde_json::from_str(raw) {
        Ok(value) => value,
        Err(error) => return failure_response("code2flow_exec_failed", &error.to_string()),
    };
    let Some(object) = parsed.as_object() else {
        return failure_response("code2flow_exec_failed", "invalid_runner_response");
    };

    let mut diagnostics = object
        .get("diagnostics")
        .and_then(|value| value.as_object())
        .map(|items| {
            items
                .iter()
                .map(|(key, value)| (key.clone(), json_value_as_string(value)))
                .collect::<BTreeMap<_, _>>()
        })
        .unwrap_or_default();

    let error = object
        .get("error")
        .map(json_value_as_string)
        .filter(|value| !value.is_empty());
    if let Some(error) = &error {
        diagnostics.insert("error".to_string(), error.clone());
    }

    let used_engine = object
        .get("used_engine")
        .map(json_value_as_string)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "fallback".to_string());

    if object.get("ok").and_then(|value| value.as_bool()) == Some(false) {
        let blocked_reasons =
            normalize_blocked_reasons(object.get("blocked_reasons"), diagnostics.get("error"));
        return Code2FlowResponse {
            ok: false,
            edges: BTreeMap::new(),
            blocked_reasons: if blocked_reasons.is_empty() {
                vec!["code2flow_exec_failed".to_string()]
            } else {
                blocked_reasons
            },
            used_engine,
            diagnostics,
            error,
        };
    }

    let mut edges = BTreeMap::new();
    if let Some(raw_edges) = object.get("edges").and_then(|value| value.as_object()) {
        for (src, targets) in raw_edges {
            if src.trim().is_empty() {
                continue;
            }
            let Some(items) = targets.as_array() else {
                continue;
            };
            let unique_targets = items
                .iter()
                .map(json_value_as_string)
                .filter(|value| !value.is_empty())
                .collect::<BTreeSet<_>>();
            if !unique_targets.is_empty() {
                edges.insert(src.clone(), unique_targets.into_iter().collect());
            }
        }
    }

    if edges.is_empty() {
        return Code2FlowResponse {
            ok: false,
            edges,
            blocked_reasons: vec!["code2flow_no_edges".to_string()],
            used_engine,
            diagnostics,
            error,
        };
    }

    diagnostics.insert(
        "edge_count".to_string(),
        edges.values().map(Vec::len).sum::<usize>().to_string(),
    );
    diagnostics.insert("node_count".to_string(), edges.len().to_string());

    Code2FlowResponse {
        ok: true,
        edges,
        blocked_reasons: Vec::new(),
        used_engine: if used_engine == "fallback" {
            "code2flow".to_string()
        } else {
            used_engine
        },
        diagnostics,
        error,
    }
}

fn normalize_blocked_reasons(
    blocked_reasons: Option<&serde_json::Value>,
    error_text: Option<&String>,
) -> Vec<String> {
    let reasons = blocked_reasons
        .and_then(|value| value.as_array())
        .map(|items| {
            items
                .iter()
                .map(json_value_as_string)
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    if reasons
        .iter()
        .any(|reason| reason == "code2flow_not_installed" || reason == "code2flow_binary_not_found")
    {
        return vec!["code2flow_not_installed".to_string()];
    }
    if matches!(error_text, Some(error) if error == "code2flow_binary_not_found") {
        return vec!["code2flow_not_installed".to_string()];
    }
    if !reasons.is_empty() {
        return reasons;
    }
    if matches!(error_text, Some(error) if !error.is_empty()) {
        return vec!["code2flow_exec_failed".to_string()];
    }
    Vec::new()
}

fn flow_parser_runner_image() -> String {
    env::var("FLOW_PARSER_RUNNER_IMAGE")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "vulhunter/flow-parser-runner:latest".to_string())
}

fn scan_workspace_root() -> PathBuf {
    env::var("SCAN_WORKSPACE_ROOT")
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("/tmp/vulhunter/scans"))
}

fn normalize_rel_path(raw_path: &str) -> String {
    raw_path
        .replace('\\', "/")
        .trim_start_matches("./")
        .to_string()
}

fn is_supported_extension(path: &Path) -> bool {
    let extension = path
        .extension()
        .map(|value| format!(".{}", value.to_string_lossy().to_lowercase()))
        .unwrap_or_default();
    SUPPORTED_EXTENSIONS.contains(&extension.as_str())
}

fn json_value_as_string(value: &serde_json::Value) -> String {
    value
        .as_str()
        .map(str::to_string)
        .unwrap_or_else(|| value.to_string())
}

fn failure_response(blocked_reason: &str, error: &str) -> Code2FlowResponse {
    let mut diagnostics = BTreeMap::new();
    if !error.is_empty() {
        diagnostics.insert("error".to_string(), error.to_string());
    }
    Code2FlowResponse {
        ok: false,
        edges: BTreeMap::new(),
        blocked_reasons: vec![blocked_reason.to_string()],
        used_engine: "fallback".to_string(),
        diagnostics,
        error: if error.is_empty() {
            None
        } else {
            Some(error.to_string())
        },
    }
}

#[cfg(test)]
mod tests {
    use super::{execute, normalize_runner_response, Code2FlowRequest};
    use std::{env, fs};
    use tempfile::TempDir;

    #[test]
    fn normalize_runner_response_maps_binary_not_found_to_not_installed() {
        let payload = r#"{
          "ok": false,
          "edges": {},
          "blocked_reasons": ["code2flow_not_installed"],
          "used_engine": "fallback",
          "diagnostics": {"binary_path": "", "error": "code2flow_binary_not_found"}
        }"#;

        let response = normalize_runner_response(payload);
        assert!(!response.ok);
        assert_eq!(response.blocked_reasons, vec!["code2flow_not_installed"]);
        assert_eq!(
            response.diagnostics.get("error").map(String::as_str),
            Some("code2flow_binary_not_found")
        );
    }

    #[test]
    fn normalize_runner_response_preserves_no_edges_reason() {
        let payload = r#"{
          "ok": false,
          "edges": {},
          "blocked_reasons": ["code2flow_no_edges"],
          "used_engine": "fallback",
          "diagnostics": {"stderr_excerpt": "generated graph without edges"}
        }"#;

        let response = normalize_runner_response(payload);
        assert!(!response.ok);
        assert_eq!(response.blocked_reasons, vec!["code2flow_no_edges"]);
    }

    #[test]
    fn normalize_runner_response_computes_edge_diagnostics() {
        let payload = r#"{
          "ok": true,
          "edges": {"caller": ["callee", "callee"]},
          "used_engine": "code2flow",
          "diagnostics": {"runner": "ok"}
        }"#;

        let response = normalize_runner_response(payload);
        assert!(response.ok);
        assert_eq!(
            response.edges.get("caller"),
            Some(&vec!["callee".to_string()])
        );
        assert_eq!(
            response.diagnostics.get("edge_count").map(String::as_str),
            Some("1")
        );
        assert_eq!(
            response.diagnostics.get("node_count").map(String::as_str),
            Some("1")
        );
    }

    #[test]
    fn execute_reports_no_candidate_files() {
        let temp_dir = TempDir::new().unwrap();
        fs::write(temp_dir.path().join("README.md"), "demo").unwrap();

        let response = execute(Code2FlowRequest {
            project_root: temp_dir.path().display().to_string(),
            target_files: Vec::new(),
            timeout_seconds: 10,
            max_files: 10,
            image: None,
        });

        assert!(!response.ok);
        assert_eq!(
            response.blocked_reasons,
            vec!["code2flow_no_candidate_files"]
        );
    }

    #[test]
    fn execute_uses_target_files_before_runner_invocation() {
        let temp_dir = TempDir::new().unwrap();
        fs::create_dir_all(temp_dir.path().join("src")).unwrap();
        fs::write(
            temp_dir.path().join("src").join("demo.py"),
            "def caller():\n    return 1\n",
        )
        .unwrap();
        env::set_var("BACKEND_DOCKER_BIN", "/definitely/missing/docker");

        let response = execute(Code2FlowRequest {
            project_root: temp_dir.path().display().to_string(),
            target_files: vec!["src/demo.py".to_string()],
            timeout_seconds: 5,
            max_files: 5,
            image: Some("vulhunter/flow-parser-runner:test".to_string()),
        });

        assert!(!response.ok);
        assert_eq!(response.blocked_reasons, vec!["code2flow_exec_failed"]);
    }

    #[test]
    fn iter_candidate_files_sorts_and_deduplicates_explicit_targets_before_truncation() {
        let temp_dir = TempDir::new().unwrap();
        fs::create_dir_all(temp_dir.path().join("src")).unwrap();
        fs::write(temp_dir.path().join("src").join("a.py"), "print('a')").unwrap();
        fs::write(temp_dir.path().join("src").join("b.py"), "print('b')").unwrap();

        let files = super::iter_candidate_files(
            temp_dir.path(),
            &[
                "src/b.py".to_string(),
                "src/a.py".to_string(),
                "src/b.py".to_string(),
            ],
            1,
        )
        .expect("files should resolve");

        assert_eq!(files.len(), 1);
        assert_eq!(
            files[0]
                .strip_prefix(temp_dir.path())
                .expect("relative path")
                .to_string_lossy()
                .replace('\\', "/"),
            "src/a.py"
        );
    }

    #[test]
    fn build_files_payload_keeps_non_utf8_sources_via_lossy_decoding() {
        let temp_dir = TempDir::new().unwrap();
        fs::create_dir_all(temp_dir.path().join("src")).unwrap();
        let file_path = temp_dir.path().join("src").join("demo.py");
        fs::write(&file_path, b"def caller():\n    return b'\xff'\n").unwrap();

        let payload = super::build_files_payload(temp_dir.path(), &[file_path])
            .expect("payload should build");

        assert_eq!(payload.len(), 1);
        assert_eq!(payload[0].file_path, "src/demo.py");
        assert!(payload[0].content.contains('\u{fffd}'));
    }
}
