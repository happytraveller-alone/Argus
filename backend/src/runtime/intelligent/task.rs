use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::Instant,
};

use anyhow::Result;
use serde_json::json;
use tokio::{
    sync::{broadcast, Mutex},
    task::JoinHandle,
};
use uuid::Uuid;

use crate::{
    db::{intelligent_task_state, system_config},
    runtime::intelligent::{
        audit_pipeline,
        audit_pipeline::{types::AuditConfigOverride, AuditPipelineConfig},
        config::{resolve_intelligent_llm_config, StageEngineSelection},
        llm::{HttpIntelligentLlmInvoker, IntelligentLlmInvoker},
        types::{IntelligentTaskEvent, IntelligentTaskFinding, IntelligentTaskRecord},
    },
    state::AppState,
};

/// Flush findings incrementally to the persistent task record.
///
/// Must be called BEFORE `stage_completed` events are emitted so the frontend
/// sees the findings when it reloads the record. This is `.await`-ed
/// synchronously — do NOT `tokio::spawn` it.
pub async fn flush_findings_to_record(
    state: &AppState,
    task_id: &str,
    findings: &[IntelligentTaskFinding],
) -> Result<()> {
    intelligent_task_state::update_record(state, task_id, |record| {
        record.findings = findings.to_vec();
    })
    .await?;
    Ok(())
}

/// Incrementally persist the accumulated pipeline `event_log` mid-run so a
/// reconnect/restart can replay history (plan §1A.3). `prefix_len` is the
/// number of lifecycle events the record already held before the pipeline
/// started emitting (today exactly the single `run_started`). The record's
/// event_log is truncated back to that prefix then re-extended with the
/// in-order `snapshot` of pipeline events collected so far. This is
/// **idempotent**: calling it again with a longer snapshot (or the terminal
/// path doing the same truncate+extend) never duplicates events, so there is
/// no double-write at terminal. Event ORDER is preserved identically to the
/// terminal layout `[run_started, ...pipeline events...]`.
///
/// `.await`-ed synchronously — do NOT `tokio::spawn` it.
pub async fn flush_event_log_to_record(
    state: &AppState,
    task_id: &str,
    prefix_len: usize,
    snapshot: &[IntelligentTaskEvent],
) -> Result<()> {
    intelligent_task_state::update_record(state, task_id, |record| {
        record.event_log.truncate(prefix_len);
        record.event_log.extend_from_slice(snapshot);
    })
    .await?;
    Ok(())
}

const BROADCAST_CAPACITY: usize = 256;

/// Number of lifecycle events the task record holds in `event_log` before the
/// audit pipeline begins emitting (today exactly `run_started`). Incremental
/// and terminal event-log flushes truncate back to this prefix before
/// re-extending with the pipeline event set, so persistence is idempotent and
/// never double-writes (plan §1A.3). The broadcast-only `step_*` events are NOT
/// persisted, so they do not count toward this prefix. Shared with
/// `audit_pipeline::mod` so its stage-boundary flushes use the same prefix.
pub(crate) const PIPELINE_EVENT_PREFIX_LEN: usize = 1;

type IntelligentTaskHandle = (JoinHandle<()>, broadcast::Sender<IntelligentTaskEvent>);

pub struct IntelligentTaskManager {
    live_tasks: Mutex<HashMap<String, IntelligentTaskHandle>>,
    invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
}

impl Default for IntelligentTaskManager {
    fn default() -> Self {
        Self::new()
    }
}

impl IntelligentTaskManager {
    pub fn new() -> Self {
        Self {
            live_tasks: Mutex::new(HashMap::new()),
            invoker: Arc::new(HttpIntelligentLlmInvoker::default()),
        }
    }

    pub fn with_invoker(invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>) -> Self {
        Self {
            live_tasks: Mutex::new(HashMap::new()),
            invoker,
        }
    }

