use std::{collections::HashMap, sync::Arc, time::Instant};

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
        config::resolve_intelligent_llm_config,
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

const BROADCAST_CAPACITY: usize = 256;

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
                        .run_task(state, task_id_for_handle, project_id, config, tx_for_task)
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
                record.append_event(IntelligentTaskEvent::new("cancelled"));
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
        let live = self.live_tasks.lock().await;
        let live_ids: Vec<String> = live.keys().cloned().collect();
        drop(live);

        let snapshot = intelligent_task_state::load_snapshot(state).await?;
        for record in snapshot.tasks.into_values() {
            if !record.status.is_terminal() && !live_ids.contains(&record.task_id) {
                let task_id = record.task_id.clone();
                let _ = intelligent_task_state::update_record(state, &task_id, |r| {
                    r.mark_cancelled();
                    r.append_event(
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
    ) {
        let started = Instant::now();

        // Helper: emit event to both persisted log and broadcast channel
        macro_rules! emit {
            ($evt:expr) => {{
                let evt: IntelligentTaskEvent = $evt;
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

        // --- config_resolve step ---
        let _ = tx.send(
            IntelligentTaskEvent::new("step_started")
                .with_data(json!({ "step": "config_resolve" })),
        );
        let _ = tx.send(
            IntelligentTaskEvent::new("step_completed")
                .with_data(json!({ "step": "config_resolve" })),
        );

        // --- 8-agent audit pipeline step ---
        let _ = tx.send(
            IntelligentTaskEvent::new("step_started")
                .with_data(json!({ "step": "audit_pipeline" })),
        );

        let invoker = Arc::clone(&self.invoker);
        let pipeline_result =
            audit_pipeline::run_pipeline(&state, &task_id, &project_id, &config, invoker, &tx)
                .await;

        let duration_ms = started.elapsed().as_millis() as u64;

        match pipeline_result {
            Ok(result) => {
                let _ = tx.send(
                    IntelligentTaskEvent::new("step_completed")
                        .with_data(json!({ "step": "audit_pipeline" })),
                );
                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.duration_ms = Some(duration_ms);
                    r.input_summary = result.input_summary.clone();
                    r.report_summary = result.report_summary.clone();
                    r.findings = result.findings.clone();
                    for event in result.events.clone() {
                        r.append_event(event);
                    }
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
                let fail_evt = IntelligentTaskEvent::new("audit_pipeline_failed")
                    .with_message(error_message.clone())
                    .with_data(json!({ "stage": failure_stage }));
                let _ = tx.send(fail_evt.clone());
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
