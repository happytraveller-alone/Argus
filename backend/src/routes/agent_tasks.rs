use std::{
    collections::BTreeMap,
    env,
    path::{Path, PathBuf},
    time::Duration,
};

use axum::{
    body::Body,
    extract::{Path as AxumPath, Query, State},
    response::Response,
    routing::{get, patch, post},
    Json, Router,
};
use http::{header, HeaderValue, StatusCode};
use serde::Deserialize;
use serde_json::{json, Value};
use time::macros::format_description;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::llm::test_llm_generation;
use crate::{
    archive::extract_archive_path_to_directory,
    config::AppConfig,
    db::{projects, system_config, task_state},
    error::ApiError,
    routes::skills,
    runtime::agentflow::{
        codex_config::build_agentflow_llm_config,
        contracts::{ARGUS_AGENTFLOW_CONTRACT_VERSION, P1_TOPOLOGY_VERSION},
        importer::{import_runner_output, sha256_hex},
        pipeline_path::resolve_agentflow_pipeline_path,
        preflight::{run_preflight, PreflightInput},
        runner::{run_streaming_command, RunnerCommand},
        streaming::{self, StreamingEvent},
    },
    state::{AppState, StoredProject},
};

const DEFAULT_AGENTFLOW_RUNNER_IMAGE: &str = "argus/agentflow-runner:1667fa35";
const DEFAULT_AGENTFLOW_WORK_VOLUME: &str = "Argus_agentflow_runner_work";
const DEFAULT_SCAN_WORKSPACE_ROOT: &str = "/tmp/Argus/scans";
const DEFAULT_SCAN_WORKSPACE_VOLUME: &str = "Argus_scan_workspace";

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", post(create_agent_task).get(list_agent_tasks))
        .route("/{task_id}", get(get_agent_task))
        .route("/{task_id}/start", post(start_agent_task))
        .route("/{task_id}/cancel", post(cancel_agent_task))
        .route("/{task_id}/events", get(stream_agent_events))
        .route("/{task_id}/events/list", get(list_agent_events))
        .route("/{task_id}/stream", get(stream_agent_events))
        .route("/{task_id}/findings", get(list_agent_findings))
        .route(
            "/{task_id}/findings/{finding_id}",
            get(get_agent_finding).patch(update_agent_finding),
        )
        .route(
            "/{task_id}/findings/{finding_id}/status",
            patch(update_agent_finding_status),
        )
        .route(
            "/{task_id}/findings/{finding_id}/report",
            get(download_finding_report),
        )
        .route("/{task_id}/summary", get(get_agent_task_summary))
        .route("/{task_id}/agent-tree", get(get_agent_tree))
        .route("/{task_id}/checkpoints", get(list_checkpoints))
        .route(
            "/{task_id}/checkpoints/{checkpoint_id}",
            get(get_checkpoint_detail),
        )
        .route("/{task_id}/report", get(download_report))
}

#[cfg(test)]
const AGENTFLOW_RUNTIME_UNCONFIGURED_ERROR: &str =
    "AgentFlow runtime is not configured yet; legacy agent runtime has been retired";

const FORBIDDEN_STATIC_INPUT_ERROR: &str =
    "智能审计 P1 禁止使用静态扫描任务或静态 finding 候选输入";

const FORBIDDEN_STATIC_INPUT_KEYS: &[&str] = &[
    "static_task_id",
    "opengrep_task_id",
    "candidate_finding_ids",
    "static_findings",
    "bootstrap_task_id",
    "bootstrap_candidate_count",
    "candidate_findings",
];

const FORBIDDEN_STATIC_INPUT_VALUES: &[&str] =
    &["opengrep", "static", "bandit", "gitleaks", "phpstan", "pmd"];

#[derive(Debug, Deserialize)]
pub struct AgentTaskListQuery {
    project_id: Option<String>,
    status: Option<String>,
    skip: Option<usize>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct AgentEventsQuery {
    after_sequence: Option<i64>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct FindingStatusQuery {
    status: String,
}

#[derive(Debug, Deserialize)]
struct AgentFindingsQuery {
    severity: Option<String>,
    vulnerability_type: Option<String>,
    verified_only: Option<bool>,
    include_false_positive: Option<bool>,
    skip: Option<usize>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct AgentFindingDetailQuery {
    include_false_positive: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct CheckpointListQuery {
    agent_id: Option<String>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct ReportQuery {
    format: Option<String>,
    include_code_snippets: Option<bool>,
    include_remediation: Option<bool>,
    include_metadata: Option<bool>,
    compact_mode: Option<bool>,
}

pub async fn create_agent_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let project_id = required_string(&payload, "project_id")?;
    reject_forbidden_static_input(&payload)?;
    ensure_intelligent_audit_llm_ready(&state).await?;

    let now = now_rfc3339();
    let task_id = Uuid::new_v4().to_string();
    let name = optional_string(&payload, "name");
    let description = optional_string(&payload, "description");
    let verification_level = optional_string(&payload, "verification_level")
        .or(Some("analysis_with_poc_plan".to_string()));
    let target_vulnerabilities = payload
        .get("target_vulnerabilities")
        .and_then(|value| value.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(ToString::to_string))
                .collect::<Vec<_>>()
        })
        .or_else(|| {
            Some(vec![
                "sql_injection".to_string(),
                "xss".to_string(),
                "command_injection".to_string(),
                "path_traversal".to_string(),
                "ssrf".to_string(),
            ])
        });
    let exclude_patterns = payload.get("exclude_patterns").and_then(string_array);
    let target_files = payload.get("target_files").and_then(string_array);
    let use_prompt_skills = payload
        .get("use_prompt_skills")
        .and_then(|value| value.as_bool())
        .unwrap_or(false);
    let prompt_skill_runtime =
        skills::prompt_skill_runtime_snapshot(&state, use_prompt_skills).await?;
    let audit_scope =
        prepare_audit_scope(payload.get("audit_scope").cloned(), prompt_skill_runtime)?;
    let max_iterations = payload
        .get("max_iterations")
        .and_then(|value| value.as_i64())
        .unwrap_or(8);

    let mut record = task_state::AgentTaskRecord {
        id: task_id.clone(),
        project_id: project_id.clone(),
        name,
        description,
        task_type: "agent_audit".to_string(),
        status: "pending".to_string(),
        current_phase: Some("created".to_string()),
        current_step: Some("waiting to start".to_string()),
        total_files: 0,
        indexed_files: 0,
        analyzed_files: 0,
        files_with_findings: 0,
        total_chunks: 0,
        findings_count: 0,
        verified_count: 0,
        false_positive_count: 0,
        total_iterations: max_iterations,
        tool_calls_count: 0,
        tokens_used: 0,
        critical_count: 0,
        high_count: 0,
        medium_count: 0,
        low_count: 0,
        verified_critical_count: 0,
        verified_high_count: 0,
        verified_medium_count: 0,
        verified_low_count: 0,
        quality_score: 0.0,
        security_score: Some(0.0),
        created_at: now.clone(),
        started_at: None,
        completed_at: None,
        progress_percentage: 0.0,
        audit_scope,
        target_vulnerabilities,
        verification_level,
        tool_evidence_protocol: Some("native_v1".to_string()),
        exclude_patterns,
        target_files,
        error_message: None,
        report: Some(format!(
            "# Agent Task Report\n\nTask `{task_id}` is now owned by the rust backend.\n"
        )),
        runtime: Some("agentflow".to_string()),
        run_id: None,
        topology_version: Some("p1-static".to_string()),
        input_digest: None,
        artifact_index: Some(json!([])),
        report_snapshot: None,
        feedback_bundle: None,
        diagnostics: None,
        events: Vec::new(),
        findings: Vec::new(),
        checkpoints: Vec::new(),
        agent_tree: Vec::new(),
    };
    push_agent_event(
        &mut record,
        "task_start",
        Some("created"),
        Some("agent task created in rust backend"),
        None,
    );
    push_checkpoint(&mut record, "auto", Some("created"));
    record.agent_tree = vec![json!({
        "id": format!("root-{task_id}"),
        "agent_id": format!("root-{task_id}"),
        "agent_name": "RustAgentRoot",
        "agent_type": "root",
        "parent_agent_id": Value::Null,
        "depth": 0,
        "task_description": record.description,
        "status": "created",
        "result_summary": "task accepted by rust backend",
        "findings_count": 0,
        "verified_findings_count": 0,
        "iterations": 0,
        "tokens_used": 0,
        "tool_calls": 0,
        "duration_ms": Value::Null,
        "children": Vec::<Value>::new(),
    })];

    let _guard = state.file_store_lock.lock().await;
    let project = projects::get_project_while_locked(&state, &project_id)
        .await
        .map_err(internal_error)?;
    if project.is_none() {
        return Err(ApiError::NotFound(format!(
            "project not found: {project_id}"
        )));
    }
    let mut snapshot = task_state::load_snapshot_unlocked(&state)
        .await
        .map_err(internal_error)?;
    snapshot.agent_tasks.insert(task_id.clone(), record.clone());
    task_state::save_snapshot_unlocked(&state, &snapshot)
        .await
        .map_err(internal_error)?;

    let spawn_state = state.clone();
    let spawn_task_id = task_id.clone();
    tokio::spawn(async move {
        if let Err(error) = start_agent_task_core(spawn_state, spawn_task_id.clone()).await {
            eprintln!("[auto-start] task {spawn_task_id} failed: {error}");
        }
    });

    Ok(Json(agent_task_value(&record)))
}

pub async fn list_agent_tasks(
    State(state): State<AppState>,
    Query(query): Query<AgentTaskListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let mut items = snapshot
        .agent_tasks
        .into_values()
        .filter(|record| match query.project_id.as_deref() {
            Some(project_id) => record.project_id == project_id,
            None => true,
        })
        .filter(|record| match query.status.as_deref() {
            Some(status) => record.status == status,
            None => true,
        })
        .collect::<Vec<_>>();
    items.sort_by(|left, right| right.created_at.cmp(&left.created_at));

    let skip = query.skip.unwrap_or(0);
    let limit = query.limit.unwrap_or(items.len());
    Ok(Json(
        items
            .into_iter()
            .skip(skip)
            .take(limit)
            .map(|record| agent_task_value(&record))
            .collect(),
    ))
}

async fn get_agent_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    Ok(Json(agent_task_value(record)))
}

async fn start_agent_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    start_agent_task_core(state, task_id).await
}

