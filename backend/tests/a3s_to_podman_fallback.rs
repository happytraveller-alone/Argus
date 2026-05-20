//! Integration tests for `scan_with_fallback` (AC4).
//!
//! Verifies A3S → Podman fallback paths trigger correctly per
//! `classify_a3s_error` priority (ImageCacheFailed > PreflightFailed >
//! exit-137 OomKilled > TimeoutExceeded > stderr OomKilled), and the
//! happy-path A3S success bypasses Podman.
//!
//! Tracing assertion is deferred (no `tracing-test` dep available); tests
//! validate `ScanOutcome.runtime_used` + `a3s_failure_reason` directly.

use std::io::Write;
use std::sync::Mutex;

use anyhow::{Result, anyhow};
use async_trait::async_trait;
use tempfile::NamedTempFile;

use backend_rust::runtime::a3s_box_runner::{A3sBoxRunnerResult, A3sBoxRunnerSpec};
use backend_rust::runtime::runner::{
    ContainerRuntime, RunnerMount, RunnerMountPlan, RunnerResult, RunnerSpec,
};
use backend_rust::scan::opengrep_a3s::{
    A3sBoxExecutor, A3sFailureReason, FallbackRunnerExecutor, RuntimeUsed, ScanOutput,
    scan_with_fallback,
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

struct FakeFallbackRunnerExecutor {
    captured_spec: Mutex<Option<RunnerSpec>>,
}

impl FakeFallbackRunnerExecutor {
    fn new() -> Self {
        Self {
            captured_spec: Mutex::new(None),
        }
    }
    fn was_called(&self) -> bool {
        self.captured_spec.lock().unwrap().is_some()
    }
    fn captured_spec(&self) -> RunnerSpec {
        self.captured_spec
            .lock()
            .unwrap()
            .clone()
            .expect("fallback spec captured")
    }
}

#[async_trait]
impl FallbackRunnerExecutor for FakeFallbackRunnerExecutor {
    async fn execute(&self, spec: RunnerSpec) -> Result<RunnerResult> {
        *self.captured_spec.lock().unwrap() = Some(spec);
        // Return a generic success runner result; scan_with_fallback should
        // surface this verbatim in ScanOutput::Fallback.
        Ok(RunnerResult {
            success: true,
            container_id: Some("fake-podman-fallback".to_string()),
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

fn empty_fallback_spec_builder() -> impl FnOnce() -> Result<RunnerSpec> + Send + 'static {
    || {
        Ok(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: String::new(),
            container_runtime: ContainerRuntime::Podman,
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
            network_disabled: true,
            mount_plan: Some(RunnerMountPlan::new(vec![
                RunnerMount::read_only("/tmp/source", "/scan/source"),
                RunnerMount::read_only("/tmp/opengrep-rules", "/scan/opengrep-rules"),
                RunnerMount::read_write("/tmp/output", "/scan/output"),
            ])),
        })
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

fn assert_podman_fallback_spec(spec: &RunnerSpec) {
    assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
    assert!(spec.network_disabled, "fallback must disable networking");
    let mount_plan = spec.mount_plan.as_ref().expect("fallback mount plan");
    assert!(
        mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/source" && mount.read_only),
        "source mount must be read-only: {mount_plan:?}"
    );
    assert!(
        mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/opengrep-rules" && mount.read_only),
        "rules mount must be read-only: {mount_plan:?}"
    );
    assert!(
        mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/output" && !mount.read_only),
        "output mount must be writable: {mount_plan:?}"
    );
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
async fn case_oom_via_exit_137_triggers_podman_fallback() {
    let a3s_result = make_runner_result(137, None, false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-1",
        Some("project-test"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::PodmanFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::OomKilled)
    );
    assert!(
        fallback_exec.was_called(),
        "fallback runner executor must be invoked"
    );
    assert_podman_fallback_spec(&fallback_exec.captured_spec());
    assert!(matches!(outcome.output, ScanOutput::Fallback(_)));
}

#[tokio::test]
async fn case_oom_via_stderr_text_triggers_podman_fallback() {
    let (stderr_path, _keep) = write_stderr("container OOMKilled by cgroup");
    let a3s_result = make_runner_result(1, Some(stderr_path), false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-2",
        None,
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::PodmanFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::OomKilled)
    );
    assert!(fallback_exec.was_called());
    assert_podman_fallback_spec(&fallback_exec.captured_spec());
}

#[tokio::test]
async fn case_preflight_kvm_beats_oom_priority() {
    // exit 137 + KVM-unavailable stderr — classifier MUST pick PreflightFailed.
    let (stderr_path, _keep) = write_stderr("KVM is not available\nprocess killed (signal: 9)");
    let a3s_result = make_runner_result(137, Some(stderr_path), false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-3",
        Some("project-priority"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::PodmanFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::PreflightFailed),
        "PreflightFailed must beat OomKilled when stderr has both"
    );
    assert!(fallback_exec.was_called());
    assert_podman_fallback_spec(&fallback_exec.captured_spec());
}

#[tokio::test]
async fn case_spawn_fail_executor_err_triggers_podman_fallback() {
    // executor returns Err(...) — treat as image cache / spawn failure.
    // classify_a3s_error sees Some(image_cache_err) → ImageCacheFailed reason.
    let a3s_exec = FakeA3sBoxExecutor::err("a3s-box binary not found in PATH");
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-4",
        None,
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::PodmanFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::ImageCacheFailed),
        "executor Err is classified as ImageCacheFailed (image_cache_err is Some)"
    );
    assert!(fallback_exec.was_called());
    assert_podman_fallback_spec(&fallback_exec.captured_spec());
}

#[tokio::test]
async fn case_a3s_non_success_with_clean_stderr_falls_back_as_spawn_failed() {
    // exit 1, stderr empty, elapsed < 900s — classify_a3s_error returns None,
    // but runner_result.success == false, so fallback triggers with
    // SpawnFailed (default reason in unwrap_or branch).
    let a3s_result = make_runner_result(1, None, false);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-5",
        Some("project-spawn"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::PodmanFallback);
    assert_eq!(
        outcome.a3s_failure_reason,
        Some(A3sFailureReason::SpawnFailed),
        "non-success without classifiable reason should default to SpawnFailed"
    );
    assert!(fallback_exec.was_called());
    assert_podman_fallback_spec(&fallback_exec.captured_spec());
}

#[tokio::test]
async fn case_success_no_fallback() {
    let a3s_result = make_runner_result(0, None, true);
    let a3s_exec = FakeA3sBoxExecutor::ok(a3s_result);
    let fallback_exec = FakeFallbackRunnerExecutor::new();

    let outcome = scan_with_fallback(
        &a3s_exec,
        &fallback_exec,
        empty_a3s_spec(),
        empty_fallback_spec_builder(),
        "task-test-6",
        Some("project-happy"),
    )
    .await
    .expect("scan_with_fallback ok");

    assert_eq!(outcome.runtime_used, RuntimeUsed::A3s);
    assert_eq!(outcome.a3s_failure_reason, None);
    assert!(
        !fallback_exec.was_called(),
        "fallback executor MUST NOT be invoked on A3S success"
    );
    assert!(matches!(outcome.output, ScanOutput::A3s(_)));
}
