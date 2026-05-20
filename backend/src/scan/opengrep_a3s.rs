//! A3S → Podman fallback wrapper for opengrep scans.
//!
//! Wraps `a3s_box_runner::execute` with classify_a3s_error + Podman fallback.
//!
//! Permit lifecycle: see ADR-A.P. Caller-provided OwnedSemaphorePermit is
//! reused across A3S + Podman fallback path; never released within wrapper.
//!
//! `classify_a3s_error` priority order (matches ADR-C table):
//!   1. ImageCacheFailed (caller passes Some when ensure_a3s_box_image_cached failed)
//!   2. PreflightFailed (PREFLIGHT_NEEDLES match in stderr_tail)
//!   3. OomKilled (exit_code == 137)
//!   4. TimeoutExceeded (elapsed >= 900s)
//!   5. OomKilled (OOM_PATTERNS or "killed" + "signal: 9" in stderr_tail)
//!
//! PreflightFailed must beat OomKilled when stderr contains both "KVM unavailable"
//! and "killed" — otherwise we'd misroute environment failures as OOM and lose
//! diagnostic value (AC8 perf gap report depends on reason field).

use std::time::Duration;

use anyhow::Result;
use async_trait::async_trait;

use crate::runtime::a3s_box_runner::{self, A3sBoxRunnerResult, A3sBoxRunnerSpec};

/// Failure classification for A3S runs that should trigger Podman fallback.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum A3sFailureReason {
    PreflightFailed,
    ImageCacheFailed,
    OomKilled,
    TimeoutExceeded,
    SpawnFailed,
}

/// 4 needle 顺序与 a3s_box_runner.rs:520-533 a3s_box_virtualization_error_text 源码一致.
const PREFLIGHT_NEEDLES: &[&str] = &[
    "Virtualization: not available",
    "KVM is not available",
    "Error creating the Kvm object",
    "Exec socket did not appear",
];

const OOM_PATTERNS: &[&str] = &["OOMKilled", "out of memory"];

/// 900s = `DEFAULT_A3S_BOX_TIMEOUT_SECONDS` per `runtime/a3s_box_runner.rs`.
pub const A3S_TIMEOUT_THRESHOLD: Duration = Duration::from_secs(900);

/// Pluggable A3S executor for testability.
///
/// Production path: `DefaultA3sBoxExecutor` calls `tokio::task::spawn_blocking`
/// to wrap the synchronous `a3s_box_runner::execute(spec)`.
/// Test path: `FakeA3sBoxExecutor` returns canned results.
#[async_trait]
pub trait A3sBoxExecutor: Send + Sync {
    async fn execute(&self, spec: A3sBoxRunnerSpec) -> Result<A3sBoxRunnerResult>;
}

pub struct DefaultA3sBoxExecutor;

#[async_trait]
impl A3sBoxExecutor for DefaultA3sBoxExecutor {
    async fn execute(&self, spec: A3sBoxRunnerSpec) -> Result<A3sBoxRunnerResult> {
        tokio::task::spawn_blocking(move || a3s_box_runner::execute(spec))
            .await
            .map_err(anyhow::Error::from)
    }
}

/// Classify A3S failure (None = no fallback needed).
pub fn classify_a3s_error(
    exit_code: Option<i32>,
    stderr_tail: &str,
    elapsed: Duration,
    image_cache_err: Option<&anyhow::Error>,
) -> Option<A3sFailureReason> {
    if image_cache_err.is_some() {
        return Some(A3sFailureReason::ImageCacheFailed);
    }
    if PREFLIGHT_NEEDLES.iter().any(|n| stderr_tail.contains(n)) {
        return Some(A3sFailureReason::PreflightFailed);
    }
    if exit_code == Some(137) {
        return Some(A3sFailureReason::OomKilled);
    }
    if elapsed >= A3S_TIMEOUT_THRESHOLD {
        return Some(A3sFailureReason::TimeoutExceeded);
    }
    if OOM_PATTERNS.iter().any(|n| stderr_tail.contains(n)) {
        return Some(A3sFailureReason::OomKilled);
    }
    if stderr_tail.contains("killed") && stderr_tail.contains("signal: 9") {
        return Some(A3sFailureReason::OomKilled);
    }
    None
}

// ── scan_with_fallback ────────────────────────────────────────────────────────