async fn start_agent_task_core(state: AppState, task_id: String) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let (project_id, audit_scope_for_preflight) = {
        let record = snapshot
            .agent_tasks
            .get(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        if record.status != "pending" {
            return Err(ApiError::Conflict(format!(
                "task {} cannot be started: current status is '{}'",
                task_id, record.status
            )));
        }
        reject_optional_audit_scope(record.audit_scope.as_ref())?;
        ensure_intelligent_audit_llm_ready(&state).await?;
        (
            record.project_id.clone(),
            record.audit_scope.clone().unwrap_or_else(|| json!({})),
        )
    };

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let now = now_rfc3339();
    {
        let record = snapshot
            .agent_tasks
            .get_mut(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        record.started_at = Some(now.clone());
        record.completed_at = None;
        record.status = "running".to_string();
        record.current_phase = Some("preflight".to_string());
        record.current_step = Some("AgentFlow preflight".to_string());
        record.progress_percentage = 5.0;
        record.total_iterations = record.total_iterations.max(1);
        push_agent_event(
            record,
            "phase_start",
            Some("preflight"),
            Some("AgentFlow 智能审计预检开始"),
            None,
        );
        push_checkpoint(record, "preflight", Some("running"));
    };
    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;

    let project = projects::get_project(&state, &project_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("project not found: {project_id}")))?;
    let stored_config = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let llm_config = build_agentflow_llm_config(
        state.config.as_ref(),
        stored_config.as_ref().map(|stored| &stored.llm_config_json),
    );
    let runner_command = agentflow_runner_command();
    let output_dir = agentflow_output_dir(&state, &task_id);
    let pipeline_resolution = resolve_agentflow_pipeline_path();
    let pipeline_path = pipeline_resolution.path.clone();
    let preflight = run_preflight(PreflightInput {
        llm_config: &llm_config,
        audit_scope: Some(&audit_scope_for_preflight),
        runner_command: runner_command
            .as_ref()
            .map(|command| command.command.as_str()),
        pipeline_path: Some(&pipeline_path),
        pipeline_candidate_paths: Some(&pipeline_resolution.candidates),
        output_dir: Some(&output_dir),
        max_parallel_nodes: state.config.runner_preflight_max_concurrency,
    })
    .await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    if !preflight.ok {
        let record = snapshot
            .agent_tasks
            .get_mut(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        finalize_agent_task_agentflow_failure(
            record,
            &now_rfc3339(),
            "preflight failed",
            preflight
                .reason_code
                .as_deref()
                .unwrap_or("preflight_failed"),
            "preflight_failed",
            &preflight.message,
            Some(json!({
                "preflight": preflight,
            })),
        );
        let response = agent_task_value(record);
        task_state::save_snapshot(&state, &snapshot)
            .await
            .map_err(internal_error)?;
        return Ok(Json(response));
    }

    let prepared_workspace = if runner_command
        .as_ref()
        .is_some_and(|command| command.source == AgentflowRunnerCommandSource::DefaultDocker)
    {
        match prepare_agentflow_workspace(&project, &task_id).await {
            Ok(workspace) => Some(workspace),
            Err(error) => {
                let record = snapshot.agent_tasks.get_mut(&task_id).ok_or_else(|| {
                    ApiError::NotFound(format!("agent task not found: {task_id}"))
                })?;
                finalize_agent_task_agentflow_failure(
                    record,
                    &now_rfc3339(),
                    "workspace prepare failed",
                    error.reason_code,
                    "preflight_failed",
                    &error.message,
                    Some(json!({
                        "workspace": {
                            "reason_code": error.reason_code,
                            "message": error.message,
                        }
                    })),
                );
                let response = agent_task_value(record);
                task_state::save_snapshot(&state, &snapshot)
                    .await
                    .map_err(internal_error)?;
                return Ok(Json(response));
            }
        }
    } else {
        None
    };
    let runner_project_root = prepared_workspace
        .as_ref()
        .map(|workspace| workspace.container_source_dir.clone())
        .or_else(|| {
            project
                .archive
                .as_ref()
                .map(|archive| archive.storage_path.clone())
        })
        .unwrap_or_else(|| "/workspace/src".to_string());
    let runner_output_dir = prepared_workspace
        .as_ref()
        .map(|workspace| workspace.container_output_dir.clone())
        .unwrap_or_else(|| output_dir.display().to_string());

    let runner_input = {
        let record = snapshot
            .agent_tasks
            .get_mut(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        record.current_phase = Some("running".to_string());
        record.current_step = Some("AgentFlow runner executing".to_string());
        record.progress_percentage = 15.0;
        push_agent_event(
            record,
            "runner_started",
            Some("running"),
            Some("AgentFlow runner 已启动"),
            Some(json!({
                "runtime": "agentflow",
                "pipeline": pipeline_path.display().to_string(),
            })),
        );
        push_checkpoint(record, "runner", Some("running"));
        build_agentflow_runner_input(
            record,
            &project,
            state.config.as_ref(),
            &llm_config,
            &runner_project_root,
            &runner_output_dir,
        )
    };
    {
        let record = snapshot
            .agent_tasks
            .get_mut(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        record.input_digest = Some(format!(
            "sha256:{}",
            sha256_hex(runner_input.to_string().as_bytes())
        ));
    }
    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;

    let Some(runner_command) = runner_command else {
        let mut snapshot = task_state::load_snapshot(&state)
            .await
            .map_err(internal_error)?;
        let record = snapshot
            .agent_tasks
            .get_mut(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
        finalize_agent_task_agentflow_failure(
            record,
            &now_rfc3339(),
            "runner missing",
            "runner_missing",
            "preflight_failed",
            "AgentFlow runner 未配置，无法启动智能审计任务",
            None,
        );
        let response = agent_task_value(record);
        task_state::save_snapshot(&state, &snapshot)
            .await
            .map_err(internal_error)?;
        return Ok(Json(response));
    };
    // Create broadcast channel for streaming events
    let event_tx = {
        let mut channels = state.task_event_channels.lock().await;
        streaming::get_or_create_channel(&mut channels, &task_id)
    };

    // Spawn incremental persistence task
    let persist_tx = {
        let (ptx, prx) = tokio::sync::mpsc::channel::<StreamingEvent>(256);
        let persist_state = state.clone();
        let persist_task_id = task_id.clone();
        let mut persist_rx = prx;
        tokio::spawn(async move {
            let mut buffer: Vec<StreamingEvent> = Vec::new();
            let mut interval = tokio::time::interval(Duration::from_secs(2));
            interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                tokio::select! {
                    event = persist_rx.recv() => {
                        match event {
                            Some(ev) if streaming::should_persist_event(&ev.event_type) => {
                                buffer.push(ev);
                                if buffer.len() >= 10 {
                                    flush_streaming_events(&persist_state, &persist_task_id, &mut buffer).await;
                                }
                            }
                            Some(_) => {}
                            None => {
                                if !buffer.is_empty() {
                                    flush_streaming_events(&persist_state, &persist_task_id, &mut buffer).await;
                                }
                                break;
                            }
                        }
                    }
                    _ = interval.tick() => {
                        if !buffer.is_empty() {
                            flush_streaming_events(&persist_state, &persist_task_id, &mut buffer).await;
                        }
                    }
                }
            }
        });
        ptx
    };

    // Forward broadcast events to persistence channel
    let mut persist_sub = event_tx.subscribe();
    let persist_fwd_tx = persist_tx.clone();
    let persist_fwd = tokio::spawn(async move {
        while let Ok(event) = persist_sub.recv().await {
            if persist_fwd_tx.send(event).await.is_err() {
                break;
            }
        }
    });

    let outcome = run_streaming_command(
        RunnerCommand {
            program: "sh".to_string(),
            args: vec!["-c".to_string(), runner_command.command],
            cwd: None,
            timeout_seconds: state.config.agent_timeout_seconds.max(1) as u64,
            stdin_json: Some(runner_input.clone()),
        },
        event_tx.clone(),
    )
    .await;

    // Clean up streaming infrastructure
    drop(persist_tx);
    persist_fwd.abort();
    {
        let mut channels = state.task_event_channels.lock().await;
        streaming::remove_channel(&mut channels, &task_id);
    }

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get_mut(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    match outcome {
        Ok(outcome) if outcome.timed_out => {
            finalize_agent_task_agentflow_failure(
                record,
                &now_rfc3339(),
                "runner timed out",
                "runner_failed",
                "runner_failed",
                "智能审计运行失败：AgentFlow runner 执行超时",
                Some(json!({"runner": outcome})),
            );
        }
        Ok(outcome) if outcome.exit_code != Some(0) => {
            finalize_agent_task_agentflow_failure(
                record,
                &now_rfc3339(),
                "runner failed",
                "runner_failed",
                "runner_failed",
                "智能审计运行失败：AgentFlow runner 返回非零退出码",
                Some(json!({"runner": outcome})),
            );
        }
        Ok(outcome) => {
            let Some(output_json) = outcome.output_json.clone() else {
                finalize_agent_task_agentflow_failure(
                    record,
                    &now_rfc3339(),
                    "runner output invalid",
                    "runner_output_invalid",
                    "import_failed",
                    "智能审计运行失败：AgentFlow runner 未输出标准 JSON",
                    Some(json!({"runner": outcome})),
                );
                task_state::save_snapshot(&state, &snapshot)
                    .await
                    .map_err(internal_error)?;
                if let Some(workspace) = &prepared_workspace {
                    let _ = tokio::fs::remove_dir_all(&workspace.workspace_dir).await;
                }
                return Err(ApiError::Internal(
                    "agent task failed: AgentFlow runner output was invalid".to_string(),
                ));
            };
            match import_runner_output(record, &output_json) {
                Ok(()) => {
                    let phase = record.status.clone();
                    push_agent_event(
                        record,
                        "task_completed",
                        Some(&phase),
                        Some("AgentFlow 智能审计任务已完成导入"),
                        Some(json!({
                            "runtime": "agentflow",
                            "runner_exit_code": outcome.exit_code,
                        })),
                    );
                }
                Err(error) => {
                    finalize_agent_task_agentflow_failure(
                        record,
                        &now_rfc3339(),
                        "import failed",
                        error.reason_code,
                        "import_failed",
                        &error.message,
                        Some(json!({
                            "runner": outcome,
                            "import_error": {
                                "reason_code": error.reason_code,
                                "message": error.message,
                            }
                        })),
                    );
                }
            }
        }
        Err(error) => {
            finalize_agent_task_agentflow_failure(
                record,
                &now_rfc3339(),
                "runner failed",
                error.reason_code,
                "runner_failed",
                &error.message,
                Some(json!({
                    "runner_error": {
                        "reason_code": error.reason_code,
                        "message": error.message,
                    }
                })),
            );
        }
    }

    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;
    if let Some(workspace) = prepared_workspace {
        let _ = tokio::fs::remove_dir_all(workspace.workspace_dir).await;
    }
    Ok(Json(json!({
        "message": "agent task start processed by AgentFlow runtime adapter",
        "task_id": task_id,
        "status": snapshot.agent_tasks.get(&task_id).map(|record| record.status.clone()),
    })))
}

async fn cancel_agent_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get_mut(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    record.status = "cancelled".to_string();
    record.current_phase = Some("cancelled".to_string());
    record.current_step = Some("cancelled by request".to_string());
    record.error_message = Some("task cancelled from rust backend".to_string());
    push_agent_event(
        record,
        "task_cancel",
        Some("cancelled"),
        Some("agent task cancelled in rust backend"),
        None,
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({
        "message": "agent task cancelled in rust backend",
        "task_id": task_id,
    })))
}

async fn list_agent_events(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<AgentEventsQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let after_sequence = query.after_sequence.unwrap_or(0);
    let limit = query.limit.unwrap_or(record.events.len());
    let events = record
        .events
        .iter()
        .filter(|event| event.sequence > after_sequence)
        .filter(|event| agent_event_is_user_visible(event))
        .take(limit)
        .map(agent_event_value)
        .collect::<Vec<_>>();
    Ok(Json(events))
}

async fn stream_agent_events(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<AgentEventsQuery>,
) -> Result<Response<Body>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let after_sequence = query.after_sequence.unwrap_or(0);
    let is_terminal = matches!(
        record.status.as_str(),
        "completed" | "failed" | "cancelled"
    );

    // Replay stored events
    let mut replay_payload = record
        .events
        .iter()
        .filter(|event| event.sequence > after_sequence)
        .filter(|event| agent_event_is_user_visible(event))
        .map(agent_event_value)
        .map(|event| format!("event: {}\ndata: {event}\n\n", event.get("type").and_then(Value::as_str).unwrap_or("info")))
        .collect::<String>();

    // For terminal tasks, return one-shot snapshot (existing behavior)
    if is_terminal {
        return Ok(event_stream_response(replay_payload));
    }

    // For running tasks, try to subscribe to broadcast channel for live push
    let maybe_rx = {
        let channels = state.task_event_channels.lock().await;
        channels.get(&task_id).map(|tx| tx.subscribe())
    };

    let Some(mut rx) = maybe_rx else {
        return Ok(event_stream_response(replay_payload));
    };

    // Long-lived SSE: replay stored events, then push live events from broadcast
    let stream = async_stream::stream! {
        // Send replayed stored events
        if !replay_payload.is_empty() {
            yield Ok::<String, std::convert::Infallible>(std::mem::take(&mut replay_payload));
        }

        // Push live events from broadcast channel
        let mut heartbeat_interval = tokio::time::interval(Duration::from_secs(15));
        heartbeat_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

        loop {
            tokio::select! {
                result = rx.recv() => {
                    match result {
                        Ok(event) => {
                            let value = serde_json::to_value(&event).unwrap_or(Value::Null);
                            let event_type = &event.event_type;
                            let line = format!("event: {event_type}\ndata: {value}\n\n");
                            yield Ok(line);
                            if matches!(event_type.as_str(), "task_complete" | "task_error" | "task_cancel" | "task_end") {
                                break;
                            }
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => {
                            continue;
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => {
                            break;
                        }
                    }
                }
                _ = heartbeat_interval.tick() => {
                    yield Ok("event: heartbeat\ndata: {}\n\n".to_string());
                }
            }
        }
    };

    let body = Body::from_stream(stream);
    let mut response = Response::new(body);
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-cache"),
    );
    Ok(response)
}

async fn list_agent_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<AgentFindingsQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let include_false_positive = query.include_false_positive.unwrap_or(false);
    let verified_only = query.verified_only.unwrap_or(false);
    let severity_filter = query.severity.as_deref().map(normalized_token);
    let vulnerability_filter = query.vulnerability_type.as_deref().map(normalized_token);
    let skip = query.skip.unwrap_or(0);
    let limit = query.limit.unwrap_or(record.findings.len());
    let mut findings = record
        .findings
        .iter()
        .filter(|finding| {
            include_false_positive || finding_export_status(finding) != "false_positive"
        })
        .filter(|finding| {
            severity_filter
                .as_deref()
                .is_none_or(|severity| normalized_token(&finding.severity) == severity)
        })
        .filter(|finding| {
            vulnerability_filter
                .as_deref()
                .is_none_or(|vulnerability_type| {
                    normalized_token(&finding.vulnerability_type) == vulnerability_type
                })
        })
        .filter(|finding| !verified_only || finding_export_status(finding) == "verified")
        .collect::<Vec<_>>();
    findings.sort_by(|left, right| {
        severity_rank(&left.severity)
            .cmp(&severity_rank(&right.severity))
            .then_with(|| right.created_at.cmp(&left.created_at))
    });
    Ok(Json(
        findings
            .into_iter()
            .skip(skip)
            .take(limit)
            .map(agent_finding_value)
            .collect::<Vec<_>>(),
    ))
}

async fn get_agent_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
    Query(query): Query<AgentFindingDetailQuery>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let finding = record
        .findings
        .iter()
        .find(|finding| finding.id == finding_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?;
    if !query.include_false_positive.unwrap_or(true)
        && finding_export_status(finding) == "false_positive"
    {
        return Err(ApiError::NotFound(format!(
            "agent finding not found: {finding_id}"
        )));
    }
    Ok(Json(agent_finding_value(finding)))
}

async fn update_agent_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get_mut(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    {
        let finding = record
            .findings
            .iter_mut()
            .find(|finding| finding.id == finding_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?;
        if let Some(status) = optional_string(&payload, "status") {
            finding.status = status;
        }
    }
    refresh_agent_task_aggregates(record);
    let response_value = agent_finding_value(
        record
            .findings
            .iter()
            .find(|finding| finding.id == finding_id)
            .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?,
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;
    Ok(Json(response_value))
}

async fn update_agent_finding_status(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
    Query(query): Query<FindingStatusQuery>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get_mut(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let finding = record
        .findings
        .iter_mut()
        .find(|finding| finding.id == finding_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?;
    finding.status = query.status.clone();
    finding.is_verified = query.status == "verified";
    if query.status == "false_positive" {
        finding.verdict = Some("false_positive".to_string());
        finding.authenticity = Some("false_positive".to_string());
    } else if query.status == "verified" {
        finding.verdict = Some("confirmed".to_string());
        finding.authenticity = Some("confirmed".to_string());
    }
    refresh_agent_task_aggregates(record);
    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({
        "message": "agent finding status updated in rust backend",
        "finding_id": finding_id,
        "status": query.status,
    })))
}

async fn get_agent_task_summary(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let mut vulnerability_types = BTreeMap::<String, Value>::new();
    for finding in &record.findings {
        if finding_export_status(finding) == "false_positive" {
            continue;
        }
        let key = normalized_token(&finding.vulnerability_type);
        let entry = vulnerability_types
            .entry(key)
            .or_insert_with(|| json!({"total": 0, "verified": 0}));
        if let Some(object) = entry.as_object_mut() {
            object.insert(
                "total".to_string(),
                json!(object.get("total").and_then(Value::as_i64).unwrap_or(0) + 1),
            );
            if finding_export_status(finding) == "verified" {
                object.insert(
                    "verified".to_string(),
                    json!(object.get("verified").and_then(Value::as_i64).unwrap_or(0) + 1),
                );
            }
        }
    }
    Ok(Json(json!({
        "task_id": record.id,
        "status": record.status,
        "progress_percentage": record.progress_percentage,
        "security_score": record.security_score.unwrap_or(0.0),
        "quality_score": record.quality_score,
        "statistics": {
            "total_files": record.total_files,
            "indexed_files": record.indexed_files,
            "analyzed_files": record.analyzed_files,
            "files_with_findings": record.files_with_findings,
            "total_chunks": record.total_chunks,
            "findings_count": record.findings_count,
            "verified_count": record.verified_count,
            "false_positive_count": record.false_positive_count,
        },
        "severity_distribution": {
            "critical": record.critical_count,
            "high": record.high_count,
            "medium": record.medium_count,
            "low": record.low_count,
        },
        "vulnerability_types": vulnerability_types,
        "duration_seconds": duration_seconds(record.started_at.as_deref(), record.completed_at.as_deref()),
    })))
}

async fn get_agent_tree(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    Ok(Json(json!({
        "task_id": record.id,
        "root_agent_id": record.agent_tree.first().and_then(|node| node.get("agent_id")).cloned().unwrap_or(Value::Null),
        "total_agents": record.agent_tree.len(),
        "running_agents": 0,
        "completed_agents": if record.status == "completed" { record.agent_tree.len() } else { 0 },
        "failed_agents": if record.status == "failed" { record.agent_tree.len() } else { 0 },
        "total_findings": record.findings_count,
        "verified_total_findings": record.verified_count,
        "nodes": record.agent_tree,
    })))
}

async fn list_checkpoints(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<CheckpointListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let limit = query.limit.unwrap_or(record.checkpoints.len());
    let mut checkpoints = record
        .checkpoints
        .iter()
        .filter(|checkpoint| {
            query
                .agent_id
                .as_deref()
                .is_none_or(|agent_id| checkpoint.agent_id == agent_id)
        })
        .collect::<Vec<_>>();
    checkpoints.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    Ok(Json(
        checkpoints
            .into_iter()
            .take(limit)
            .map(checkpoint_summary_value)
            .collect::<Vec<_>>(),
    ))
}

async fn get_checkpoint_detail(
    State(state): State<AppState>,
    AxumPath((task_id, checkpoint_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let checkpoint = record
        .checkpoints
        .iter()
        .find(|checkpoint| checkpoint.id == checkpoint_id)
        .ok_or_else(|| ApiError::NotFound(format!("checkpoint not found: {checkpoint_id}")))?;
    Ok(Json(checkpoint_detail_value(checkpoint)))
}

async fn download_report(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ReportQuery>,
) -> Result<Response<Body>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let project = load_agent_task_project(&state, &record.project_id).await?;
    let options = report_export_options(&query);
    let format = normalize_report_format(query.format.as_deref(), true);
    let report_json = build_agent_report_json(record, &project, &options);
    let markdown = build_agent_report_markdown(record, &project, &options);
    let filename = build_report_download_filename(&project.name, report_extension(&format));

    let (content_type, body) = match format.as_str() {
        "json" => (
            "application/json",
            serde_json::to_vec(&report_json).map_err(internal_error)?,
        ),
        "pdf" => ("application/pdf", minimal_pdf_bytes(&markdown)),
        _ => ("text/markdown; charset=utf-8", markdown.into_bytes()),
    };

    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_str(content_type).map_err(internal_error)?,
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&build_content_disposition(&filename)).map_err(internal_error)?,
    );
    Ok(response)
}

async fn download_finding_report(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
    Query(query): Query<ReportQuery>,
) -> Result<Response<Body>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let finding = record
        .findings
        .iter()
        .find(|finding| finding.id == finding_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?;
    let project = load_agent_task_project(&state, &record.project_id).await?;
    let options = report_export_options(&query);
    let format = normalize_report_format(query.format.as_deref(), true);
    let report_json = build_agent_finding_report_json(record, &project, finding, &options);
    let markdown = build_agent_finding_report_markdown(record, &project, finding, &options);
    let filename = build_finding_report_filename(&project.name, finding, report_extension(&format));

    let (content_type, body) = match format.as_str() {
        "json" => (
            "application/json",
            serde_json::to_vec(&report_json).map_err(internal_error)?,
        ),
        "pdf" => ("application/pdf", minimal_pdf_bytes(&markdown)),
        _ => ("text/markdown; charset=utf-8", markdown.into_bytes()),
    };

    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_str(content_type).map_err(internal_error)?,
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&build_content_disposition(&filename)).map_err(internal_error)?,
    );
    Ok(response)
}

#[derive(Debug, Clone)]
struct AgentReportProject {
    id: String,
    name: String,
}

#[derive(Debug, Clone, Copy)]
struct ReportExportOptions {
    include_code_snippets: bool,
    include_remediation: bool,
    include_metadata: bool,
    compact_mode: bool,
}

async fn load_agent_task_project(
    state: &AppState,
    project_id: &str,
) -> Result<AgentReportProject, ApiError> {
    let project = projects::get_project(state, project_id)
        .await
        .map_err(internal_error)?;
    if let Some(project) = project {
        return Ok(AgentReportProject {
            id: project.id,
            name: project.name,
        });
    }
    let fallback = project_id
        .chars()
        .take(8)
        .collect::<String>()
        .trim()
        .to_string();
    Ok(AgentReportProject {
        id: project_id.to_string(),
        name: if fallback.is_empty() {
            "project".to_string()
        } else {
            fallback
        },
    })
}

fn report_export_options(query: &ReportQuery) -> ReportExportOptions {
    ReportExportOptions {
        include_code_snippets: query.include_code_snippets.unwrap_or(true),
        include_remediation: query.include_remediation.unwrap_or(true),
        include_metadata: query.include_metadata.unwrap_or(true),
        compact_mode: query.compact_mode.unwrap_or(false),
    }
}

fn normalize_report_format(format: Option<&str>, allow_pdf: bool) -> String {
    let normalized = format.unwrap_or("markdown").trim().to_ascii_lowercase();
    match normalized.as_str() {
        "json" => "json".to_string(),
        "pdf" if allow_pdf => "pdf".to_string(),
        "markdown" => "markdown".to_string(),
        _ => "markdown".to_string(),
    }
}

fn report_extension(format: &str) -> &'static str {
    match format {
        "json" => "json",
        "pdf" => "pdf",
        _ => "md",
    }
}

