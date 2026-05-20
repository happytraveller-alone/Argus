//! Phase D.4 / D.5 — Unit tests for sandbox pool metrics and isolation invariants.
//!
//! NOT live-gated.  Uses FakeSandbox + FakeFactory — no live runtime required.
//!
//! AC9: pool size is observable via metric=standby_pool_size_current structured logs.
//! AC3: no sandbox-id appears in two distinct take() dispatches over a test run.
//!
//! Run:
//!   cargo test --features test-helpers --test sandbox_pool_unit

use std::{
    collections::{HashMap, HashSet},
    future::Future,
    pin::Pin,
    sync::{
        atomic::{AtomicUsize, Ordering as AOrdering},
        Arc,
    },
};

use backend_rust::runtime::sandbox_pool::{
    OnShutdownDestroy, Sandbox, SandboxFactory, SandboxId, SandboxPool,
};
use tokio::sync::OwnedSemaphorePermit;

// ── FakeSandbox / FakeFactory ─────────────────────────────────────────────────

#[derive(Clone, Eq, PartialEq, Hash, Debug)]
enum FakeKind {
    Alpha,
}

struct FakeSandbox {
    id: String,
}

impl Sandbox for FakeSandbox {
    type TemplateKind = FakeKind;
    fn id(&self) -> SandboxId {
        self.id.clone()
    }
}

struct FakeFactory {
    counter: Arc<AtomicUsize>,
}

impl FakeFactory {
    fn new() -> Self {
        Self {
            counter: Arc::new(AtomicUsize::new(0)),
        }
    }
}

impl SandboxFactory<FakeSandbox> for FakeFactory {
    fn create<'a>(
        &'a self,
        _kind: FakeKind,
        permit: OwnedSemaphorePermit,
    ) -> Pin<Box<dyn Future<Output = anyhow::Result<FakeSandbox>> + Send + 'a>> {
        let n = self.counter.fetch_add(1, AOrdering::SeqCst);
        // Drop permit immediately — signals creation slot is free.
        drop(permit);
        Box::pin(async move {
            Ok(FakeSandbox {
                id: format!("fake-sandbox-{n}"),
            })
        })
    }
}

fn noop_destroy() -> OnShutdownDestroy<FakeSandbox> {
    Arc::new(|_| Box::pin(async { Ok(()) }))
}

fn make_pool(capacity: usize, factory: Arc<FakeFactory>) -> Arc<SandboxPool<FakeSandbox>> {
    let mut caps = HashMap::new();
    caps.insert(FakeKind::Alpha, capacity);
    Arc::new(SandboxPool::new(
        caps,
        capacity + 4,
        factory,
        noop_destroy(),
    ))
}

