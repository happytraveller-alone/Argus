//! Integration tests for `scan_with_fallback` (AC4).
//!
//! Verifies A3S → docker fallback paths trigger correctly per
//! `classify_a3s_error` priority (ImageCacheFailed > PreflightFailed >
//! exit-137 OomKilled > TimeoutExceeded > stderr OomKilled), and the
//! happy-path A3S success bypasses docker.
//!
//! Tracing assertion is deferred (no `tracing-test` dep available); tests
//! validate `ScanOutcome.runtime_used` + `a3s_failure_reason` directly.

use std::io::Write;
use std::sync::Mutex;

use anyhow::{anyhow, Result};
use async_trait::async_trait;
use tempfile::NamedTempFile;

use backend_rust::runtime::a3s_box_runner::{A3sBoxRunnerResult, A3sBoxRunnerSpec};
use backend_rust::runtime::runner::{ContainerRuntime, RunnerResult, RunnerSpec};
use backend_rust::scan::opengrep_a3s::{
    scan_with_fallback, A3sBoxExecutor, A3sFailureReason, DockerExecutor, RuntimeUsed, ScanOutput,
};

// ── Fakes ────────────────────────────────────────────────────────────────────

struct FakeA3sBoxExecutor {
    response: Mutex<Option<Result<A3sBoxRunnerResult>>>,
}

impl FakeA3sBoxExecutor {
    fn ok(r: A3sBoxRunnerResult) -> Self {
        Self {
            response: Mutex::new(Some(Ok(r))),
        }
    }
    fn err(msg: &'static str) -> Self {
        Self {
            response: Mutex::new(Some(Err(anyhow!(msg)))),
        }
    }
}

#[async_trait]
impl A3sBoxExecutor for FakeA3sBoxExecutor {
    async fn execute(&self, _spec: A3sBoxRunnerSpec) -> Result<A3sBoxRunnerResult> {
        self.response
            .lock()
            .unwrap()
            .take()
            .expect("FakeA3sBoxExecutor response taken twice")
    }
}

struct FakeDockerExecutor {
    called: Mutex<bool>,
}

impl FakeDockerExecutor {
    fn new() -> Self {
        Self {
            called: Mutex::new(false),
        }
    }
    fn was_called(&self) -> bool {
        *self.called.lock().unwrap()
    }
}

#[async_trait]
impl DockerExecutor for FakeDockerExecutor {
    async fn execute(&self, _spec: RunnerSpec) -> Result<RunnerResult> {
        *self.called.lock().unwrap() = true;
        // Return a generic non-success runner result; scan_with_fallback should
        // surface this verbatim in ScanOutput::Docker.
        Ok(RunnerResult {
            success: true,
            container_id: Some("fake-docker-fallback".to_string()),
            exit_code: 0,
            stdout_path: None,
            stderr_path: None,
            error: None,
        })
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

fn empty_a3s_spec() -> A3sBoxRunnerSpec {
    A3sBoxRunnerSpec::default()
}

fn empty_docker_spec_builder() -> impl FnOnce() -> RunnerSpec + Send + 'static {
    || RunnerSpec {
        scanner_type: "opengrep".to_string(),
        image: String::new(),
        container_runtime: ContainerRuntime::Docker,
        workspace_dir: String::new(),
        command: Vec::new(),
        timeout_seconds: 0,
        env: Default::default(),
        expected_exit_codes: vec![0],
        artifact_paths: Vec::new(),
        capture_stdout_path: None,
        capture_stderr_path: None,
        completion_summary_path: None,
        workspace_root_override: None,
        memory_limit_mb: None,
        memory_swap_limit_mb: None,
        cpu_limit: None,
        pids_limit: None,
        network_disabled: false,
        mount_plan: None,
    }
}

/// Write `text` to a NamedTempFile and return (path, file-keepalive).
/// Caller must keep the returned `NamedTempFile` alive until after
/// `scan_with_fallback` reads from `stderr_path`.
fn write_stderr(text: &str) -> (String, NamedTempFile) {
    let mut tmp = NamedTempFile::new().expect("tempfile create");
    tmp.write_all(text.as_bytes()).expect("tempfile write");
    let path = tmp.path().to_string_lossy().into_owned();
    (path, tmp)
}

fn make_runner_result(
    exit_code: i32,
    stderr_path: Option<String>,
    success: bool,
) -> A3sBoxRunnerResult {
    A3sBoxRunnerResult {
        success,
        box_name: None,
        exit_code,
        stdout_path: None,
        stderr_path,
        error: None,
    }
}

// ── Cases ────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn case_oom_via_exit_137_triggers_docker_fallback() {
    let a3s_result = make_runner_result(137, None, false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-1",
        Some("project-test"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::DockerFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::OomKilled)
    );
    assert!(docker_exec.was_called(), "docker executor must be invoked");
    assert!(matches!(outcome.output, ScanOutput::Docker(_)));
}

#[tokio::test]
async fn case_oom_via_stderr_text_triggers_docker_fallback() {
    let (stderr_path, _keep) = write_stderr("container OOMKilled by cgroup");
    let a3s_result = make_runner_result(1, Some(stderr_path), false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-2",
        None,
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::DockerFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::OomKilled)
    );
    assert!(docker_exec.was_called());
}

#[tokio::test]
async fn case_preflight_kvm_beats_oom_priority() {
    // exit 137 + KVM-unavailable stderr — classifier MUST pick PreflightFailed.
    let (stderr_path, _keep) = write_stderr("KVM is not available\nprocess killed (signal: 9)");
    let a3s_result = make_runner_result(137, Some(stderr_path), false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-3",
        Some("project-priority"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::DockerFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::PreflightFailed),
        "PreflightFailed must beat OomKilled when stderr has both"
    );
    assert!(docker_exec.was_called());
}

#[tokio::test]
async fn case_spawn_fail_executor_err_triggers_docker_fallback() {
    // executor returns Err(...) — treat as image cache / spawn failure.
    // classify_a3s_error sees Some(image_cache_err) → ImageCacheFailed reason.
    let a3s_exec = FakeA3sBoxExecutor::err("a3s-box binary not found in PATH");
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-4",
        None,
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::DockerFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::ImageCacheFailed),
        "executor Err is classified as ImageCacheFailed (image_cache_err is Some)"
    );
    assert!(docker_exec.was_called());
}

#[tokio::test]
async fn case_a3s_non_success_with_clean_stderr_falls_back_as_spawn_failed() {
    // exit 1, stderr empty, elapsed < 900s — classify_a3s_error returns None,
    // but runner_result.success == false, so fallback triggers with
    // SpawnFailed (default reason in unwrap_or branch).
    let a3s_result = make_runner_result(1, None, false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-5",
        Some("project-spawn"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::DockerFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::SpawnFailed),
        "non-success without classifiable reason should default to SpawnFailed"
    );
    assert!(docker_exec.was_called());
}

#[tokio::test]
async fn case_success_no_fallback() {
    let a3s_result = make_runner_result(0, None, true);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let docker_exec = FakeDockerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &docker_exec,
        empty_a3s_spec(),
        empty_docker_spec_builder(),
        "task-test-6",
        Some("project-happy"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::A3s);
    assert_eq!(outcome.a3s_failure_reason, None);
    assert!(
        !docker_exec.was_called(),
        "docker executor MUST NOT be invoked on A3S success"
    );
    assert!(matches!(outcome.output, ScanOutput::A3s(_)));
}