fn refresh_agent_task_aggregates(record: &mut task_state::AgentTaskRecord) {
    let mut active_findings = 0i64;
    let mut verified = 0i64;
    let mut false_positive = 0i64;
    let mut critical = 0i64;
    let mut high = 0i64;
    let mut medium = 0i64;
    let mut low = 0i64;
    let mut verified_critical = 0i64;
    let mut verified_high = 0i64;
    let mut verified_medium = 0i64;
    let mut verified_low = 0i64;
    let mut files = std::collections::BTreeSet::new();

    for finding in &record.findings {
        let status = finding.status.to_ascii_lowercase();
        let severity = finding.severity.to_ascii_lowercase();
        if status == "false_positive" {
            false_positive += 1;
            continue;
        }
        active_findings += 1;
        if status == "verified" {
            verified += 1;
        }
        if let Some(file_path) = finding
            .resolved_file_path
            .as_deref()
            .or(finding.file_path.as_deref())
        {
            files.insert(file_path.to_string());
        }
        match severity.as_str() {
            "critical" => {
                critical += 1;
                if status == "verified" {
                    verified_critical += 1;
                }
            }
            "high" => {
                high += 1;
                if status == "verified" {
                    verified_high += 1;
                }
            }
            "medium" => {
                medium += 1;
                if status == "verified" {
                    verified_medium += 1;
                }
            }
            _ => {
                low += 1;
                if status == "verified" {
                    verified_low += 1;
                }
            }
        }
    }

    record.findings_count = active_findings;
    record.verified_count = verified;
    record.false_positive_count = false_positive;
    record.files_with_findings = files.len() as i64;
    record.critical_count = critical;
    record.high_count = high;
    record.medium_count = medium;
    record.low_count = low;
    record.verified_critical_count = verified_critical;
    record.verified_high_count = verified_high;
    record.verified_medium_count = verified_medium;
    record.verified_low_count = verified_low;
}

