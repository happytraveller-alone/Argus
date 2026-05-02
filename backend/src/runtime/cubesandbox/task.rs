use std::{
    collections::HashMap,
    sync::Arc,
    time::{Duration, Instant},
};

use anyhow::Result;
use serde_json::Value;
use tokio::{sync::Mutex, task::JoinHandle};
use uuid::Uuid;

use crate::{
    db::cubesandbox_task_state,
    runtime::cubesandbox::{
        client::{CubeSandboxClient, CubeSandboxClientConfig},
        config::CubeSandboxConfig,
        helper::{
            run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand,
            CubeSandboxHelperOutput,
        },
        types::{
            now_rfc3339, CubeSandboxCleanupStatus, CubeSandboxTaskRecord, CubeSandboxTaskStatus,
        },
    },
    state::AppState,
};

#[derive(Default)]
pub struct CubeSandboxTaskManager {
    live_tasks: Mutex<HashMap<String, JoinHandle<()>>>,
}

impl CubeSandboxTaskManager {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn submit(
        self: &Arc<Self>,
        state: AppState,
        code: String,
        timeout_seconds: Option<u64>,
        metadata: Option<Value>,
    ) -> Result<CubeSandboxTaskRecord> {
        let task_id = Uuid::new_v4().to_string();
        let record = CubeSandboxTaskRecord::new_queued(
            task_id.clone(),
            code.clone(),
            timeout_seconds,
            metadata.clone(),
        );
        cubesandbox_task_state::save_record(&state, record.clone()).await?;

        let manager = Arc::clone(self);
        let task_id_for_handle = task_id.clone();
        let handle = tokio::spawn(async move {
            manager
                .run_task(state, task_id_for_handle, code, timeout_seconds, metadata)
                .await;
        });
        self.live_tasks.lock().await.insert(task_id, handle);
        Ok(record)
    }

    pub async fn interrupt(
        &self,
        state: &AppState,
        task_id: &str,
    ) -> Result<Option<CubeSandboxTaskRecord>> {
        if let Some(handle) = self.live_tasks.lock().await.remove(task_id) {
            handle.abort();
        }
        cubesandbox_task_state::update_record(state, task_id, |record| {
            record.interrupt_requested = true;
            if !record.status.is_terminal() {
                record.mark_terminal(CubeSandboxTaskStatus::Interrupted);
                record.error_message = Some("interrupted".to_string());
            }
        })
        .await
    }

    pub async fn reconcile_orphans(&self, state: &AppState) -> Result<()> {
        let live = self.live_tasks.lock().await;
        let live_ids: Vec<String> = live.keys().cloned().collect();
        drop(live);

        let snapshot = cubesandbox_task_state::load_snapshot(state).await?;
        for record in snapshot.tasks.into_values() {
            if !record.status.is_terminal() && !live_ids.contains(&record.task_id) {
                let task_id = record.task_id.clone();
                cubesandbox_task_state::update_record(state, &task_id, |record| {
                    record.mark_terminal(CubeSandboxTaskStatus::Interrupted);
                    record.error_category = Some("interrupted".to_string());
                    record.error_message = Some("backend_restarted".to_string());
                })
                .await?;
            }
        }
        Ok(())
    }

    async fn run_task(
        self: Arc<Self>,
        state: AppState,
        task_id: String,
        code: String,
        timeout_seconds: Option<u64>,
        metadata: Option<Value>,
    ) {
        let result = self
            .run_task_inner(&state, &task_id, &code, timeout_seconds, metadata)
            .await;
        if let Err(error) = result {
            let _ = cubesandbox_task_state::update_record(&state, &task_id, |record| {
                if !record.status.is_terminal() {
                    record.mark_terminal(CubeSandboxTaskStatus::Failed);
                }
                record
                    .error_category
                    .get_or_insert_with(|| "internal".to_string());
                record.error_message = Some(error.to_string());
            })
            .await;
        }
        self.live_tasks.lock().await.remove(&task_id);
    }