    pub async fn submit(
        self: &Arc<Self>,
        state: AppState,
        project_id: String,
        audit_config_override: Option<AuditConfigOverride>,
    ) -> Result<IntelligentTaskRecord> {
        // Basic UUID-ish validation
        if project_id.trim().is_empty() {
            anyhow::bail!("project_id must not be empty");
        }

        let task_id = Uuid::new_v4().to_string();
        let project = crate::db::projects::get_project(&state, &project_id)
            .await
            .map_err(|error| anyhow::anyhow!(error.to_string()))?
            .ok_or_else(|| anyhow::anyhow!("project not found: {project_id}"))?;
        let project_name = project.name.clone();

        // Resolve LLM config early — on failure save a failed record and return Ok
        let system_cfg = system_config::load_current(&state).await;
        // Phase 0.5 seam: resolve the per-stage engine selection from the same
        // stored config. Absent/unknown `intelligentEngine` config → all-Rust,
        // so the pipeline behaves identically to baseline (AC2).
        let engine_selection = match &system_cfg {
            Ok(Some(cfg)) => StageEngineSelection::from_stored(cfg),
            _ => StageEngineSelection::all_rust(),
        };
        let (config_result, config_err_msg) = match &system_cfg {
            Ok(Some(cfg)) => match resolve_intelligent_llm_config(cfg, &state.config) {
                Ok(c) => (Some(c), None),
                Err(e) => (None, Some(e.message.clone())),
            },
            Ok(None) => (None, Some("no system configuration saved".to_string())),
            Err(e) => (None, Some(e.to_string())),
        };

        match config_result {
            None => {
                // LLM config not available — create a failed record immediately
                let err_msg = config_err_msg
                    .unwrap_or_else(|| "no enabled LLM configuration found".to_string());
                let mut record = IntelligentTaskRecord::new_pending(
                    task_id,
                    project_id,
                    String::new(),
                    String::new(),
                );
                record.project_name = Some(project_name.clone());
                record.mark_failed("llm_config", err_msg);
                intelligent_task_state::save_record(&state, record.clone()).await?;
                Ok(record)
            }
            Some(config) => {
                let record = IntelligentTaskRecord::new_pending(
                    task_id.clone(),
                    project_id.clone(),
                    config.model.clone(),
                    config.fingerprint.clone(),
                );
                let mut record = record;
                record.project_name = Some(project_name.clone());
                intelligent_task_state::save_record(&state, record.clone()).await?;

                let (tx, _rx) = broadcast::channel(BROADCAST_CAPACITY);
                let manager = Arc::clone(self);
                let task_id_for_handle = task_id.clone();
                let tx_for_task = tx.clone();
                let handle = tokio::spawn(async move {
                    manager
                        .run_task(
                            state,
                            task_id_for_handle,
                            project_id,
                            config,
                            tx_for_task,
                            audit_config_override,
                            engine_selection,
                        )
                        .await;
                });
                self.live_tasks.lock().await.insert(task_id, (handle, tx));
                Ok(record)
            }
        }
    }

    pub async fn cancel(
        &self,
        state: &AppState,
        task_id: &str,
    ) -> Result<Option<IntelligentTaskRecord>> {
        // Abort any live handle
        if let Some((handle, _tx)) = self.live_tasks.lock().await.remove(task_id) {
            handle.abort();
        }

        intelligent_task_state::update_record(state, task_id, |record| {
            if record.status.is_cancellable() {
                record.mark_cancelled();
                record.append_event_with_next_seq(IntelligentTaskEvent::new("cancelled"));
            }
        })
        .await
    }

    /// Subscribe to live events for a running task.
    /// Returns `None` if the task is not currently live (already completed/cancelled).
    pub async fn subscribe(
        &self,
        task_id: &str,
    ) -> Option<broadcast::Receiver<IntelligentTaskEvent>> {
        self.live_tasks
            .lock()
            .await
            .get(task_id)
            .map(|(_, tx)| tx.subscribe())
    }

    pub async fn reconcile_orphans(&self, state: &AppState) -> Result<()> {
        // TODO(phase-1.5/3): once sidecar sessions exist, reconcile_orphans
        // should resume each orphaned in-progress task from its last completed
        // stage (via the persisted `session_checkpoint`) and signal the sidecar
        // to abort any orphaned in-flight `/run-stage` run, instead of the
        // blanket cancel-on-restart below. The incremental event_log now lets a
        // reconnect replay history (plan §1A.3); restart-resume orchestration is
        // intentionally NOT built yet (no consumer). Current behavior unchanged.
        let live = self.live_tasks.lock().await;
        let live_ids: Vec<String> = live.keys().cloned().collect();
        drop(live);

        let snapshot = intelligent_task_state::load_snapshot(state).await?;
        for record in snapshot.tasks.into_values() {
            if !record.status.is_terminal() && !live_ids.contains(&record.task_id) {
                let task_id = record.task_id.clone();
                let _ = intelligent_task_state::update_record(state, &task_id, |r| {
                    r.mark_cancelled();
                    r.append_event_with_next_seq(
                        IntelligentTaskEvent::new("cancelled").with_message("backend_restarted"),
                    );
                })
                .await;
            }
        }
        Ok(())
    }

