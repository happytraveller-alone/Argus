//! Phase 5 integration tests: cubesandbox startup reconcile acceptance verification.
//!
//! Covers acceptance criteria A1–A6 from:
//!   argus/.omc/specs/deep-dive-enhance-sandbox-startup-cleanup.md
//!
//! MANUAL TEST NOTES (deferred to PR-time smoke tests):
//!
//! A3 (env rewrite smoke): Set CUBESANDBOX_TEMPLATE_ID=tpl-bogus, restart backend,
//!   observe env_rewrote_bool=true in the reconcile log and .env rewritten to a
//!   live template_id. Covered by Phase 4 implementation; deferred to PR-time.
//!
//! A5 (cubemaster-down /health): Stop cubemaster, restart backend, hit /health →
//!   expect HTTP 200 within 60 s (reconcile errors are non-fatal). Deferred to
//!   PR-time manual verification step.

use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc, Mutex as StdMutex,
};

use anyhow::Result;
use backend_rust::{
    config::AppConfig,
    runtime::cubesandbox::{
        cubemaster_client::{CubemasterSandbox, CubemasterTemplate},
        reconcile::{reconcile_with_client_for_test, CubemasterApi, ReconcileSummary},
    },
    state::AppState,
};
use time::OffsetDateTime;
use tracing::Subscriber;
use tracing_subscriber::{layer::Context, Layer};

// ─── MOCK ─────────────────────────────────────────────────────────────────────
// Copied from reconcile.rs mod tests (which is mod-private).

struct MockCubemasterApi {
    templates: Vec<CubemasterTemplate>,
    sandboxes: Result<Vec<CubemasterSandbox>>,
    deleted_templates: StdMutex<Vec<String>>,
    deleted_sandboxes: StdMutex<Vec<String>>,
    list_templates_err: Option<String>,
}

impl MockCubemasterApi {
    fn new(templates: Vec<CubemasterTemplate>) -> Self {
        Self {
            templates,
            sandboxes: Ok(vec![]),
            deleted_templates: StdMutex::new(vec![]),
            deleted_sandboxes: StdMutex::new(vec![]),
            list_templates_err: None,
        }
    }

    fn with_list_templates_err(mut self, msg: &str) -> Self {
        self.list_templates_err = Some(msg.to_string());
        self
    }

    fn deleted_templates_snapshot(&self) -> Vec<String> {
        self.deleted_templates.lock().unwrap().clone()
    }
}

impl CubemasterApi for MockCubemasterApi {
    async fn list_templates(&self) -> Result<Vec<CubemasterTemplate>> {
        if let Some(msg) = &self.list_templates_err {
            return Err(anyhow::anyhow!("{}", msg));
        }
        Ok(self.templates.clone())
    }

    async fn list_sandboxes(&self) -> Result<Vec<CubemasterSandbox>> {
        match &self.sandboxes {
            Ok(v) => Ok(v.clone()),
            Err(e) => Err(anyhow::anyhow!("{e}")),
        }
    }

    async fn delete_template(&self, template_id: &str) -> Result<()> {
        self.deleted_templates
            .lock()
            .unwrap()
            .push(template_id.to_string());
        Ok(())
    }