/// Pluggable fallback runner for testability (mirrors `A3sBoxExecutor`).
///
/// Production path: `DefaultFallbackRunnerExecutor` calls `tokio::task::spawn_blocking`
/// to wrap the synchronous `runner::execute(spec)`.
/// Test path: `FakeFallbackRunnerExecutor` returns canned `RunnerResult`.
#[async_trait]
pub trait FallbackRunnerExecutor: Send + Sync {
    async fn execute(
        &self,
        spec: crate::runtime::runner::RunnerSpec,
    ) -> Result<crate::runtime::runner::RunnerResult>;
}

pub struct DefaultFallbackRunnerExecutor;

#[async_trait]
impl FallbackRunnerExecutor for DefaultFallbackRunnerExecutor {
    async fn execute(
        &self,
        spec: crate::runtime::runner::RunnerSpec,
    ) -> Result<crate::runtime::runner::RunnerResult> {
        tokio::task::spawn_blocking(move || crate::runtime::runner::execute(spec))
            .await
            .map_err(anyhow::Error::from)
    }
}

/// Runtime path actually used for a single scan attempt.
///
/// Reported via tracing + returned in `ScanOutcome` for caller to set
/// `effective_executor_label` (see `static_tasks.rs` A3sBox dispatch).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeUsed {
    /// A3S path completed (success — no fallback needed).
    A3s,
    /// A3S failed and Podman fallback path completed.
    PodmanFallback,
}

/// Raw scan output — caller pattern-matches and post-processes per A3S
/// vs fallback-runner SARIF/log conventions (already split in static_tasks.rs).
pub enum ScanOutput {
    A3s(A3sBoxRunnerResult),
    Fallback(crate::runtime::runner::RunnerResult),
}

/// Output of `scan_with_fallback`.
///
/// `a3s_failure_reason` is `Some` iff `runtime_used == PodmanFallback` (i.e.
/// Podman fallback took over because A3S classification returned a non-`None` reason).
pub struct ScanOutcome {
    pub runtime_used: RuntimeUsed,
    pub a3s_failure_reason: Option<A3sFailureReason>,
    /// Underlying scan output. Variant depends on which path produced it:
    /// - `A3s` → `A3sBoxRunnerResult` from A3S executor
    /// - `PodmanFallback` → `RunnerResult` from fallback executor
    pub output: ScanOutput,
}

/// Read `stderr_tail` from `A3sBoxRunnerResult.stderr_path` (best-effort).
///
/// Returns empty string when path is absent or unreadable. Used only for
/// classification — failure to read just degrades classification fidelity,
/// never blocks the fallback decision.
async fn read_a3s_stderr_tail(stderr_path: Option<&str>) -> String {
    let Some(path) = stderr_path else {
        return String::new();
    };
    tokio::fs::read_to_string(path).await.unwrap_or_default()
}

