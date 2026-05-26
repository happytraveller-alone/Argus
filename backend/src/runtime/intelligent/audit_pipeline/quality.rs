//! Per-stage output quality gate with bounded retry and soft-degrade.
//!
//! Each of the 8 pipeline stages declares a [`GatePolicy`] — a label describing
//! the minimum acceptable output and a `max_retries` budget. The
//! [`run_stage_with_retry`] helper wraps any stage invocation so that:
//!
//! 1. The stage runs at least once (`attempt = 0`).
//! 2. If the predicate fails, the helper retries with an *amplified prompt*
//!    (a free-form suffix passed back into the stage's `run()` call) until the
//!    budget is exhausted.
//! 3. When the budget is exhausted and the predicate still fails, the helper
//!    sets `ctx.partial_analysis = true`, emits a `stage_quality_gate_failed`
//!    event, and **returns the insufficient output as Ok**. The pipeline keeps
//!    flowing — this is the soft-degrade requested by the user (mirrors the
//!    existing `hunt_fallback` pattern at `stages/hunt.rs:724`).
//!
//! See the spec at `.omc/specs/deep-dive-audit-pipeline-stage-output-retry.md`.

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use anyhow::Result;
use serde_json::json;

use crate::runtime::intelligent::types::IntelligentTaskEvent;

use super::context::{AuditStage, PipelineEventSink};

/// Per-stage minimum-output policy plus retry budget.
///
/// `max_retries` counts retries AFTER the first attempt. `max_retries == 0`
/// means a single attempt with no retry (useful for stages whose empty output
/// is a legitimate signal — `gapfill` / `feedback`).
#[derive(Debug, Clone, Copy)]
pub struct GatePolicy {
    /// Short human-readable description of the predicate. Echoed in retry
    /// prompts and the `stage_quality_gate_failed` event.
    pub label: &'static str,
    /// Number of retries permitted AFTER the first attempt. Total attempts =
    /// `max_retries + 1`.
    pub max_retries: u32,
}

impl GatePolicy {
    pub const fn new(label: &'static str, max_retries: u32) -> Self {
        Self { label, max_retries }
    }
}

/// Per-stage gates for the full 8-stage pipeline. Hard-coded defaults match
/// the spec's default-policy table; tests may override individual fields.
#[derive(Debug, Clone, Copy)]
pub struct StageGatesPolicy {
    pub recon: GatePolicy,
    pub hunt: GatePolicy,
    pub validate: GatePolicy,
    pub gapfill: GatePolicy,
    pub dedupe: GatePolicy,
    pub trace: GatePolicy,
    pub feedback: GatePolicy,
    pub report: GatePolicy,
}

impl Default for StageGatesPolicy {
    fn default() -> Self {
        Self {
            recon: GatePolicy::new("initial_tasks >= 1", 2),
            hunt: GatePolicy::new("findings >= 1 OR input tasks empty", 3),
            validate: GatePolicy::new(
                "validation findings count >= hunt findings count",
                2,
            ),
            gapfill: GatePolicy::new("(no gate — empty new_tasks is legal)", 0),
            dedupe: GatePolicy::new(
                "groups >= 1 when input has confirmed findings",
                1,
            ),
            trace: GatePolicy::new(
                "traces >= confirmed findings count",
                1,
            ),
            feedback: GatePolicy::new("(no gate — empty new_tasks is legal)", 0),
            report: GatePolicy::new("summary non-empty (>= 32 chars)", 2),
        }
    }
}

/// Reason a stage's output failed the gate predicate, plus a short summary of
/// the output the gate saw. Both fields end up in the retry prompt
/// amplification and the `stage_quality_gate_failed` event payload.
#[derive(Debug, Clone)]
pub struct GateFailure {
    pub reason: String,
    pub last_output_summary: String,
}

impl GateFailure {
    pub fn new(reason: impl Into<String>, last_output_summary: impl Into<String>) -> Self {
        Self {
            reason: reason.into(),
            last_output_summary: last_output_summary.into(),
        }
    }
}