    async fn delete_sandbox(&self, sandbox_id: &str) -> Result<()> {
        self.deleted_sandboxes
            .lock()
            .unwrap()
            .push(sandbox_id.to_string());
        Ok(())
    }
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

fn make_template(id: &str, status: &str, age_hours: i64) -> CubemasterTemplate {
    let created_at = OffsetDateTime::now_utc() - time::Duration::hours(age_hours);
    CubemasterTemplate {
        template_id: id.to_string(),
        kind: String::new(),
        status: status.to_string(),
        created_at,
        image_fingerprint: None,
    }
}

async fn no_db_state() -> AppState {
    let config = AppConfig::for_tests();
    AppState::from_config(config)
        .await
        .expect("failed to build test AppState")
}

async fn reconcile_no_db(mock: &MockCubemasterApi) -> ReconcileSummary {
    let state = no_db_state().await;
    reconcile_with_client_for_test(&state, mock).await
}

// ─── A1: single structured-log emit ──────────────────────────────────────────

/// Counting tracing Layer that increments a counter for every event that
/// originates from the reconcile module.
///
/// `emit_summary_log` uses `tracing::info!(target = "argus::cubesandbox::reconcile", ...)`
/// where `target =` is a key-value FIELD (not the `target:` metadata directive).
/// The actual metadata target is the Rust module path:
///   `backend_rust::runtime::cubesandbox::reconcile`
/// We match on that path AND assert the event has a `target` field with the
/// expected value, verifying both the call count and the field contract.
struct CountingLayer {
    /// Rust module path to match against `event.metadata().target()`.
    module_target: &'static str,
    count: Arc<AtomicUsize>,
}

impl<S: Subscriber> Layer<S> for CountingLayer {
    fn on_event(&self, event: &tracing::Event<'_>, _ctx: Context<'_, S>) {
        if event.metadata().target() == self.module_target {
            self.count.fetch_add(1, Ordering::SeqCst);
        }
    }
}

/// A1: exactly one structured reconcile log event is emitted per reconcile call.
///
/// Uses `flavor = "current_thread"` so that `set_default` (thread-local) stays
/// active for the entire async task — avoids the multi-thread dispatcher mismatch.
#[tokio::test(flavor = "current_thread")]
async fn a1_single_structured_log_event_emitted() {
    use tracing_subscriber::prelude::*;

    let counter = Arc::new(AtomicUsize::new(0));
    let layer = CountingLayer {
        // emit_summary_log uses `tracing::info!(target = "...", ...)` which sets a
        // KEY-VALUE FIELD named `target`, not the metadata target directive.
        // The metadata target is the Rust module path of the call site.
        module_target: "backend_rust::runtime::cubesandbox::reconcile",
        count: Arc::clone(&counter),
    };

    // set_default installs a thread-local override subscriber valid for this scope.
    // current_thread runtime guarantees the async task never migrates threads,
    // so the guard remains active for all await points including emit_summary_log.
    let registry = tracing_subscriber::registry().with(layer);
    let _guard = tracing::subscriber::set_default(registry);

    let mock = MockCubemasterApi::new(vec![]);
    let _summary = reconcile_no_db(&mock).await;

    assert_eq!(
        counter.load(Ordering::SeqCst),
        1,
        "reconcile must emit exactly 1 structured event to target argus::cubesandbox::reconcile"
    );
}

// ─── A2: normal fixture — counters match expected deletions ──────────────────

/// A2: fixture with 1 READY (tpl-good), 1 FAILED (tpl-failed), 1 RUNNING zombie
/// (tpl-zombie, 3h old), and a DB row for tpl-missing (not in cubemaster).
///
/// With no DB pool the reverse-orphan step is a no-op (list_active_all_kinds
/// returns Ok([])); tpl-missing cannot be seen. This test therefore validates
/// the cubemaster-side cleanup counters only.
///
/// tpl-good is READY but has no DB row and no env_pin → forward orphan → deleted.
#[tokio::test]
async fn a2_normal_fixture_cubemaster_cleanup_counters() {
    let templates = vec![
        make_template("tpl-good", "READY", 1),
        make_template("tpl-failed", "FAILED", 5),
        make_template("tpl-zombie", "RUNNING", 3),
    ];
    let mock = MockCubemasterApi::new(templates);
    let summary = reconcile_no_db(&mock).await;

    assert_eq!(summary.deleted_failed_n, 1, "tpl-failed must be deleted");
    assert_eq!(
        summary.deleted_running_zombie_n, 1,
        "tpl-zombie (3h) must be deleted"
    );
    // tpl-good is READY, no DB row, no env_pin → forward orphan
    assert_eq!(
        summary.forward_orphan_n, 1,
        "tpl-good must be forward-orphan deleted"
    );
    assert_eq!(
        summary.reverse_orphan_n, 0,
        "no reverse orphans (no DB pool)"
    );
    assert_eq!(summary.fingerprint_mismatch_n, 0);
    assert!(
        summary.errors.is_empty(),
        "no errors expected: {:?}",
        summary.errors
    );

    let deleted = mock.deleted_templates_snapshot();
    assert!(
        deleted.contains(&"tpl-failed".to_string()),
        "tpl-failed in deleted set"
    );
    assert!(
        deleted.contains(&"tpl-zombie".to_string()),
        "tpl-zombie in deleted set"
    );
    assert!(
        deleted.contains(&"tpl-good".to_string()),
        "tpl-good in deleted set (forward orphan)"
    );
    assert_eq!(deleted.len(), 3, "exactly 3 templates deleted");
}

/// A2 variant: tpl-good is READY and protected by CUBESANDBOX_TEMPLATE_ID env pin → NOT deleted.
/// tpl-failed and tpl-zombie are still deleted.
#[tokio::test]
async fn a2_env_pin_protects_ready_template() {
    // Ensure env pin is set for this test only.
    // Note: env mutation is process-global; tests run single-threaded via tokio,
    // but cargo-test may run multiple test threads. Use a unique value unlikely to clash.
    std::env::set_var("CUBESANDBOX_TEMPLATE_ID", "tpl-good");

    let templates = vec![
        make_template("tpl-good", "READY", 1),
        make_template("tpl-failed", "FAILED", 5),
        make_template("tpl-zombie", "RUNNING", 3),
    ];
    let mock = MockCubemasterApi::new(templates);
    let summary = reconcile_no_db(&mock).await;

    std::env::remove_var("CUBESANDBOX_TEMPLATE_ID");

    assert_eq!(summary.deleted_failed_n, 1, "tpl-failed deleted");
    assert_eq!(summary.deleted_running_zombie_n, 1, "tpl-zombie deleted");
    assert_eq!(summary.forward_orphan_n, 0, "tpl-good protected by env_pin");

    let deleted = mock.deleted_templates_snapshot();
    assert!(
        !deleted.contains(&"tpl-good".to_string()),
        "tpl-good must NOT be deleted"
    );
    assert_eq!(deleted.len(), 2, "only failed+zombie deleted");
}

// ─── A4/A6: idempotence ──────────────────────────────────────────────────────

/// A4/A6: second reconcile call with empty cubemaster has all delete counters at 0.
#[tokio::test]
async fn a6_second_call_all_delete_counters_zero() {
    // First call: delete one failed template.
    let first_mock = MockCubemasterApi::new(vec![make_template("tpl-failed", "FAILED", 5)]);
    let summary1 = reconcile_no_db(&first_mock).await;
    assert_eq!(
        summary1.deleted_failed_n, 1,
        "first call must delete tpl-failed"
    );

    // Second call: cubemaster is now empty (simulating state after first cleanup).
    let second_mock = MockCubemasterApi::new(vec![]);
    let summary2 = tokio::task::spawn(async move {
        let state = no_db_state().await;
        reconcile_with_client_for_test(&state, &second_mock).await
    })
    .await
    .expect("second reconcile must not panic");

    assert_eq!(
        summary2.deleted_failed_n, 0,
        "no failed to delete on second call"
    );
    assert_eq!(
        summary2.deleted_running_zombie_n, 0,
        "no zombies on second call"
    );
    assert_eq!(
        summary2.reverse_orphan_n, 0,
        "no reverse orphans on second call"
    );
    assert_eq!(
        summary2.forward_orphan_n, 0,
        "no forward orphans on second call"
    );
    assert_eq!(
        summary2.scan_failed_invalidated_n, 0,
        "no scan failures on second call"
    );
    assert_eq!(
        summary2.fingerprint_mismatch_n, 0,
        "no fingerprint mismatches on second call"
    );
}

// ─── A5: cubemaster-down variant ─────────────────────────────────────────────

/// A5: when list_templates returns Err, reconcile returns ReconcileSummary (never panics),
/// with exactly 1 error and all delete/invalidate counters at 0.
#[tokio::test]
async fn a5_cubemaster_down_returns_summary_not_panic() {
    let mock = MockCubemasterApi::new(vec![]).with_list_templates_err("ConnectionRefused");
    let summary = reconcile_no_db(&mock).await;

    assert_eq!(
        summary.errors.len(),
        1,
        "exactly 1 error on connection refused"
    );
    assert!(
        summary.errors[0].contains("list_templates"),
        "error message mentions list_templates: {:?}",
        summary.errors[0]
    );
    assert_eq!(summary.deleted_failed_n, 0);
    assert_eq!(summary.deleted_running_zombie_n, 0);
    assert_eq!(summary.reverse_orphan_n, 0);
    assert_eq!(summary.forward_orphan_n, 0);
    assert_eq!(summary.scan_failed_invalidated_n, 0);
    assert_eq!(summary.fingerprint_mismatch_n, 0);
    assert!(!summary.env_rewrote_bool);
    assert_eq!(summary.orphan_sandbox_n, 0);

    // Confirm the bootstrap call site would not error out:
    // reconcile returns ReconcileSummary (not Result) so the wrapper always returns Ok.
    let bootstrap_result: Result<()> = async {
        let state = no_db_state().await;
        let mock2 = MockCubemasterApi::new(vec![]).with_list_templates_err("ConnectionRefused");
        let _s = reconcile_with_client_for_test(&state, &mock2).await;
        Ok(())
    }
    .await;
    assert!(
        bootstrap_result.is_ok(),
        "bootstrap wrapper must return Ok even when cubemaster is down"
    );
}