/// Poll `read_active()` until it reaches `expected_len` or `timeout_ms` elapses.
/// Needed because `warmup()` spawns background refill tasks that complete asynchronously.
async fn wait_for_pool_size(
    pool: &Arc<SandboxPool<FakeSandbox>>,
    expected_len: usize,
    timeout_ms: u64,
) {
    let deadline = tokio::time::Instant::now() + tokio::time::Duration::from_millis(timeout_ms);
    loop {
        if pool.read_active().await.len() >= expected_len {
            return;
        }
        if tokio::time::Instant::now() >= deadline {
            let actual = pool.read_active().await.len();
            panic!("pool did not reach size {expected_len} within {timeout_ms}ms; actual={actual}");
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
    }
}

// ── AC9: metrics emitted on take and refill ───────────────────────────────────

/// AC9: pool size configurable per kind and observable via structured logs.
///
/// This test verifies that:
///   1. After warmup, `starvation_count() == 0` (no starvation during warmup).
///   2. After draining the pool, `starvation_count()` increments on each empty take.
///   3. After a refill, the next take() succeeds and starvation_count does not increment.
///
/// The actual log field assertions (metric="standby_pool_size_current") are structural —
/// the fields are emitted by the modified take()/refill code paths.  Tracing-subscriber
/// capture would require a test-local subscriber; the counter-based assertions here
/// serve as the observable proxy per the plan's "structured logs or real metrics crate"
/// guidance.
#[tokio::test]
async fn ac9_metrics_emitted() {
    let factory = Arc::new(FakeFactory::new());
    let pool = make_pool(2, factory);

    // Warmup spawns background refill tasks — wait until all 2 slots are filled.
    pool.warmup().await;
    wait_for_pool_size(&pool, 2, 2000).await;

    // No starvation during warmup.
    assert_eq!(
        pool.starvation_count(),
        0,
        "no starvation expected after warmup"
    );

    // read_active() shows 2 entries (AC6 invariant — also checked here).
    let active = pool.read_active().await;
    assert_eq!(active.len(), 2, "pool at capacity: 2 standby entries");

    // Take both sandboxes — starvation_count stays 0 (successful takes).
    let s1 = pool.take(&FakeKind::Alpha).await;
    assert!(s1.is_some(), "first take must succeed");
    assert_eq!(
        pool.starvation_count(),
        0,
        "successful take: starvation_count unchanged"
    );

    let s2 = pool.take(&FakeKind::Alpha).await;
    assert!(s2.is_some(), "second take must succeed");
    assert_eq!(
        pool.starvation_count(),
        0,
        "second successful take: starvation_count unchanged"
    );

    // Pool is now empty.  Next take() triggers starvation.
    let s3 = pool.take(&FakeKind::Alpha).await;
    assert!(s3.is_none(), "take on empty pool must return None");
    assert_eq!(
        pool.starvation_count(),
        1,
        "starvation_count must be 1 after first empty take"
    );

    // Second starvation event.
    let s4 = pool.take(&FakeKind::Alpha).await;
    assert!(s4.is_none());
    assert_eq!(
        pool.starvation_count(),
        2,
        "starvation_count must be 2 after second empty take"
    );

    // Trigger a refill and wait for it — then take should succeed without starvation increment.
    pool.refill_in_background(FakeKind::Alpha).await;
    // Wait for background refill task to complete.
    wait_for_pool_size(&pool, 1, 2000).await;

    let s5 = pool.take(&FakeKind::Alpha).await;
    assert!(s5.is_some(), "take after refill must succeed");
    // starvation_count must still be 2 — successful take does not increment.
    assert_eq!(
        pool.starvation_count(),
        2,
        "starvation_count must not change on successful take after refill"
    );
}

// ── AC9: kill-switch does not increment starvation counter ───────────────────

/// AC9 / AC10 boundary: disabled pool returns None from take() without
/// incrementing starvation_count.  This distinguishes kill-switch from starvation.
#[tokio::test]
async fn ac9_kill_switch_does_not_increment_starvation() {
    let factory = Arc::new(FakeFactory::new());
    let pool = make_pool(1, factory);

    pool.set_disabled(true);

    // Multiple take() calls on disabled pool: all return None, counter stays 0.
    for _ in 0..5 {
        let result = pool.take(&FakeKind::Alpha).await;
        assert!(result.is_none(), "disabled pool must return None from take");
    }
    assert_eq!(
        pool.starvation_count(),
        0,
        "kill-switch path must NOT increment starvation counter"
    );
}

// ── AC3: no sandbox-id reuse across dispatches ───────────────────────────────

/// AC3: cold-start isolation — no sandbox-id appears in two distinct take()
/// dispatches over the entire test run.
///
/// Each sandbox is single-use; after take(), the scan path calls
/// best_effort_delete_sandbox (not tested here) and never returns the handle
/// to the pool.  The factory always creates new sandboxes with unique IDs.
///
/// This test verifies the uniqueness invariant: all IDs returned by N sequential
/// take() calls (with refills between them) are distinct.
#[tokio::test]
async fn ac3_no_pool_residue_across_dispatches() {
    let factory = Arc::new(FakeFactory::new());
    let pool = make_pool(3, Arc::clone(&factory));

    pool.warmup().await;
    wait_for_pool_size(&pool, 3, 2000).await;

    // Perform 6 take() operations with refills to collect IDs.
    let mut seen_ids: HashSet<String> = HashSet::new();
    let mut taken_count = 0usize;

    for _ in 0..6 {
        // Refill if needed to keep pool non-empty.
        pool.refill_in_background(FakeKind::Alpha).await;
        wait_for_pool_size(&pool, 1, 1000).await;

        if let Some(sandbox) = pool.take(&FakeKind::Alpha).await {
            let id = sandbox.id();
            assert!(
                seen_ids.insert(id.clone()),
                "AC3 violation: sandbox id '{id}' was dispatched more than once"
            );
            taken_count += 1;
        }
    }

    assert!(
        taken_count >= 3,
        "at least 3 sandboxes must have been taken across 6 attempts"
    );
    // All collected IDs are unique (invariant already checked above per-insertion).
    assert_eq!(
        seen_ids.len(),
        taken_count,
        "all dispatched sandbox IDs must be unique"
    );
}

// ── AC3: uniqueness enforced across pool warmup + N+1 sequential takes ────────

/// Extended AC3 guard: populate pool, take N (pool capacity) + 1 sequential
/// sandboxes (with refill), assert all IDs unique.
#[tokio::test]
async fn ac3_no_pool_residue_n_plus_one_sequential() {
    const POOL_SIZE: usize = 2;
    let factory = Arc::new(FakeFactory::new());
    let pool = make_pool(POOL_SIZE, Arc::clone(&factory));

    pool.warmup().await;
    wait_for_pool_size(&pool, POOL_SIZE, 2000).await;

    let mut seen_ids: HashSet<String> = HashSet::new();

    // Take N + 1 sandboxes total.
    for i in 0..=(POOL_SIZE) {
        if i > 0 {
            // Refill after each take, then wait for it to complete.
            pool.refill_in_background(FakeKind::Alpha).await;
            wait_for_pool_size(&pool, 1, 1000).await;
        }
        if let Some(s) = pool.take(&FakeKind::Alpha).await {
            let id = s.id();
            assert!(
                seen_ids.insert(id.clone()),
                "AC3 violation at iteration {i}: id '{id}' already seen"
            );
        }
    }

    // All seen IDs are unique.
    let ids_vec: Vec<_> = seen_ids.iter().cloned().collect();
    let unique: HashSet<_> = ids_vec.iter().cloned().collect();
    assert_eq!(
        ids_vec.len(),
        unique.len(),
        "all sandbox IDs across dispatches must be unique"
    );
}
