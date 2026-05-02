use std::{collections::HashMap, sync::Arc, time::Instant};

use anyhow::Result;
use serde_json::json;
use tokio::{
    sync::{broadcast, Mutex},
    task::JoinHandle,
};
use uuid::Uuid;

use crate::{
    archive,
    db::{intelligent_task_state, system_config},
    runtime::intelligent::{
        config::resolve_intelligent_llm_config,
        llm::{HttpIntelligentLlmInvoker, IntelligentLlmInvoker},
        types::{IntelligentTaskEvent, IntelligentTaskRecord},
    },
    state::AppState,
};

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

        // --- input_read step ---
        let _ = tx.send(
            IntelligentTaskEvent::new("step_started").with_data(json!({ "step": "input_read" })),
        );

        // Build input summary from project archive listing
        let input_summary = self.build_input_summary(&state, &project_id).await;

        let input_summary = match input_summary {
            Ok(summary) => {
                let _ = tx.send(
                    IntelligentTaskEvent::new("step_completed")
                        .with_data(json!({ "step": "input_read" })),
                );
                summary
            }
            Err(err_msg) => {
                let failed_evt =
                    IntelligentTaskEvent::new("input_read_failed").with_message(err_msg.clone());
                let _ = tx.send(failed_evt.clone());
                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.mark_failed("input_read", &err_msg);
                    r.append_event(failed_evt.clone());
                })
                .await;
                self.live_tasks.lock().await.remove(&task_id);
                return;
            }
        };

        // Save input_summary to record before invoking LLM
        let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
            r.input_summary = input_summary.clone();
        })
        .await;

        // Compose prompt
        let prompt = format!(
            "You are a security auditor. Analyze the following project file inventory for potential security concerns.\n\n{input_summary}\n\nProvide a brief security summary."
        );

        // --- llm_invoke step ---
        let _ = tx.send(
            IntelligentTaskEvent::new("step_started").with_data(json!({ "step": "llm_invoke" })),
        );
        let _ = tx.send(IntelligentTaskEvent::new("thinking_start"));

        // Invoke LLM (single attempt, no retry)
        let invoker = Arc::clone(&self.invoker);
        let invocation_result = invoker.invoke(&prompt, &config).await;

        let duration_ms = started.elapsed().as_millis() as u64;

        match invocation_result {
            Ok(invocation) => {
                let report_summary = invocation.content.chars().take(500).collect::<String>();
                let attempt_event = invocation.attempt_event;

                // Emit thinking token (truncated to 500 chars) then thinking_end
                let _ = tx.send(
                    IntelligentTaskEvent::new("thinking_token").with_data(json!({
                        "content": report_summary,
                    })),
                );
                let _ = tx.send(IntelligentTaskEvent::new("thinking_end"));
                let _ = tx.send(
                    IntelligentTaskEvent::new("step_completed")
                        .with_data(json!({ "step": "llm_invoke" })),
                );

                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.duration_ms = Some(duration_ms);
                    r.report_summary = report_summary.clone();
                    r.append_event(attempt_event.clone());
                    // mark_completed validates proof fields
                    if let Err(validation_err) = r.mark_completed() {
                        r.mark_failed("completion_validation", validation_err);
                    }
                })
                .await;

                let _ = tx.send(attempt_event);
            }
            Err(err) => {
                let _ = tx.send(IntelligentTaskEvent::new("thinking_end"));
                let fail_evt = IntelligentTaskEvent::new("llm_attempt").with_data(json!({
                    "success": false,
                    "redacted_error": err.redacted_message,
                }));
                let _ = tx.send(fail_evt.clone());
                let _ = intelligent_task_state::update_record(&state, &task_id, |r| {
                    r.duration_ms = Some(duration_ms);
                    r.append_event(fail_evt.clone());
                    r.mark_failed("llm_request", &err.redacted_message);
                })
                .await;
            }
        }

        self.live_tasks.lock().await.remove(&task_id);
        // tx is dropped here → all broadcast::Receivers will see RecvError::Closed
    }

    async fn build_input_summary(
        &self,
        state: &AppState,
        project_id: &str,
    ) -> Result<String, String> {
        use crate::db::projects;

        let project = projects::get_project(state, project_id)
            .await
            .map_err(|e| format!("failed to load project: {e}"))?;

        let Some(project) = project else {
            return Err(format!("project not found: {project_id}"));
        };

        let Some(archive_meta) = project.archive else {
            return Err(format!("project {project_id} has no archive"));
        };

        let storage_path = std::path::PathBuf::from(&archive_meta.storage_path);
        let entries =
            archive::list_archive_files_from_path(&storage_path, &archive_meta.original_filename)
                .map_err(|e| format!("failed to list archive: {e}"))?;

        const MAX_ENTRIES: usize = 200;
        let lines: Vec<String> = entries
            .iter()
            .take(MAX_ENTRIES)
            .map(|e| format!("{} ({}B)", e.path, e.size))
            .collect();

        let total = entries.len();
        let shown = lines.len();
        let mut summary = format!("Project file inventory ({shown}/{total} files):\n");
        summary.push_str(&lines.join("\n"));
        if total > MAX_ENTRIES {
            summary.push_str(&format!("\n... and {} more files", total - MAX_ENTRIES));
        }
        Ok(summary)
    }
}