    async fn run_task_inner(
        &self,
        state: &AppState,
        task_id: &str,
        code: &str,
        timeout_seconds: Option<u64>,
        metadata: Option<Value>,
    ) -> Result<()> {
        let started = Instant::now();
        cubesandbox_task_state::update_record(state, task_id, |record| {
            record.status = CubeSandboxTaskStatus::Starting;
            record.started_at = Some(now_rfc3339());
            record.touch();
        })
        .await?;

        let config = CubeSandboxConfig::load_runtime(state).await?;
        config.validate_for_execution()?;
        let client = CubeSandboxClient::new(CubeSandboxClientConfig {
            api_base_url: config.api_base_url.clone(),
            data_plane_base_url: config.data_plane_base_url.clone(),
            template_id: config.template_id.clone(),
            execution_timeout_seconds: timeout_seconds.unwrap_or(config.execution_timeout_seconds),
            cleanup_timeout_seconds: config.sandbox_cleanup_timeout_seconds,
            stdout_limit_bytes: config.stdout_limit_bytes,
            stderr_limit_bytes: config.stderr_limit_bytes,
        })?;
        let use_local_lifecycle = should_run_local_lifecycle(&config)?;
        if use_local_lifecycle && config.auto_install {
            let install_output =
                run_helper_command(&config, CubeSandboxHelperCommand::Install).await?;
            self.persist_helper_output(state, task_id, &install_output)
                .await?;
            ensure_helper_success(CubeSandboxHelperCommand::Install, &install_output)?;
        }
        if use_local_lifecycle {
            let status_output =
                run_helper_command(&config, CubeSandboxHelperCommand::Status).await?;
            self.persist_helper_output(state, task_id, &status_output)
                .await?;
            if !status_output.success && config.auto_start {
                let start_output =
                    run_helper_command(&config, CubeSandboxHelperCommand::RunVmBackground).await?;
                self.persist_helper_output(state, task_id, &start_output)
                    .await?;
                ensure_helper_success(CubeSandboxHelperCommand::RunVmBackground, &start_output)?;
            } else {
                ensure_helper_success(CubeSandboxHelperCommand::Status, &status_output)?;
            }
        }
        client.health().await?;

        let sandbox = client.create_sandbox().await?;
        client.connect_sandbox(&sandbox.sandbox_id).await?;
        cubesandbox_task_state::update_record(state, task_id, |record| {
            record.status = CubeSandboxTaskStatus::Running;
            record.sandbox_id = Some(sandbox.sandbox_id.clone());
            record.metadata = metadata.clone();
            record.touch();
        })
        .await?;

        let process_result = tokio::time::timeout(
            Duration::from_secs(
                timeout_seconds
                    .unwrap_or(config.execution_timeout_seconds)
                    .max(1),
            ),
            client.run_python(&sandbox, code),
        )
        .await;

        let cleanup_result = client.delete_sandbox(&sandbox.sandbox_id).await;
        let duration_ms = started.elapsed().as_millis() as u64;

        cubesandbox_task_state::update_record(state, task_id, |record| {
            record.duration_ms = Some(duration_ms);
            match process_result {
                Ok(Ok(output)) => {
                    record.stdout = output.stdout;
                    record.stderr = output.stderr;
                    record.stdout_truncated = output.stdout_truncated;
                    record.stderr_truncated = output.stderr_truncated;
                    record.exit_code = output.exit_code;
                    if output.exit_code.unwrap_or(0) == 0 {
                        record.mark_terminal(CubeSandboxTaskStatus::Completed);
                    } else {
                        record.mark_terminal(CubeSandboxTaskStatus::Failed);
                        record.error_category = Some("process_exit".to_string());
                    }
                }
                Ok(Err(error)) => {
                    record.mark_terminal(CubeSandboxTaskStatus::Failed);
                    record.error_category = Some("execution".to_string());
                    record.error_message = Some(error.to_string());
                }
                Err(_) => {
                    record.mark_terminal(CubeSandboxTaskStatus::Failed);
                    record.error_category = Some("timeout".to_string());
                    record.error_message = Some("execution timed out".to_string());
                }
            }

            match cleanup_result {
                Ok(()) => record.cleanup_status = CubeSandboxCleanupStatus::Completed,
                Err(error) => {
                    record.cleanup_status = CubeSandboxCleanupStatus::Failed;
                    record.cleanup_error = Some(error.to_string());
                    if record.status == CubeSandboxTaskStatus::Completed {
                        record.status = CubeSandboxTaskStatus::CleanupFailed;
                    }
                }
            }
        })
        .await?;
        Ok(())
    }

    async fn persist_helper_output(
        &self,
        state: &AppState,
        task_id: &str,
        output: &CubeSandboxHelperOutput,
    ) -> Result<()> {
        cubesandbox_task_state::update_record(state, task_id, |record| {
            record.helper_log_tail = join_log_tail(&output.stdout_tail, &output.stderr_tail);
            record.touch();
        })
        .await?;
        Ok(())
    }
}

fn ensure_helper_success(
    command: CubeSandboxHelperCommand,
    output: &CubeSandboxHelperOutput,
) -> Result<()> {
    if output.success {
        return Ok(());
    }
    anyhow::bail!(
        "CubeSandbox helper command failed: {:?} exit={:?}",
        command,
        output.exit_code
    )
}

fn join_log_tail(stdout: &str, stderr: &str) -> String {
    match (stdout.is_empty(), stderr.is_empty()) {
        (true, true) => String::new(),
        (false, true) => stdout.to_string(),
        (true, false) => stderr.to_string(),
        (false, false) => format!("{stdout}\n{stderr}"),
    }
}