fn seed_failed_agent_task_tree(record: &mut task_state::AgentTaskRecord, summary: &str) {
    record.agent_tree = vec![json!({
        "id": format!("root-{}", record.id),
        "agent_id": format!("root-{}", record.id),
        "agent_name": "RustAgentRoot",
        "agent_type": "root",
        "parent_agent_id": Value::Null,
        "depth": 0,
        "task_description": record.description,
        "status": "failed",
        "result_summary": summary,
        "findings_count": 0,
        "verified_findings_count": 0,
        "iterations": record.total_iterations.max(1),
        "tokens_used": 0,
        "tool_calls": 0,
        "duration_ms": 0,
        "children": Vec::<Value>::new(),
    })];
}

fn mark_agent_tree_failed(nodes: &mut [Value], summary: &str) {
    for node in nodes {
        if let Some(node_object) = node.as_object_mut() {
            node_object.insert("status".to_string(), json!("failed"));
            node_object.insert("result_summary".to_string(), json!(summary));
            if let Some(children) = node_object
                .get_mut("children")
                .and_then(Value::as_array_mut)
            {
                mark_agent_tree_failed(children, summary);
            }
        }
    }
}

#[cfg(test)]
fn finalize_agent_task_forbidden_static_input(
    record: &mut task_state::AgentTaskRecord,
    now: &str,
    error: &str,
) {
    if record.agent_tree.is_empty() {
        seed_failed_agent_task_tree(record, error);
    } else {
        mark_agent_tree_failed(&mut record.agent_tree, error);
    }
    record.status = "failed".to_string();
    record.current_phase = Some("failed".to_string());
    record.current_step = Some("forbidden static input".to_string());
    record.completed_at = Some(now.to_string());
    record.progress_percentage = 100.0;
    record.quality_score = 0.0;
    record.security_score = Some(0.0);
    record.error_message = Some(error.to_string());
    push_agent_event(
        record,
        "forbidden_static_input",
        Some("failed"),
        Some("智能审计任务包含禁止的静态扫描候选输入，已拒绝启动"),
        Some(json!({"reason_code": "forbidden_static_input", "error": error})),
    );
    push_checkpoint(record, "import_failed", Some("forbidden_static_input"));
}

#[cfg(test)]
fn finalize_agent_task_failed(record: &mut task_state::AgentTaskRecord, now: &str, error: &str) {
    if record.agent_tree.is_empty() {
        seed_failed_agent_task_tree(record, error);
    } else {
        mark_agent_tree_failed(&mut record.agent_tree, error);
    }
    record.status = "failed".to_string();
    record.current_phase = Some("failed".to_string());
    record.current_step = Some("agentflow runtime failed".to_string());
    record.completed_at = Some(now.to_string());
    record.progress_percentage = 100.0;
    record.quality_score = 0.0;
    record.security_score = Some(0.0);
    record.error_message = Some(error.to_string());
    record.tool_calls_count = record.agent_tree.len().saturating_sub(1) as i64;
    record.tokens_used = 0;
    push_agent_event(
        record,
        "phase_start",
        Some("analysis"),
        Some("agent task execution started in rust backend"),
        None,
    );
    push_agent_event(
        record,
        "task_error",
        Some("failed"),
        Some("agentflow runtime failed in rust backend"),
        Some(json!({"error": error})),
    );
    push_checkpoint(record, "final", Some("failed"));
}

async fn flush_streaming_events(
    state: &AppState,
    task_id: &str,
    buffer: &mut Vec<StreamingEvent>,
) {
    let events = std::mem::take(buffer);
    if events.is_empty() {
        return;
    }
    let result: Result<(), anyhow::Error> = async {
        let _guard = state.file_store_lock.lock().await;
        let mut snapshot = task_state::load_snapshot_unlocked(state).await?;
        if let Some(record) = snapshot.agent_tasks.get_mut(task_id) {
            for event in &events {
                task_state::append_streaming_event(record, event);
            }
            if let Some(last_node) = events
                .iter()
                .rev()
                .find(|e| e.event_type == "node_start")
            {
                record.current_step = Some(format!(
                    "Running: {}",
                    last_node.node_id.as_deref().unwrap_or("agent")
                ));
            }
        }
        task_state::save_snapshot_unlocked(state, &snapshot).await?;
        Ok(())
    }
    .await;
    if let Err(error) = result {
        eprintln!("[incremental-persist] task {task_id}: {error}");
    }
}

fn finalize_agent_task_agentflow_failure(
    record: &mut task_state::AgentTaskRecord,
    now: &str,
    current_step: &str,
    reason_code: &str,
    checkpoint_name: &str,
    error: &str,
    diagnostics: Option<Value>,
) {
    if record.agent_tree.is_empty() {
        seed_failed_agent_task_tree(record, error);
    } else {
        mark_agent_tree_failed(&mut record.agent_tree, error);
    }
    record.status = "failed".to_string();
    record.current_phase = Some("failed".to_string());
    record.current_step = Some(current_step.to_string());
    record.completed_at = Some(now.to_string());
    record.progress_percentage = 100.0;
    record.quality_score = 0.0;
    record.security_score = Some(0.0);
    record.error_message = Some(error.to_string());
    let diagnostic_payload = json!({
        "runtime": "agentflow",
        "reason_code": reason_code,
        "message": error,
        "details": diagnostics.unwrap_or(Value::Null),
    });
    record.diagnostics = Some(diagnostic_payload.clone());
    push_agent_event(
        record,
        reason_code,
        Some("failed"),
        Some(error),
        Some(diagnostic_payload),
    );
    push_checkpoint(record, "failed", Some(checkpoint_name));
}

fn finding_export_status(finding: &task_state::AgentFindingRecord) -> &'static str {
    let status = finding.status.trim().to_ascii_lowercase();
    let verdict = finding
        .verdict
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    let authenticity = finding
        .authenticity
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();

    if status == "false_positive" || verdict == "false_positive" || authenticity == "false_positive"
    {
        "false_positive"
    } else if finding.is_verified
        || status == "verified"
        || verdict == "confirmed"
        || authenticity == "confirmed"
    {
        "verified"
    } else {
        "pending"
    }
}

fn normalized_token(value: &str) -> String {
    value.trim().to_ascii_lowercase()
}

fn severity_rank(severity: &str) -> i32 {
    match normalized_token(severity).as_str() {
        "critical" => 0,
        "high" => 1,
        "medium" => 2,
        "low" => 3,
        _ => 4,
    }
}