/// Build the retry-prompt amplification text — the suffix appended to the
/// stage's prompt on retry attempts. Mirrors `invoke_json::repair_prompt` in
/// shape: short, factual, asks the LLM to re-emit valid output.
fn build_amplification(gate: &GatePolicy, failure: &GateFailure) -> String {
    format!(
        "\n\n---\nRETRY: Previous attempt produced insufficient output ({}). \
         The required minimum for this stage is: {}. \
         Re-emit the JSON object with valid output that meets the minimum. \
         Do not include this retry notice or prose in the response.",
        failure.last_output_summary, gate.label,
    )
}

/// Run a stage's async `run()` under a quality gate with bounded retries.
///
/// `attempt` is a closure that re-invokes the stage's `run()`. It receives an
/// `Option<String>` amplification suffix — `None` on the first call, `Some(_)`
/// on retries. Stages append the suffix to their prompt before calling the
/// LLM.
///
/// `predicate` evaluates the returned output. `Ok(())` means the gate passes
/// and the helper returns immediately. `Err(GateFailure)` triggers a retry.
///
/// When all retries are exhausted, the helper sets `partial_analysis = true`,
/// emits `stage_quality_gate_failed`, and **returns the last (insufficient)
/// output as `Ok`** — the pipeline keeps flowing.
///
/// Stages that fail at the LLM transport layer (i.e. `attempt` itself returns
/// `Err`) propagate that error up immediately — gate retries are for
/// quality, not connectivity.
pub async fn run_stage_with_retry<T, F, Fut, P>(
    gate: &GatePolicy,
    stage: AuditStage,
    partial_analysis: &Arc<AtomicBool>,
    events: &PipelineEventSink,
    attempt: F,
    predicate: P,
) -> Result<T>
where
    F: Fn(Option<String>) -> Fut,
    Fut: std::future::Future<Output = Result<T>>,
    P: Fn(&T) -> Result<(), GateFailure>,
{
    let mut last_failure: Option<GateFailure> = None;

    for attempt_idx in 0u32..=gate.max_retries {
        let amplification = match (attempt_idx, last_failure.as_ref()) {
            (0, _) | (_, None) => None,
            (_, Some(failure)) => Some(build_amplification(gate, failure)),
        };

        if attempt_idx > 0 {
            let failure = last_failure
                .as_ref()
                .expect("retry path has prior failure");
            events.emit(IntelligentTaskEvent::new("stage_retry").with_data(json!({
                "stage": stage.as_str(),
                "attempt": attempt_idx,
                "predicateLabel": gate.label,
                "lastOutputSummary": failure.last_output_summary,
                "reason": failure.reason,
            })));
        }

        let output = attempt(amplification).await?;
        match predicate(&output) {
            Ok(()) => return Ok(output),
            Err(failure) => {
                if attempt_idx >= gate.max_retries {
                    // Soft-degrade: flag partial analysis, emit event, return
                    // the insufficient output so downstream stages keep flowing.
                    partial_analysis.store(true, Ordering::Relaxed);
                    events.emit(
                        IntelligentTaskEvent::new("stage_quality_gate_failed").with_data(json!({
                            "stage": stage.as_str(),
                            "attempts": attempt_idx + 1,
                            "predicateLabel": gate.label,
                            "lastOutputSummary": failure.last_output_summary,
                            "reason": failure.reason,
                        })),
                    );
                    return Ok(output);
                }
                last_failure = Some(failure);
            }
        }
    }

    // for-loop with inclusive upper bound `0..=max_retries` always terminates
    // via one of the returns above; this is unreachable but keeps the type
    // checker happy.
    unreachable!("run_stage_with_retry exited the loop without returning")
}

/// `partial_analysis`-only variant of [`run_stage_with_retry`] for stages
/// whose gate is always-true (`gapfill`, `feedback`). Single call, no retry.
/// Kept as a separate helper so call sites stay uniform — every stage routes
/// through `quality::`.
pub async fn run_stage_no_gate<T, Fut>(attempt: Fut) -> Result<T>
where
    Fut: std::future::Future<Output = Result<T>>,
{
    attempt.await
}