/// Run an opengrep scan via A3S, falling back to Podman on classified failure.
///
/// Permit lifecycle (ADR-A.P, Option P1 reuse): the resource permit must be
/// held in the caller's scope across this call so it covers both the A3S
/// attempt and the Podman fallback attempt. We do NOT take it as a parameter
/// to stay decoupled from the caller's permit type (e.g.,
/// `OpengrepResourcePermit` vs `tokio::sync::OwnedSemaphorePermit`); the
/// caller is responsible for dropping it after `.await?` returns.
///
/// Podman fallback spec construction is delegated to `fallback_spec_builder` closure
/// (Option α from ADR-A): static_tasks.rs invokes its private
/// `build_opengrep_runner_spec` inside the closure, avoiding pub-ifying that
/// helper. Closure runs only when fallback triggers (lazy).
///
/// Tracing: on fallback, emits `tracing::warn!(stage = "a3s_to_podman_fallback",
/// reason, task_id, project_id, elapsed_ms, exit_code, ...)` per AC4.
pub async fn scan_with_fallback<F>(
    a3s_executor: &dyn A3sBoxExecutor,
    fallback_executor: &dyn FallbackRunnerExecutor,
    a3s_spec: A3sBoxRunnerSpec,
    fallback_spec_builder: F,
    task_id: &str,
    project_id: Option<&str>,
) -> Result<ScanOutcome>
where
    F: FnOnce() -> Result<crate::runtime::runner::RunnerSpec> + Send + 'static,
{
    use std::time::Instant;

    let start = Instant::now();
    // Capture workspace_dir before spec is moved into executor — needed to
    // recover meta JSON for fallback diagnostic before run_opengrep_scan_inner
    // wipes the workspace at the happy-path cleanup.
    let captured_workspace_dir = a3s_spec.workspace_dir.clone();

    // ── A3S attempt ───────────────────────────────────────────────────────
    let a3s_result = a3s_executor.execute(a3s_spec).await;
    let elapsed = start.elapsed();

    let (a3s_runner_result, image_cache_err): (Option<A3sBoxRunnerResult>, Option<anyhow::Error>) =
        match a3s_result {
            Ok(r) => (Some(r), None),
            Err(e) => (None, Some(e)),
        };

    let stderr_tail = match a3s_runner_result.as_ref() {
        Some(r) => read_a3s_stderr_tail(r.stderr_path.as_deref()).await,
        None => String::new(),
    };
    let exit_code = a3s_runner_result.as_ref().map(|r| r.exit_code);
    let runner_success = a3s_runner_result.as_ref().map(|r| r.success);
    let runner_error = a3s_runner_result.as_ref().and_then(|r| r.error.clone());

    let reason = classify_a3s_error(exit_code, &stderr_tail, elapsed, image_cache_err.as_ref());

    // Success path: A3S returned a result and classifier says no fallback needed.
    if let Some(r) = a3s_runner_result {
        if reason.is_none() && r.success {
            return Ok(ScanOutcome {
                runtime_used: RuntimeUsed::A3s,
                a3s_failure_reason: None,
                output: ScanOutput::A3s(r),
            });
        }
    }

    // Fallback path: A3S returned non-success or executor failed.
    let fallback_reason = reason.unwrap_or(A3sFailureReason::SpawnFailed);

    // ── Diagnostic side-channel ─────────────────────────────────────────
    // Persist fallback context to /tmp/Argus/last-a3s-fallback.json so
    // operators can root-cause silent A3S failures even when RUST_LOG /
    // tracing-subscriber filtering swallows the warn! event below. Best-
    // effort write — never blocks the fallback path.
    let stderr_tail_last_2k: String = if stderr_tail.len() > 2048 {
        stderr_tail[stderr_tail.len() - 2048..].to_string()
    } else {
        stderr_tail.clone()
    };
    let diag = serde_json::json!({
        "stage": "a3s_to_podman_fallback",
        "reason": format!("{:?}", fallback_reason),
        "task_id": task_id,
        "project_id": project_id.unwrap_or(""),
        "elapsed_ms": elapsed.as_millis() as u64,
        "exit_code": exit_code,
        "a3s_success": runner_success,
        "a3s_runner_error": runner_error,
        "image_cache_err": image_cache_err.as_ref().map(|e| e.to_string()),
        "stderr_tail_len": stderr_tail.len(),
        "stderr_tail_last_2k": stderr_tail_last_2k,
    });
    // Snapshot the a3s-box-runner.json meta + stdout/stderr log files from
    // the captured workspace BEFORE run_opengrep_scan_inner wipes it on
    // success-via-fallback. The wrapped error from runner_result.error only
    // carries the high-level "Exec socket did not appear" bail message; we
    // need the raw a3s-box stdout/stderr to root-cause why.
    let workspace_path = std::path::Path::new(&captured_workspace_dir);
    let meta_snapshot =
        std::fs::read_to_string(workspace_path.join("meta/a3s-box-runner.json")).ok();
    let stdout_log_snapshot =
        std::fs::read_to_string(workspace_path.join("logs/a3s-box-stdout.log")).ok();
    let stderr_log_snapshot =
        std::fs::read_to_string(workspace_path.join("logs/a3s-box-stderr.log")).ok();
    let mut diag = diag;
    if let Some(obj) = diag.as_object_mut() {
        if let Some(meta) = meta_snapshot {
            obj.insert("meta_json".to_string(), serde_json::Value::String(meta));
        }
        if let Some(stdout_log) = stdout_log_snapshot {
            obj.insert(
                "a3s_box_stdout_log".to_string(),
                serde_json::Value::String(stdout_log),
            );
        }
        if let Some(stderr_log) = stderr_log_snapshot {
            obj.insert(
                "a3s_box_stderr_log".to_string(),
                serde_json::Value::String(stderr_log),
            );
        }
    }
    let diag_path = std::env::var("ARGUS_A3S_FALLBACK_DIAG_PATH")
        .unwrap_or_else(|_| "/tmp/Argus/scans/last-a3s-fallback.json".to_string());
    let _ = std::fs::write(
        &diag_path,
        serde_json::to_vec_pretty(&diag).unwrap_or_default(),
    );

    tracing::warn!(
        stage = "a3s_to_podman_fallback",
        reason = ?fallback_reason,
        task_id = %task_id,
        project_id = project_id.unwrap_or(""),
        elapsed_ms = elapsed.as_millis() as u64,
        exit_code = ?exit_code,
        stderr_tail_len = stderr_tail.len(),
        "A3S opengrep failed; falling back to Podman (permit reused)"
    );

    // Build Podman spec via caller-injected closure (Option α from ADR-A).
    let fallback_spec = tokio::task::spawn_blocking(fallback_spec_builder)
        .await
        .map_err(anyhow::Error::from)??;

    // Permit reused across Podman fallback run (ADR-A.P P1) — caller's scope holds it.
    let fallback_result = fallback_executor.execute(fallback_spec).await?;

    Ok(ScanOutcome {
        runtime_used: RuntimeUsed::PodmanFallback,
        a3s_failure_reason: Some(fallback_reason),
        output: ScanOutput::Fallback(fallback_result),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::anyhow;

    #[test]
    fn classify_oom_via_exit_137() {
        let r = classify_a3s_error(Some(137), "", Duration::from_secs(10), None);
        assert_eq!(r, Some(A3sFailureReason::OomKilled));
    }

    #[test]
    fn classify_oom_via_stderr_oomkilled() {
        let r = classify_a3s_error(
            Some(1),
            "container OOMKilled",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::OomKilled));
    }

    #[test]
    fn classify_oom_via_stderr_oom_text() {
        let r = classify_a3s_error(
            Some(1),
            "fatal: out of memory",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::OomKilled));
    }

    #[test]
    fn classify_oom_via_signal_9() {
        let r = classify_a3s_error(
            Some(1),
            "process killed (signal: 9)",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::OomKilled));
    }

    #[test]
    fn classify_timeout() {
        let r = classify_a3s_error(Some(1), "", Duration::from_secs(901), None);
        assert_eq!(r, Some(A3sFailureReason::TimeoutExceeded));
    }

    #[test]
    fn classify_virtualization_unavailable() {
        let r = classify_a3s_error(
            Some(1),
            "Virtualization: not available on this host",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::PreflightFailed));
    }

    #[test]
    fn classify_kvm_object_error() {
        let r = classify_a3s_error(
            Some(1),
            "Error creating the Kvm object",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::PreflightFailed));
    }

    #[test]
    fn classify_exec_socket_failure() {
        let r = classify_a3s_error(
            Some(1),
            "Exec socket did not appear",
            Duration::from_secs(10),
            None,
        );
        assert_eq!(r, Some(A3sFailureReason::PreflightFailed));
    }

    #[test]
    fn classify_image_cache_failed() {
        let err = anyhow!("Podman registry connection refused");
        let r = classify_a3s_error(Some(0), "", Duration::from_secs(0), Some(&err));
        assert_eq!(r, Some(A3sFailureReason::ImageCacheFailed));
    }

    #[test]
    fn classify_normal_pass() {
        let r = classify_a3s_error(
            Some(0),
            "scan complete: 100 findings",
            Duration::from_secs(60),
            None,
        );
        assert_eq!(r, None);
    }

    #[test]
    fn classify_priority_preflight_over_oom() {
        // stderr 同时含 KVM unavailable + signal 9 — 必须优先识别为 PreflightFailed
        let stderr = "KVM is not available\nprocess killed (signal: 9)";
        let r = classify_a3s_error(Some(137), stderr, Duration::from_secs(10), None);
        assert_eq!(r, Some(A3sFailureReason::PreflightFailed));
    }

    #[test]
    fn executor_trait_compile() {
        // Compile-time Send + Sync check: a3s box trait object is sendable across threads.
        fn assert_send<T: Send + Sync>(_: &T) {}
        let exec = DefaultA3sBoxExecutor;
        assert_send(&exec);
    }
}