fn build_agent_report_json(
    record: &task_state::AgentTaskRecord,
    project: &AgentReportProject,
    options: &ReportExportOptions,
) -> Value {
    let mut severity_distribution = BTreeMap::<String, i64>::new();
    let mut status_distribution = BTreeMap::<String, i64>::new();
    for finding in &record.findings {
        *severity_distribution
            .entry(finding.severity.to_ascii_lowercase())
            .or_insert(0) += 1;
        *status_distribution
            .entry(finding.status.to_ascii_lowercase())
            .or_insert(0) += 1;
    }

    json!({
        "report_metadata": {
            "task_id": record.id,
            "project_id": project.id,
            "project_name": project.name,
            "generated_at": now_rfc3339(),
            "task_status": record.status,
        },
        "summary": {
            "total_findings": record.findings.len(),
            "active_findings": record.findings_count,
            "verified_findings": record.verified_count,
            "false_positive_findings": record.false_positive_count,
            "severity_distribution": severity_distribution,
            "status_distribution": status_distribution,
            "security_score": record.security_score.unwrap_or(0.0),
            "quality_score": record.quality_score,
            "progress_percentage": record.progress_percentage,
            "tool_calls": record.tool_calls_count,
            "tokens_used": record.tokens_used,
        },
        "export_options": {
            "include_code_snippets": options.include_code_snippets,
            "include_remediation": options.include_remediation,
            "include_metadata": options.include_metadata,
            "compact_mode": options.compact_mode,
        },
        "findings": record
            .findings
            .iter()
            .map(|finding| export_finding_json(finding, options))
            .collect::<Vec<_>>(),
    })
}

fn build_agent_report_markdown(
    record: &task_state::AgentTaskRecord,
    project: &AgentReportProject,
    options: &ReportExportOptions,
) -> String {
    let mut lines = vec![
        format!(
            "# 漏洞报告：{}",
            render_markdown_heading_text(&project.name)
        ),
        String::new(),
        "## 执行摘要".to_string(),
        String::new(),
        format!("- 任务状态：`{}`", record.status),
        format!("- 进度：`{:.1}%`", record.progress_percentage),
        format!("- 漏洞总数：`{}`", record.findings.len()),
        format!("- 已验证漏洞：`{}`", record.verified_count),
        format!("- 误报漏洞：`{}`", record.false_positive_count),
        format!(
            "- 安全评分：`{:.1}` / 100",
            record.security_score.unwrap_or(0.0)
        ),
        String::new(),
    ];

    if options.include_metadata {
        lines.push("## 元数据".to_string());
        lines.push(String::new());
        lines.push(format!("- 项目 ID：`{}`", project.id));
        lines.push(format!("- 任务 ID：`{}`", record.id));
        lines.push(format!("- 任务类型：`{}`", record.task_type));
        lines.push(format!("- 创建时间：`{}`", record.created_at));
        if let Some(started_at) = record.started_at.as_deref() {
            lines.push(format!("- 启动时间：`{started_at}`"));
        }
        if let Some(completed_at) = record.completed_at.as_deref() {
            lines.push(format!("- 完成时间：`{completed_at}`"));
        }
        lines.push(String::new());
    }

    if let Some(task_report) = record.report.as_deref() {
        let normalized = task_report.trim();
        if !normalized.is_empty() {
            lines.push("## 项目报告".to_string());
            lines.push(String::new());
            lines.push(normalized.to_string());
            lines.push(String::new());
        }
    }

    lines.push("## 漏洞列表".to_string());
    lines.push(String::new());
    if record.findings.is_empty() {
        lines.push("_当前任务无漏洞数据。_".to_string());
    } else {
        for (index, finding) in record.findings.iter().enumerate() {
            lines.push(format!(
                "### 漏洞 {}：{}",
                index + 1,
                render_markdown_heading_text(
                    finding
                        .display_title
                        .as_deref()
                        .unwrap_or(finding.title.as_str())
                )
            ));
            lines.push(String::new());
            lines.push(format!("- ID：`{}`", finding.id));
            lines.push(format!(
                "- 严重级别：`{}`",
                finding.severity.to_ascii_lowercase()
            ));
            lines.push(format!("- 状态：`{}`", finding.status.to_ascii_lowercase()));
            lines.push(format!(
                "- 漏洞类型：`{}`",
                finding.vulnerability_type.to_ascii_lowercase()
            ));
            if options.include_metadata {
                if let Some(path) = finding
                    .resolved_file_path
                    .as_deref()
                    .or(finding.file_path.as_deref())
                {
                    if let Some(line) = finding.resolved_line_start.or(finding.line_start) {
                        lines.push(format!(
                            "- 位置：`{}:{}`",
                            render_markdown_heading_text(path),
                            line
                        ));
                    } else {
                        lines.push(format!("- 位置：`{}`", render_markdown_heading_text(path)));
                    }
                }
            }
            if let Some(description) = finding
                .description_markdown
                .as_deref()
                .or(finding.description.as_deref())
            {
                if !description.trim().is_empty() {
                    lines.push(String::new());
                    lines.push("**漏洞描述**".to_string());
                    lines.push(String::new());
                    lines.push(description.trim().to_string());
                }
            }
            if options.include_code_snippets {
                if let Some(code_snippet) = finding.code_snippet.as_deref() {
                    if !code_snippet.trim().is_empty() {
                        lines.push(String::new());
                        lines.push("**代码片段**".to_string());
                        lines.push(String::new());
                        lines.push("```text".to_string());
                        lines.push(code_snippet.trim().to_string());
                        lines.push("```".to_string());
                    }
                }
            }
            if options.include_remediation {
                if let Some(suggestion) = finding.suggestion.as_deref() {
                    if !suggestion.trim().is_empty() {
                        lines.push(String::new());
                        lines.push("**修复建议**".to_string());
                        lines.push(String::new());
                        lines.push(suggestion.trim().to_string());
                    }
                }
            }
            lines.push(String::new());
        }
    }

    lines.push("---".to_string());
    lines.push(String::new());
    lines.push("*本报告由 Rust backend 生成*".to_string());

    let raw = lines.join("\n");
    let mut markdown = if options.compact_mode {
        compact_markdown(&raw)
    } else {
        raw
    };
    if !markdown.ends_with('\n') {
        markdown.push('\n');
    }
    markdown
}

fn build_agent_finding_report_json(
    record: &task_state::AgentTaskRecord,
    project: &AgentReportProject,
    finding: &task_state::AgentFindingRecord,
    options: &ReportExportOptions,
) -> Value {
    json!({
        "report_metadata": {
            "task_id": record.id,
            "finding_id": finding.id,
            "project_id": project.id,
            "project_name": project.name,
            "generated_at": now_rfc3339(),
            "task_status": record.status,
        },
        "finding": export_finding_json(finding, options),
    })
}

fn build_agent_finding_report_markdown(
    record: &task_state::AgentTaskRecord,
    project: &AgentReportProject,
    finding: &task_state::AgentFindingRecord,
    options: &ReportExportOptions,
) -> String {
    let title = finding
        .display_title
        .as_deref()
        .unwrap_or(finding.title.as_str());
    let mut lines = vec![
        format!("# 漏洞详情报告：{}", render_markdown_heading_text(title)),
        String::new(),
        format!("- 项目：`{}`", render_markdown_heading_text(&project.name)),
        format!("- 任务 ID：`{}`", record.id),
        format!("- 漏洞 ID：`{}`", finding.id),
        format!("- 严重级别：`{}`", finding.severity.to_ascii_lowercase()),
        format!("- 状态：`{}`", finding.status.to_ascii_lowercase()),
        format!(
            "- 漏洞类型：`{}`",
            finding.vulnerability_type.to_ascii_lowercase()
        ),
        String::new(),
    ];

    if options.include_metadata {
        if let Some(path) = finding
            .resolved_file_path
            .as_deref()
            .or(finding.file_path.as_deref())
        {
            if let Some(line) = finding.resolved_line_start.or(finding.line_start) {
                lines.push(format!(
                    "- 位置：`{}:{}`",
                    render_markdown_heading_text(path),
                    line
                ));
            } else {
                lines.push(format!("- 位置：`{}`", render_markdown_heading_text(path)));
            }
        }
        if let Some(confidence) = finding.confidence.or(finding.ai_confidence) {
            lines.push(format!("- 置信度：`{confidence:.2}`"));
        }
        lines.push(String::new());
    }

    if let Some(description) = finding
        .description_markdown
        .as_deref()
        .or(finding.description.as_deref())
    {
        if !description.trim().is_empty() {
            lines.push("## 漏洞描述".to_string());
            lines.push(String::new());
            lines.push(description.trim().to_string());
            lines.push(String::new());
        }
    }

    if options.include_code_snippets {
        if let Some(code_snippet) = finding.code_snippet.as_deref() {
            if !code_snippet.trim().is_empty() {
                lines.push("## 代码片段".to_string());
                lines.push(String::new());
                lines.push("```text".to_string());
                lines.push(code_snippet.trim().to_string());
                lines.push("```".to_string());
                lines.push(String::new());
            }
        }
    }

    if options.include_remediation {
        if let Some(suggestion) = finding.suggestion.as_deref() {
            if !suggestion.trim().is_empty() {
                lines.push("## 修复建议".to_string());
                lines.push(String::new());
                lines.push(suggestion.trim().to_string());
                lines.push(String::new());
            }
        }
    }

    if let Some(report) = finding.report.as_deref() {
        if !report.trim().is_empty() {
            lines.push("## 报告补充".to_string());
            lines.push(String::new());
            lines.push(report.trim().to_string());
            lines.push(String::new());
        }
    }

    let raw = lines.join("\n");
    let mut markdown = if options.compact_mode {
        compact_markdown(&raw)
    } else {
        raw
    };
    if !markdown.ends_with('\n') {
        markdown.push('\n');
    }
    markdown
}

fn export_finding_json(
    finding: &task_state::AgentFindingRecord,
    options: &ReportExportOptions,
) -> Value {
    let mut value = serde_json::Map::new();
    value.insert("id".to_string(), json!(finding.id));
    value.insert(
        "title".to_string(),
        json!(finding
            .display_title
            .clone()
            .unwrap_or_else(|| finding.title.clone())),
    );
    value.insert(
        "severity".to_string(),
        json!(finding.severity.to_ascii_lowercase()),
    );
    value.insert(
        "status".to_string(),
        json!(finding.status.to_ascii_lowercase()),
    );
    value.insert(
        "vulnerability_type".to_string(),
        json!(finding.vulnerability_type.to_ascii_lowercase()),
    );
    value.insert(
        "description".to_string(),
        json!(finding
            .description_markdown
            .as_deref()
            .or(finding.description.as_deref())),
    );
    value.insert("verdict".to_string(), json!(finding.verdict));
    value.insert("authenticity".to_string(), json!(finding.authenticity));
    value.insert("reachability".to_string(), json!(finding.reachability));
    value.insert("is_verified".to_string(), json!(finding.is_verified));
    if options.include_metadata {
        value.insert("file_path".to_string(), json!(finding.file_path));
        value.insert("line_start".to_string(), json!(finding.line_start));
        value.insert("line_end".to_string(), json!(finding.line_end));
        value.insert(
            "resolved_file_path".to_string(),
            json!(finding.resolved_file_path),
        );
        value.insert(
            "resolved_line_start".to_string(),
            json!(finding.resolved_line_start),
        );
        value.insert("confidence".to_string(), json!(finding.confidence));
        value.insert("ai_confidence".to_string(), json!(finding.ai_confidence));
        value.insert("created_at".to_string(), json!(finding.created_at));
    }
    if options.include_code_snippets {
        value.insert("code_snippet".to_string(), json!(finding.code_snippet));
        value.insert("code_context".to_string(), json!(finding.code_context));
    }
    if options.include_remediation {
        value.insert("suggestion".to_string(), json!(finding.suggestion));
        value.insert("fix_code".to_string(), json!(finding.fix_code));
    }
    if finding.report.is_some() {
        value.insert("report".to_string(), json!(finding.report));
    }
    Value::Object(value)
}