/// Convenience constructor for a `partial_analysis` flag pointer with the
/// same `Arc<AtomicBool>` shape used by `AuditRunContext`. Used by tests to
/// build a flag without standing up a full context.
#[cfg(test)]
pub fn new_partial_analysis_flag() -> Arc<AtomicBool> {
    Arc::new(AtomicBool::new(false))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::intelligent::audit_pipeline::context::PipelineEventSink;
    use tokio::sync::mpsc;

    /// Build a PipelineEventSink wired to an mpsc channel so tests can
    /// assert on the events that fire.
    fn test_sink() -> (PipelineEventSink, mpsc::UnboundedReceiver<IntelligentTaskEvent>) {
        // The production PipelineEventSink::new takes a broadcast::Sender,
        // but for unit tests we only need the emit-capture surface. The
        // event-emission path uses tx.send which works on both sender types
        // by API. We use the broadcast sender path here.
        let (broadcast_tx, _broadcast_rx) =
            tokio::sync::broadcast::channel::<IntelligentTaskEvent>(64);
        let (mpsc_tx, mpsc_rx) = mpsc::unbounded_channel();
        // Replicate PipelineEventSink::new shape: forwards each event to both
        // the broadcast channel (for live consumers) and an internal collect
        // queue. Since we don't have direct access to the internal collector,
        // we instead build a sink that just clones into the broadcast
        // channel; tests then drain via a tap.
        //
        // For coverage purposes, the assertions below check that the helper
        // PROPAGATES outputs and triggers partial_analysis correctly — event
        // capture is exercised in integration tests where the full
        // PipelineEventSink is in scope.
        let _ = mpsc_tx; // silence unused warning while we keep this stub shape
        let sink = PipelineEventSink::new(broadcast_tx).0;
        (sink, mpsc_rx)
    }

    /// Predicate that always passes — proves a single-attempt success path.
    #[tokio::test]
    async fn run_stage_with_retry_returns_first_output_when_predicate_passes() {
        let gate = GatePolicy::new("always pass", 2);
        let partial = new_partial_analysis_flag();
        let (sink, _rx) = test_sink();

        let calls = std::sync::atomic::AtomicU32::new(0);
        let result = run_stage_with_retry(
            &gate,
            AuditStage::Recon,
            &partial,
            &sink,
            |amp| {
                calls.fetch_add(1, Ordering::Relaxed);
                assert!(amp.is_none(), "first attempt must not be amplified");
                async { Ok::<u32, anyhow::Error>(42) }
            },
            |_| Ok(()),
        )
        .await
        .expect("must succeed");

        assert_eq!(result, 42);
        assert_eq!(calls.load(Ordering::Relaxed), 1);
        assert!(!partial.load(Ordering::Relaxed), "no soft-degrade on success");
    }

    /// Predicate fails twice then passes — proves retry happens up to budget
    /// and amplification reaches retry attempts.
    #[tokio::test]
    async fn run_stage_with_retry_retries_until_predicate_passes() {
        let gate = GatePolicy::new("output >= 2", 3);
        let partial = new_partial_analysis_flag();
        let (sink, _rx) = test_sink();

        let calls = std::sync::atomic::AtomicU32::new(0);
        let result = run_stage_with_retry(
            &gate,
            AuditStage::Hunt,
            &partial,
            &sink,
            |amp| {
                let n = calls.fetch_add(1, Ordering::Relaxed) + 1;
                if n > 1 {
                    let amp = amp.expect("retries must carry amplification");
                    assert!(
                        amp.contains("output >= 2"),
                        "amplification must echo the gate label"
                    );
                    assert!(
                        amp.contains("Previous attempt"),
                        "amplification must mention prior attempt"
                    );
                }
                async move { Ok::<u32, anyhow::Error>(n) }
            },
            |out: &u32| {
                if *out >= 2 {
                    Ok(())
                } else {
                    Err(GateFailure::new(
                        "below threshold",
                        format!("out={out}"),
                    ))
                }
            },
        )
        .await
        .expect("must succeed by retry 2");

        assert_eq!(result, 2);
        assert_eq!(calls.load(Ordering::Relaxed), 2);
        assert!(
            !partial.load(Ordering::Relaxed),
            "soft-degrade must not fire when retry succeeds"
        );
    }

    /// All retries exhausted — proves soft-degrade returns Ok with last output
    /// and sets partial_analysis.
    #[tokio::test]
    async fn run_stage_with_retry_soft_degrades_on_exhaustion() {
        let gate = GatePolicy::new("always fail", 2);
        let partial = new_partial_analysis_flag();
        let (sink, _rx) = test_sink();

        let calls = std::sync::atomic::AtomicU32::new(0);
        let result = run_stage_with_retry(
            &gate,
            AuditStage::Validate,
            &partial,
            &sink,
            |_| {
                calls.fetch_add(1, Ordering::Relaxed);
                async { Ok::<u32, anyhow::Error>(0) }
            },
            |_| Err(GateFailure::new("never satisfies", "out=0")),
        )
        .await
        .expect("soft-degrade returns Ok with insufficient output");

        assert_eq!(result, 0);
        assert_eq!(
            calls.load(Ordering::Relaxed),
            3,
            "1 initial + 2 retries = 3 total attempts"
        );
        assert!(
            partial.load(Ordering::Relaxed),
            "exhaustion must set partial_analysis"
        );
    }

    /// max_retries == 0 disables retry entirely — proves the "no gate" shape
    /// behaves like a single-attempt passthrough.
    #[tokio::test]
    async fn run_stage_with_retry_single_attempt_when_max_retries_is_zero() {
        let gate = GatePolicy::new("(no gate)", 0);
        let partial = new_partial_analysis_flag();
        let (sink, _rx) = test_sink();

        let calls = std::sync::atomic::AtomicU32::new(0);
        let result = run_stage_with_retry(
            &gate,
            AuditStage::Gapfill,
            &partial,
            &sink,
            |_| {
                calls.fetch_add(1, Ordering::Relaxed);
                async { Ok::<u32, anyhow::Error>(7) }
            },
            |_| Err(GateFailure::new("would fail", "out=7")),
        )
        .await
        .expect("soft-degrade after the single attempt");

        assert_eq!(result, 7);
        assert_eq!(calls.load(Ordering::Relaxed), 1);
        assert!(
            partial.load(Ordering::Relaxed),
            "max_retries=0 still flags partial_analysis when predicate fails"
        );
    }

    /// Transport-layer errors must propagate immediately — proves the helper
    /// distinguishes quality failure from connectivity failure.
    #[tokio::test]
    async fn run_stage_with_retry_propagates_transport_errors() {
        let gate = GatePolicy::new("always pass", 5);
        let partial = new_partial_analysis_flag();
        let (sink, _rx) = test_sink();

        let result: Result<u32> = run_stage_with_retry(
            &gate,
            AuditStage::Recon,
            &partial,
            &sink,
            |_| async { Err::<u32, _>(anyhow::anyhow!("LLM transport failed")) },
            |_| Ok(()),
        )
        .await;

        let err = result.expect_err("transport error must propagate");
        assert!(err.to_string().contains("LLM transport failed"));
        assert!(
            !partial.load(Ordering::Relaxed),
            "transport failure must not flag partial_analysis"
        );
    }

    /// Default policy table snapshot — protects against accidental policy
    /// regressions during refactors.
    #[test]
    fn default_stage_gates_policy_matches_spec() {
        let p = StageGatesPolicy::default();
        assert_eq!(p.recon.max_retries, 2);
        assert_eq!(p.hunt.max_retries, 3);
        assert_eq!(p.validate.max_retries, 2);
        assert_eq!(p.gapfill.max_retries, 0);
        assert_eq!(p.dedupe.max_retries, 1);
        assert_eq!(p.trace.max_retries, 1);
        assert_eq!(p.feedback.max_retries, 0);
        assert_eq!(p.report.max_retries, 2);
        assert!(p.recon.label.contains("initial_tasks"));
        assert!(p.hunt.label.contains("findings"));
    }
}
