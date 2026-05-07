//! A3S → docker fallback wrapper for opengrep scans.
//!
//! Wraps `a3s_box_runner::execute` with classify_a3s_error + docker fallback
//! per spec `deep-interview-a3s-perf-align-docker.md` ADR-A.
//!
//! Permit lifecycle: see ADR-A.P. Caller-provided OwnedSemaphorePermit is
//! reused across A3S + docker fallback path; never released within wrapper.
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

/// Failure classification for A3S runs that should trigger docker fallback.
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
        let r = classify_a3s_error(Some(1), "container OOMKilled", Duration::from_secs(10), None);
        assert_eq!(r, Some(A3sFailureReason::OomKilled));
    }

    #[test]
    fn classify_oom_via_stderr_oom_text() {
        let r = classify_a3s_error(Some(1), "fatal: out of memory", Duration::from_secs(10), None);
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
        let err = anyhow!("docker registry connection refused");
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