    async fn run_task(
        self: Arc<Self>,
        state: AppState,
        task_id: String,
        project_id: String,
        config: crate::runtime::intelligent::config::IntelligentLlmConfig,
        tx: broadcast::Sender<IntelligentTaskEvent>,
        audit_config_override: Option<AuditConfigOverride>,
        engine_selection: StageEngineSelection,
    ) {
        let started = Instant::now();

        // Single per-task `seq` authority. Both the lifecycle emits below and
        // the pipeline's `PipelineEventSink` stamp `seq` from THIS counter, so
        // `seq` is globally monotonic within the task and the broadcast copy
        // matches the persisted copy of every event (plan §1A.1).
        let seq_counter = Arc::new(AtomicU64::new(1));

        // Helper: stamp the shared monotonic `seq`, broadcast, and return the
        // stamped event so the persisted `append_event` copy carries the same
        // `seq` as the broadcast copy.
        macro_rules! emit {
            ($evt:expr) => {{
                let mut evt: IntelligentTaskEvent = $evt;
                evt.seq = seq_counter.fetch_add(1, Ordering::SeqCst);
                let _ = tx.send(evt.clone());
                evt
            }};
        }

        // Transition to running
        let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
            r.mark_running();
            r.append_event(emit!(IntelligentTaskEvent::new("run_started")));
        })
        .await;

        // --- config_resolve step --- (broadcast-only, not persisted; still
        // seq-stamped so the live stream stays monotonic).
        let _ = emit!(
            IntelligentTaskEvent::new("step_started")
                .with_data(json!({ "step": "config_resolve" }))
        );
        let _ = emit!(
            IntelligentTaskEvent::new("step_completed")
                .with_data(json!({ "step": "config_resolve" }))
        );

        // --- 8-agent audit pipeline step ---
        let _ = emit!(
            IntelligentTaskEvent::new("step_started")
                .with_data(json!({ "step": "audit_pipeline" }))
        );

        let invoker = Arc::clone(&self.invoker);
        let base_cfg = AuditPipelineConfig::default();
        let audit_cfg = match audit_config_override {
            Some(o) => o.into_config(&base_cfg),
            None => base_cfg,
        };
        let pipeline_result = audit_pipeline::run_pipeline_with_config(
            &state,
            &task_id,
            &project_id,
            &config,
            invoker,
            &tx,
            &audit_cfg,
            engine_selection,
            Arc::clone(&seq_counter),
        )
        .await;

        let duration_ms = started.elapsed().as_millis() as u64;

        match pipeline_result {
            Ok(result) => {
                let _ = emit!(
                    IntelligentTaskEvent::new("step_completed")
                        .with_data(json!({ "step": "audit_pipeline" }))
                );
                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.duration_ms = Some(duration_ms);
                    r.input_summary = result.input_summary.clone();
                    r.report_summary = result.report_summary.clone();
                    r.findings = result.findings.clone();
                    // Idempotent terminal reconcile of the pipeline event region:
                    // incremental flushes (mod.rs stage boundaries) already wrote
                    // these events with their stamped `seq`. Truncate to the
                    // lifecycle prefix (run_started) then re-extend with the
                    // authoritative final set so we never double-write. ORDER is
                    // identical to the legacy append path.
                    r.event_log.truncate(PIPELINE_EVENT_PREFIX_LEN);
                    r.event_log.extend(result.events.clone());
                    if let Err(validation_err) = r.mark_completed() {
                        r.mark_failed("completion_validation", validation_err);
                    }
                })
                .await;
            }
            Err(error) => {
                let error_message = error.to_string();
                let failure_stage = if error_message.starts_with("[llm_request]") {
                    "llm_request"
                } else if error_message.contains("has no archive") {
                    "input_read"
                } else {
                    "audit_pipeline"
                };
                let fail_evt = emit!(IntelligentTaskEvent::new("audit_pipeline_failed")
                    .with_message(error_message.clone())
                    .with_data(json!({ "stage": failure_stage })));
                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.duration_ms = Some(duration_ms);
                    r.append_event(fail_evt.clone());
                    r.mark_failed(failure_stage, error_message.clone());
                })
                .await;
            }
        }

        self.live_tasks.lock().await.remove(&task_id);
        // tx is dropped here → all broadcast::Receivers will see RecvError::Closed
    }
}