fn compact_markdown(markdown_text: &str) -> String {
    let mut compacted = Vec::new();
    let mut previous_blank = false;
    let mut in_code_fence = false;
    for raw_line in markdown_text
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .lines()
    {
        let line = raw_line.trim_end();
        if line.starts_with("```") {
            in_code_fence = !in_code_fence;
            previous_blank = false;
            compacted.push(line.to_string());
            continue;
        }
        if in_code_fence {
            compacted.push(line.to_string());
            continue;
        }
        if line.trim().is_empty() {
            if !previous_blank {
                compacted.push(String::new());
                previous_blank = true;
            }
            continue;
        }
        previous_blank = false;
        compacted.push(line.to_string());
    }
    compacted.join("\n").trim().to_string()
}

fn render_markdown_heading_text(text: &str) -> String {
    text.replace("\r\n", "\n")
        .replace('\r', "\n")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn build_report_download_filename(project_name: &str, extension: &str) -> String {
    let project_fallback = "project";
    let project_name = sanitize_download_filename_segment(project_name, project_fallback);
    let date_part = OffsetDateTime::now_utc()
        .format(&format_description!("[year]-[month]-[day]"))
        .unwrap_or_else(|_| "1970-01-01".to_string());
    let extension = extension.trim_start_matches('.').trim();
    let extension = if extension.is_empty() {
        "txt"
    } else {
        extension
    };
    format!("漏洞报告-{project_name}-{date_part}.{extension}")
}

fn build_finding_report_filename(
    project_name: &str,
    finding: &task_state::AgentFindingRecord,
    extension: &str,
) -> String {
    let base = build_report_download_filename(project_name, extension);
    let finding_short = finding.id.chars().take(8).collect::<String>();
    let marker = if finding_short.is_empty() {
        "finding".to_string()
    } else {
        format!("finding-{finding_short}")
    };
    if let Some((stem, ext)) = base.rsplit_once('.') {
        format!("{stem}-{marker}.{ext}")
    } else {
        format!("{base}-{marker}")
    }
}

fn sanitize_download_filename_segment(value: &str, fallback: &str) -> String {
    let text = value.trim();
    if text.is_empty() {
        return fallback.to_string();
    }
    let mut sanitized = String::with_capacity(text.len());
    for ch in text.chars() {
        if matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*') || ch.is_control() {
            sanitized.push('-');
        } else {
            sanitized.push(ch);
        }
    }
    let collapsed = sanitized.split_whitespace().collect::<Vec<_>>().join(" ");
    let trimmed = collapsed.trim_matches(|ch| ch == '.' || ch == ' ').trim();
    if trimmed.is_empty() {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

fn build_content_disposition(filename: &str) -> String {
    let (stem, extension) = match filename.rsplit_once('.') {
        Some((stem, ext)) => (stem, format!(".{ext}")),
        None => (filename, String::new()),
    };
    let mut ascii_stem = stem
        .chars()
        .map(|ch| {
            if ch.is_ascii_graphic() || ch == ' ' {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    while ascii_stem.contains("__") {
        ascii_stem = ascii_stem.replace("__", "_");
    }
    let ascii_stem = ascii_stem.trim_matches(|ch| ch == '.' || ch == ' ' || ch == '_' || ch == '-');
    let ascii_stem = if ascii_stem.is_empty() {
        "vulnerability-report"
    } else {
        ascii_stem
    };
    let ascii_filename = format!("{ascii_stem}{extension}");
    let encoded_filename = percent_encode_utf8(filename);
    format!("attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}")
}

fn percent_encode_utf8(text: &str) -> String {
    let mut encoded = String::new();
    for byte in text.as_bytes() {
        if matches!(byte, b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~') {
            encoded.push(*byte as char);
        } else {
            encoded.push('%');
            encoded.push_str(&format!("{byte:02X}"));
        }
    }
    encoded
}

#[derive(Clone, Debug)]
struct AgentflowRunnerCommand {
    command: String,
    source: AgentflowRunnerCommandSource,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum AgentflowRunnerCommandSource {
    ExplicitEnv,
    DefaultDocker,
}

#[derive(Debug)]
struct AgentflowWorkspace {
    workspace_dir: PathBuf,
    container_source_dir: String,
    container_output_dir: String,
}

#[derive(Debug)]
struct AgentflowWorkspaceError {
    reason_code: &'static str,
    message: String,
}

fn agentflow_runner_command() -> Option<AgentflowRunnerCommand> {
    if let Some(command) = env::var("AGENTFLOW_RUNNER_COMMAND")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    {
        return Some(AgentflowRunnerCommand {
            command,
            source: AgentflowRunnerCommandSource::ExplicitEnv,
        });
    }

    default_agentflow_runner_enabled().then(|| AgentflowRunnerCommand {
        command: default_agentflow_runner_command(),
        source: AgentflowRunnerCommandSource::DefaultDocker,
    })
}

fn default_agentflow_runner_enabled() -> bool {
    env::var("AGENTFLOW_DEFAULT_RUNNER_ENABLED")
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            !matches!(
                normalized.as_str(),
                "0" | "false" | "no" | "off" | "disabled"
            )
        })
        .unwrap_or(true)
}

fn default_agentflow_runner_command() -> String {
    let image = env_trimmed("ARGUS_AGENTFLOW_RUNNER_IMAGE")
        .unwrap_or_else(|| DEFAULT_AGENTFLOW_RUNNER_IMAGE.to_string());
    let scan_volume = env_trimmed("SCAN_WORKSPACE_VOLUME")
        .unwrap_or_else(|| DEFAULT_SCAN_WORKSPACE_VOLUME.to_string());
    let work_volume = env_trimmed("AGENTFLOW_RUNNER_WORK_VOLUME")
        .unwrap_or_else(|| DEFAULT_AGENTFLOW_WORK_VOLUME.to_string());
    let codex_host_dir = env_trimmed("ARGUS_CODEX_HOST_DIR");
    let network = env_trimmed("AGENTFLOW_RUNNER_NETWORK").unwrap_or_else(|| "bridge".to_string());
    let container_cli = env_trimmed("CONTAINER_CLI")
        .or_else(|| env_trimmed("BACKEND_DOCKER_BIN"))
        .unwrap_or_else(|| "docker".to_string());
    let mut command = vec![
        container_cli,
        "run".to_string(),
        "--rm".to_string(),
        "-i".to_string(),
        "--pull".to_string(),
        "never".to_string(),
        "--network".to_string(),
        network,
        "--read-only".to_string(),
        "--security-opt".to_string(),
        "no-new-privileges:true".to_string(),
        "--cap-drop".to_string(),
        "ALL".to_string(),
        "--pids-limit".to_string(),
        "512".to_string(),
        "--memory".to_string(),
        "4g".to_string(),
        "--cpus".to_string(),
        "2".to_string(),
        "--tmpfs".to_string(),
        "/tmp:rw,nosuid,nodev,noexec,size=512m".to_string(),
        "-v".to_string(),
        format!("{scan_volume}:/workspace:ro"),
        "-v".to_string(),
        format!("{work_volume}:/work:rw"),
        "-e".to_string(),
        "AGENTFLOW_RUNS_DIR=/work/agentflow-runs".to_string(),
        "-e".to_string(),
        "ARGUS_AGENTFLOW_OUTPUT_DIR=/work/outputs".to_string(),
        "-e".to_string(),
        "ARGUS_AGENTFLOW_INPUT_PATH=/work/input/runner_input.json".to_string(),
        "-e".to_string(),
        "HOME=/tmp/argus-agentflow-home".to_string(),
    ];
    if let Some(codex_host_dir) = codex_host_dir {
        command.extend([
            "--user".to_string(),
            // Local Codex credentials are normally 0600 on the host. The bind
            // mount is read-only, but the runner must run as root to read them.
            "0:0".to_string(),
            "--cap-add".to_string(),
            // The runner still writes /work while using a pre-existing named
            // volume initialized for the non-root agentflow user.
            "DAC_OVERRIDE".to_string(),
            "-v".to_string(),
            format!("{codex_host_dir}:/run/argus-codex:ro"),
            "-e".to_string(),
            "ARGUS_CODEX_CONFIG_FILE=/run/argus-codex/config.toml".to_string(),
            "-e".to_string(),
            "ARGUS_CODEX_AUTH_FILE=/run/argus-codex/auth.json".to_string(),
        ]);
    }
    command.extend([image, "argus-agentflow-runner".to_string()]);
    command
        .into_iter()
        .map(|part| shell_quote(&part))
        .collect::<Vec<_>>()
        .join(" ")
}

fn env_trimmed(key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn shell_quote(value: &str) -> String {
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.' | '/' | ':' | '='))
    {
        value.to_string()
    } else {
        format!("'{}'", value.replace('\'', "'\"'\"'"))
    }
}

async fn prepare_agentflow_workspace(
    project: &StoredProject,
    task_id: &str,
) -> Result<AgentflowWorkspace, AgentflowWorkspaceError> {
    let archive = project
        .archive
        .as_ref()
        .ok_or_else(|| AgentflowWorkspaceError {
            reason_code: "project_archive_missing",
            message: "智能审计启动失败：项目归档不存在，无法准备 AgentFlow 源码工作区".to_string(),
        })?;
    let workspace_root = agentflow_scan_workspace_root();
    let task_segment = safe_path_segment(task_id);
    let workspace_dir = workspace_root.join("agentflow-runtime").join(&task_segment);
    let source_dir = workspace_dir.join("source");
    let output_dir = workspace_dir.join("output");
    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
    tokio::fs::create_dir_all(&source_dir)
        .await
        .map_err(|error| AgentflowWorkspaceError {
            reason_code: "workspace_prepare_failed",
            message: format!("智能审计启动失败：无法创建 AgentFlow 源码工作区：{error}"),
        })?;
    tokio::fs::create_dir_all(&output_dir)
        .await
        .map_err(|error| AgentflowWorkspaceError {
            reason_code: "workspace_prepare_failed",
            message: format!("智能审计启动失败：无法创建 AgentFlow 输出工作区：{error}"),
        })?;

    let source_dir_for_extract = source_dir.clone();
    let archive_path = PathBuf::from(&archive.storage_path);
    let archive_name = archive.original_filename.clone();
    tokio::task::spawn_blocking(move || {
        extract_archive_path_to_directory(&archive_path, &archive_name, &source_dir_for_extract)
    })
    .await
    .map_err(|error| AgentflowWorkspaceError {
        reason_code: "workspace_prepare_failed",
        message: format!("智能审计启动失败：AgentFlow 源码工作区准备任务异常：{error}"),
    })?
    .map_err(|error| AgentflowWorkspaceError {
        reason_code: "workspace_prepare_failed",
        message: format!("智能审计启动失败：项目归档解压失败：{error}"),
    })?;

    Ok(AgentflowWorkspace {
        workspace_dir,
        container_source_dir: shared_workspace_container_path(&workspace_root, &source_dir),
        container_output_dir: shared_workspace_container_path(&workspace_root, &output_dir),
    })
}

fn agentflow_scan_workspace_root() -> PathBuf {
    env_trimmed("SCAN_WORKSPACE_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_SCAN_WORKSPACE_ROOT))
}

fn shared_workspace_container_path(workspace_root: &Path, path: &Path) -> String {
    let relative = path.strip_prefix(workspace_root).unwrap_or(path);
    let relative = relative
        .components()
        .map(|component| component.as_os_str().to_string_lossy())
        .collect::<Vec<_>>()
        .join("/");
    if relative.is_empty() {
        "/workspace".to_string()
    } else {
        format!("/workspace/{relative}")
    }
}

fn safe_path_segment(value: &str) -> String {
    let segment = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    if segment.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        segment
    }
}

fn agentflow_output_dir(state: &AppState, task_id: &str) -> PathBuf {
    state
        .config
        .zip_storage_path
        .join("agentflow")
        .join(task_id)
}

fn build_agentflow_runner_input(
    record: &task_state::AgentTaskRecord,
    project: &StoredProject,
    config: &AppConfig,
    llm_config: &Value,
    project_root: &str,
    output_dir: &str,
) -> Value {
    let audit_scope = record.audit_scope.as_ref();
    let target_files = record
        .target_files
        .clone()
        .filter(|items| !items.is_empty())
        .or_else(|| scope_string_array(audit_scope, "target_files"))
        .unwrap_or_default();
    let exclude_patterns = record
        .exclude_patterns
        .clone()
        .filter(|items| !items.is_empty())
        .or_else(|| scope_string_array(audit_scope, "exclude_patterns"))
        .unwrap_or_default();
    let target_vulnerabilities = record
        .target_vulnerabilities
        .clone()
        .filter(|items| !items.is_empty())
        .or_else(|| scope_string_array(audit_scope, "target_vulnerabilities"))
        .unwrap_or_default();
    let scoped_verification_level = scope_string(audit_scope, "verification_level");
    let verification_level = normalize_agentflow_verification_level(
        record
            .verification_level
            .as_deref()
            .or(scoped_verification_level.as_deref()),
    );
    let prompt_skill = scope_string(audit_scope, "prompt_skill");
    let max_concurrency = config.runner_preflight_max_concurrency.max(1) as u32;

    json!({
        "contract_version": ARGUS_AGENTFLOW_CONTRACT_VERSION,
        "task_id": record.id,
        "project_id": record.project_id,
        "project_root": project_root,
        "target": "container",
        "topology_version": P1_TOPOLOGY_VERSION,
        "audit_scope": {
            "target_files": target_files,
            "exclude_patterns": exclude_patterns,
            "target_vulnerabilities": target_vulnerabilities,
            "verification_level": verification_level,
            "prompt_skill": prompt_skill,
            "extra": {
                "task_name": record.name,
                "task_description": record.description,
                "project_name": project.name,
                "prompt_skill_runtime": audit_scope
                    .and_then(|scope| scope.get("prompt_skill_runtime"))
                    .cloned()
                    .unwrap_or(Value::Null),
            }
        },
        "output_dir": output_dir,
        "llm": {
            "provider": llm_config.get("llmProvider").and_then(Value::as_str).unwrap_or("openai_compatible"),
            "model": llm_config.get("llmModel").and_then(Value::as_str).unwrap_or(""),
            "base_url": llm_config.get("llmBaseUrl").and_then(Value::as_str),
            "api_key_ref": if llm_config.get("llmApiKey").and_then(Value::as_str).unwrap_or("").is_empty() {
                Value::Null
            } else {
                llm_config
                    .get("llmApiKeyRef")
                    .and_then(Value::as_str)
                    .map(|value| Value::String(value.to_string()))
                    .unwrap_or_else(|| Value::String("system_config:llmApiKey".to_string()))
            },
            "agent_kind": derive_agent_kind(llm_config.get("llmProvider").and_then(Value::as_str).unwrap_or("openai_compatible")),
            "wire_api": derive_wire_api(llm_config.get("llmProvider").and_then(Value::as_str).unwrap_or("openai_compatible")),
            "api_key_env": derive_api_key_env(llm_config.get("llmProvider").and_then(Value::as_str).unwrap_or("openai_compatible")),
        },
        "resource_budget": {
            "max_cpu_cores": 2.0,
            "max_memory_mb": 4096,
            "max_duration_seconds": config.agent_timeout_seconds.max(1),
            "max_concurrency": max_concurrency,
        },
        "metadata": {
            "runtime": "agentflow",
            "argus_task_status": record.status,
            "serve_enabled": false,
            "remote_target": false,
            "dynamic_experts": false,
            "credential_source": llm_config.get("credentialSource").and_then(Value::as_str).unwrap_or("app_config"),
        }
    })
}

fn derive_agent_kind(provider: &str) -> &'static str {
    match provider.trim().to_ascii_lowercase().as_str() {
        "anthropic_compatible" | "anthropic" => "claude",
        "kimi_compatible" => "kimi",
        "pi_compatible" => "pi",
        _ => "codex",
    }
}

fn derive_wire_api(provider: &str) -> &'static str {
    match provider.trim().to_ascii_lowercase().as_str() {
        "anthropic_compatible" | "anthropic" => "messages",
        _ => "responses",
    }
}

fn derive_api_key_env(provider: &str) -> &'static str {
    match provider.trim().to_ascii_lowercase().as_str() {
        "anthropic_compatible" | "anthropic" => "ANTHROPIC_API_KEY",
        "kimi_compatible" => "KIMI_API_KEY",
        "pi_compatible" => "PI_API_KEY",
        _ => "OPENAI_API_KEY",
    }
}

fn scope_string_array(scope: Option<&Value>, key: &str) -> Option<Vec<String>> {
    scope
        .and_then(|scope| scope.get(key))
        .and_then(string_array)
        .filter(|items| !items.is_empty())
}

fn scope_string(scope: Option<&Value>, key: &str) -> Option<String> {
    scope?
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn normalize_agentflow_verification_level(value: Option<&str>) -> &'static str {
    match value
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "basic" | "quick" => "basic",
        "strict" | "deep" | "analysis_with_poc" | "analysis_with_poc_plan" => "strict",
        _ => "standard",
    }
}

fn prepare_audit_scope(
    audit_scope: Option<Value>,
    prompt_skill_runtime: Value,
) -> Result<Option<Value>, ApiError> {
    match audit_scope {
        Some(Value::Object(mut object)) => {
            let scope_value = Value::Object(object.clone());
            reject_forbidden_static_input(&scope_value)?;
            object.insert("prompt_skill_runtime".to_string(), prompt_skill_runtime);
            Ok(Some(Value::Object(object)))
        }
        Some(other) => Err(ApiError::BadRequest(format!(
            "audit_scope must be an object when provided, got {}",
            value_kind(&other),
        ))),
        _ => Ok(Some(json!({
            "prompt_skill_runtime": prompt_skill_runtime,
        }))),
    }
}

fn reject_optional_audit_scope(audit_scope: Option<&Value>) -> Result<(), ApiError> {
    match audit_scope {
        Some(value) => reject_forbidden_static_input(value),
        None => Ok(()),
    }
}

fn reject_forbidden_static_input(value: &Value) -> Result<(), ApiError> {
    if let Some(reason) = find_forbidden_static_input(value, "$") {
        return Err(ApiError::BadRequest(format!(
            "{FORBIDDEN_STATIC_INPUT_ERROR}: {reason}"
        )));
    }
    Ok(())
}

fn find_forbidden_static_input(value: &Value, path: &str) -> Option<String> {
    match value {
        Value::Object(object) => {
            for (key, child) in object {
                let normalized_key = key.trim().to_ascii_lowercase();
                let child_path = format!("{path}.{key}");
                if FORBIDDEN_STATIC_INPUT_KEYS.contains(&normalized_key.as_str()) {
                    return Some(format!("field `{child_path}` is not allowed"));
                }
                if matches!(
                    normalized_key.as_str(),
                    "candidate_origin" | "source_engine"
                ) {
                    if let Some(text) = child.as_str() {
                        let normalized_value = text.trim().to_ascii_lowercase();
                        if FORBIDDEN_STATIC_INPUT_VALUES.contains(&normalized_value.as_str()) {
                            return Some(format!(
                                "field `{child_path}` cannot be `{normalized_value}`"
                            ));
                        }
                    }
                }
                if let Some(reason) = find_forbidden_static_input(child, &child_path) {
                    return Some(reason);
                }
            }
            None
        }
        Value::Array(items) => items.iter().enumerate().find_map(|(index, child)| {
            find_forbidden_static_input(child, &format!("{path}[{index}]"))
        }),
        Value::String(text) => {
            let normalized = text.trim().to_ascii_lowercase();
            if normalized.contains("static scan")
                || normalized.contains("static finding")
                || normalized.contains("scanner bootstrap")
            {
                Some(format!("value at `{path}` references `{normalized}`"))
            } else {
                None
            }
        }
        _ => None,
    }
}

fn value_kind(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn agent_task_value(record: &task_state::AgentTaskRecord) -> Value {
    let mut value = serde_json::to_value(record).unwrap_or_else(|_| json!({}));
    if let Some(object) = value.as_object_mut() {
        let mut critical = 0i64;
        let mut high = 0i64;
        let mut medium = 0i64;
        let mut low = 0i64;
        let mut info = 0i64;
        let mut pending = 0i64;
        let mut verified = 0i64;
        let mut false_positive = 0i64;

        for finding in &record.findings {
            match normalized_token(&finding.severity).as_str() {
                "critical" => critical += 1,
                "high" => high += 1,
                "medium" => medium += 1,
                "low" => low += 1,
                _ => info += 1,
            }
            match finding_export_status(finding) {
                "verified" => verified += 1,
                "false_positive" => false_positive += 1,
                _ => pending += 1,
            }
        }
        let total_count = record.findings.len() as i64;
        object.insert(
            "defect_summary".to_string(),
            json!({
                "scope": "all_findings",
                "total_count": total_count,
                "severity_counts": {
                    "critical": critical,
                    "high": high,
                    "medium": medium,
                    "low": low,
                    "info": info,
                },
                "status_counts": {
                    "pending": pending,
                    "verified": verified,
                    "false_positive": false_positive,
                },
            }),
        );
    }
    value
}

fn agent_event_value(record: &task_state::AgentEventRecord) -> Value {
    serde_json::to_value(record).unwrap_or_else(|_| json!({}))
}

fn agent_finding_value(record: &task_state::AgentFindingRecord) -> Value {
    serde_json::to_value(record).unwrap_or_else(|_| json!({}))
}

fn checkpoint_summary_value(record: &task_state::AgentCheckpointRecord) -> Value {
    serde_json::to_value(record).unwrap_or_else(|_| json!({}))
}

fn checkpoint_detail_value(record: &task_state::AgentCheckpointRecord) -> Value {
    serde_json::to_value(record).unwrap_or_else(|_| json!({}))
}

fn push_agent_event(
    record: &mut task_state::AgentTaskRecord,
    event_type: &str,
    phase: Option<&str>,
    message: Option<&str>,
    metadata: Option<Value>,
) {
    let sequence = record.events.len() as i64 + 1;
    record.events.push(task_state::AgentEventRecord {
        id: Uuid::new_v4().to_string(),
        task_id: record.id.clone(),
        event_type: event_type.to_string(),
        phase: phase.map(ToString::to_string),
        message: message.map(ToString::to_string),
        tool_name: None,
        tool_input: None,
        tool_output: None,
        tool_duration_ms: None,
        finding_id: None,
        tokens_used: None,
        metadata,
        role: phase.map(ToString::to_string),
        visibility: Some("user".to_string()),
        correlation_id: Some(record.id.clone()),
        topology_version: record.topology_version.clone(),
        source_node_id: Some(format!("root-{}", record.id)),
        sequence,
        timestamp: now_rfc3339(),
    });
}

fn agent_event_is_user_visible(event: &task_state::AgentEventRecord) -> bool {
    !matches!(
        event.visibility.as_deref(),
        Some("internal" | "AGENTS_ONLY" | "agents_only")
    )
}

fn push_checkpoint(
    record: &mut task_state::AgentTaskRecord,
    checkpoint_type: &str,
    name: Option<&str>,
) {
    record.checkpoints.push(task_state::AgentCheckpointRecord {
        id: Uuid::new_v4().to_string(),
        task_id: record.id.clone(),
        agent_id: format!("root-{}", record.id),
        agent_name: "RustAgentRoot".to_string(),
        agent_type: "root".to_string(),
        parent_agent_id: None,
        iteration: record.total_iterations.max(0),
        status: record.status.clone(),
        total_tokens: record.tokens_used,
        tool_calls: record.tool_calls_count,
        findings_count: record.findings_count,
        checkpoint_type: checkpoint_type.to_string(),
        checkpoint_name: name.map(ToString::to_string),
        created_at: Some(now_rfc3339()),
        state_data: json!({
            "status": record.status,
            "progress_percentage": record.progress_percentage,
        }),
        metadata: Some(json!({"source": "rust-backend"})),
    });
}

fn required_string(payload: &Value, key: &str) -> Result<String, ApiError> {
    payload
        .get(key)
        .and_then(|value| value.as_str())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
        .ok_or_else(|| ApiError::BadRequest(format!("missing required field: {key}")))
}

fn optional_string(payload: &Value, key: &str) -> Option<String> {
    payload
        .get(key)
        .and_then(|value| value.as_str())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn string_array(value: &Value) -> Option<Vec<String>> {
    value.as_array().map(|items| {
        items
            .iter()
            .filter_map(|item| item.as_str().map(ToString::to_string))
            .collect::<Vec<_>>()
    })
}

fn event_stream_response(body: String) -> Response<Body> {
    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    response
}

fn duration_seconds(started_at: Option<&str>, completed_at: Option<&str>) -> Option<f64> {
    let start = started_at.and_then(parse_timestamp);
    let end = completed_at.and_then(parse_timestamp);
    match (start, end) {
        (Some(start), Some(end)) => Some((end - start).as_seconds_f64()),
        _ => None,
    }
}

fn parse_timestamp(value: &str) -> Option<OffsetDateTime> {
    OffsetDateTime::parse(value, &Rfc3339).ok()
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

fn minimal_pdf_bytes(message: &str) -> Vec<u8> {
    format!(
        "%PDF-1.4\n1 0 obj<<>>endobj\n2 0 obj<< /Length {} >>stream\n{}\nendstream\nendobj\ntrailer<<>>\n%%EOF\n",
        message.len(),
        message
    )
    .into_bytes()
}

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(error.to_string())
}

async fn ensure_intelligent_audit_llm_ready(state: &AppState) -> Result<Value, ApiError> {
    let stored = system_config::load_current(state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| {
            ApiError::BadRequest(
                "智能审计启动失败：请先在扫描配置 > 智能引擎中保存并测试 LLM 配置。".to_string(),
            )
        })?;
    let selected = crate::routes::llm_config_set::selected_enabled_runtime(
        &stored.llm_config_json,
        &stored.other_config_json,
        state.config.as_ref(),
    )
    .map_err(|error| ApiError::BadRequest(error.message))?;
    let outcome = test_llm_generation(&state.http_client, &selected.runtime)
        .await
        .map_err(|error| ApiError::BadRequest(error.message))?;
    let mut envelope = crate::routes::llm_config_set::mark_row_preflight(
        &stored.llm_config_json,
        &selected.row_id,
        "passed",
        None,
        Some("启动前预检通过"),
        Some(&outcome.fingerprint),
    );
    envelope = crate::routes::llm_config_set::set_latest_preflight_run(
        &envelope,
        vec![selected.row_id.clone()],
        Some(selected.row_id),
        Some(outcome.fingerprint.clone()),
    );
    let _ = system_config::save_current(
        state,
        envelope,
        stored.other_config_json,
        outcome.metadata(),
    )
    .await
    .map_err(internal_error)?;
    Ok(outcome.metadata())
}

#[cfg(test)]
mod tests {
    use super::{
        finalize_agent_task_failed, finalize_agent_task_forbidden_static_input,
        reject_forbidden_static_input, task_state, AGENTFLOW_RUNTIME_UNCONFIGURED_ERROR,
    };
    use serde_json::json;

    #[test]
    fn finalize_agentflow_runtime_failure_marks_task_failed_and_surfaces_error() {
        let mut record = task_state::AgentTaskRecord {
            id: "task-1".to_string(),
            project_id: "project-1".to_string(),
            name: Some("demo".to_string()),
            description: Some("demo task".to_string()),
            task_type: "agent_audit".to_string(),
            status: "pending".to_string(),
            current_phase: Some("created".to_string()),
            current_step: Some("waiting".to_string()),
            total_files: 0,
            indexed_files: 0,
            analyzed_files: 0,
            files_with_findings: 0,
            total_chunks: 0,
            findings_count: 0,
            verified_count: 0,
            false_positive_count: 0,
            total_iterations: 1,
            tool_calls_count: 0,
            tokens_used: 0,
            critical_count: 0,
            high_count: 0,
            medium_count: 0,
            low_count: 0,
            verified_critical_count: 0,
            verified_high_count: 0,
            verified_medium_count: 0,
            verified_low_count: 0,
            quality_score: 0.0,
            security_score: Some(0.0),
            created_at: "2026-01-01T00:00:00Z".to_string(),
            started_at: Some("2026-01-01T00:00:01Z".to_string()),
            completed_at: None,
            progress_percentage: 0.0,
            audit_scope: Some(json!({})),
            target_vulnerabilities: None,
            verification_level: None,
            tool_evidence_protocol: None,
            exclude_patterns: None,
            target_files: None,
            error_message: None,
            report: None,
            runtime: Some("agentflow".to_string()),
            run_id: None,
            topology_version: Some("p1-static".to_string()),
            input_digest: None,
            artifact_index: None,
            report_snapshot: None,
            feedback_bundle: None,
            diagnostics: None,
            events: Vec::new(),
            findings: Vec::new(),
            checkpoints: Vec::new(),
            agent_tree: Vec::new(),
        };

        finalize_agent_task_failed(
            &mut record,
            "2026-01-01T00:00:02Z",
            AGENTFLOW_RUNTIME_UNCONFIGURED_ERROR,
        );

        assert_eq!(record.status, "failed");
        assert_eq!(record.current_phase.as_deref(), Some("failed"));
        assert_eq!(
            record.current_step.as_deref(),
            Some("agentflow runtime failed")
        );
        assert_eq!(
            record.error_message.as_deref(),
            Some(AGENTFLOW_RUNTIME_UNCONFIGURED_ERROR)
        );
        assert_eq!(record.agent_tree[0]["status"], "failed");
        assert_eq!(
            record.agent_tree[0]["result_summary"],
            AGENTFLOW_RUNTIME_UNCONFIGURED_ERROR
        );
        assert!(record
            .events
            .iter()
            .any(|event| event.event_type == "task_error"));
    }

    #[test]
    fn forbidden_static_input_scan_rejects_nested_static_candidates() {
        let payload = json!({
            "audit_scope": {
                "targets": [{
                    "path": "src/main.py",
                    "candidate_origin": "opengrep"
                }]
            }
        });

        let error = reject_forbidden_static_input(&payload).expect_err("opengrep source rejected");
        assert!(error.to_string().contains("candidate_origin"));
        assert!(error.to_string().contains("opengrep"));
    }

    #[test]
    fn forbidden_static_input_finalizer_records_dedicated_event_and_checkpoint() {
        let mut record = task_state::AgentTaskRecord {
            id: "task-1".to_string(),
            project_id: "project-1".to_string(),
            name: Some("demo".to_string()),
            description: Some("demo task".to_string()),
            task_type: "agent_audit".to_string(),
            status: "pending".to_string(),
            current_phase: Some("created".to_string()),
            current_step: Some("waiting".to_string()),
            total_iterations: 1,
            created_at: "2026-01-01T00:00:00Z".to_string(),
            audit_scope: Some(json!({"candidate_findings": ["finding-1"]})),
            ..Default::default()
        };

        finalize_agent_task_forbidden_static_input(
            &mut record,
            "2026-01-01T00:00:02Z",
            "forbidden static input",
        );

        assert_eq!(record.status, "failed");
        assert_eq!(
            record.current_step.as_deref(),
            Some("forbidden static input")
        );
        assert!(record
            .events
            .iter()
            .any(|event| event.event_type == "forbidden_static_input"));
        assert!(record.checkpoints.iter().any(|checkpoint| {
            checkpoint.checkpoint_name.as_deref() == Some("forbidden_static_input")
        }));
    }
}
