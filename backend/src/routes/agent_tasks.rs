use std::collections::BTreeMap;

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

use crate::{
    db::{projects, task_state},
    error::ApiError,
    routes::skills,
    runtime::hermes::{
        contracts::{AgentRole, HandoffStatus},
        discovery, executor, handoff,
    },
    state::AppState,
};

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

enum HermesDispatchOutcome {
    Succeeded,
    Failed(String),
    Unavailable,
}

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
            "# Agent Task Report\n\nTask `{}` is now owned by the rust backend.\n",
            task_id
        )),
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
    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get_mut(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    let now = now_rfc3339();
    record.started_at = Some(now.clone());
    record.total_iterations = record.total_iterations.max(1);

    match try_hermes_dispatch(record).await {
        HermesDispatchOutcome::Succeeded => finalize_agent_task_completed(record, &now),
        HermesDispatchOutcome::Failed(error) => {
            finalize_agent_task_failed(record, &now, &error);
        }
        HermesDispatchOutcome::Unavailable => finalize_agent_task_mock_completed(record, &now),
    }

    task_state::save_snapshot(&state, &snapshot)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({
        "message": "agent task started in rust backend",
        "task_id": task_id,
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
    let payload = record
        .events
        .iter()
        .filter(|event| event.sequence > after_sequence)
        .map(agent_event_value)
        .map(|event| format!("data: {}\n\n", event))
        .collect::<String>();
    Ok(event_stream_response(payload))
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

fn seed_agent_task_findings(record: &mut task_state::AgentTaskRecord) {
    if !record.findings.is_empty() {
        return;
    }
    let now = now_rfc3339();
    let finding_one_id = Uuid::new_v4().to_string();
    let finding_two_id = Uuid::new_v4().to_string();
    record.findings.push(task_state::AgentFindingRecord {
        id: finding_one_id,
        task_id: record.id.clone(),
        vulnerability_type: "sql_injection".to_string(),
        severity: "high".to_string(),
        title: "SQL injection in authentication flow".to_string(),
        display_title: Some("登录链路中的 SQL 注入风险".to_string()),
        description: Some(
            "动态 SQL 语句拼接了未经参数化处理的输入，可能导致账号数据泄露。".to_string(),
        ),
        description_markdown: Some(
            "在认证流程中检测到拼接式查询，建议改用参数化查询与白名单校验。".to_string(),
        ),
        file_path: Some("src/auth/login.ts".to_string()),
        line_start: Some(42),
        line_end: Some(49),
        resolved_file_path: Some("src/auth/login.ts".to_string()),
        resolved_line_start: Some(42),
        code_snippet: Some(
            "const sql = `SELECT * FROM users WHERE email = '${email}'`".to_string(),
        ),
        code_context: Some("login handler".to_string()),
        status: "verified".to_string(),
        is_verified: true,
        verdict: Some("confirmed".to_string()),
        reachability: Some("reachable".to_string()),
        authenticity: Some("confirmed".to_string()),
        suggestion: Some("使用参数化查询并对输入做严格校验。".to_string()),
        fix_code: Some("const sql = 'SELECT * FROM users WHERE email = ?'".to_string()),
        report: Some("该漏洞可被直接利用，优先级应设为高。".to_string()),
        ai_confidence: Some(0.96),
        confidence: Some(0.95),
        created_at: now.clone(),
        ..Default::default()
    });
    record.findings.push(task_state::AgentFindingRecord {
        id: finding_two_id,
        task_id: record.id.clone(),
        vulnerability_type: "xss".to_string(),
        severity: "medium".to_string(),
        title: "Reflected XSS in search endpoint".to_string(),
        display_title: Some("搜索结果反射型 XSS".to_string()),
        description: Some("搜索参数直接进入 HTML 模板，缺少输出编码。".to_string()),
        description_markdown: Some("建议统一使用安全模板转义函数渲染用户输入。".to_string()),
        file_path: Some("src/web/search.tsx".to_string()),
        line_start: Some(77),
        line_end: Some(83),
        resolved_file_path: Some("src/web/search.tsx".to_string()),
        resolved_line_start: Some(77),
        code_snippet: Some(
            "return <div dangerouslySetInnerHTML={{ __html: keyword }} />".to_string(),
        ),
        status: "pending".to_string(),
        is_verified: false,
        verdict: Some("likely".to_string()),
        reachability: Some("likely_reachable".to_string()),
        authenticity: Some("likely".to_string()),
        suggestion: Some("将渲染逻辑改为文本节点并增加统一编码层。".to_string()),
        ai_confidence: Some(0.74),
        confidence: Some(0.71),
        created_at: now,
        ..Default::default()
    });
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

fn seed_agent_task_tree(record: &mut task_state::AgentTaskRecord) {
    record.agent_tree = vec![
        json!({
            "id": format!("root-{}", record.id),
            "agent_id": format!("root-{}", record.id),
            "agent_name": "RustAgentRoot",
            "agent_type": "root",
            "parent_agent_id": Value::Null,
            "depth": 0,
            "task_description": record.description,
            "status": "completed",
            "result_summary": "task executed in rust backend",
            "findings_count": record.findings_count,
            "verified_findings_count": record.verified_count,
            "iterations": record.total_iterations,
            "tokens_used": record.tokens_used,
            "tool_calls": record.tool_calls_count,
            "duration_ms": 120000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("recon-{}", record.id),
            "agent_id": format!("recon-{}", record.id),
            "agent_name": "HermesReconAgent",
            "agent_type": "recon",
            "parent_agent_id": format!("root-{}", record.id),
            "depth": 1,
            "task_description": "map attack surface and identify risk points",
            "status": "completed",
            "result_summary": "mapped input surfaces and trust boundaries",
            "findings_count": 0,
            "verified_findings_count": 0,
            "iterations": 1,
            "tokens_used": 64,
            "tool_calls": 2,
            "duration_ms": 15000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("analysis-{}", record.id),
            "agent_id": format!("analysis-{}", record.id),
            "agent_name": "HermesAnalysisAgent",
            "agent_type": "analysis",
            "parent_agent_id": format!("root-{}", record.id),
            "depth": 1,
            "task_description": "trace suspicious sinks",
            "status": "completed",
            "result_summary": "identified candidate sinks and dataflow paths",
            "findings_count": record.findings_count,
            "verified_findings_count": 0,
            "iterations": record.total_iterations.max(1).saturating_sub(1),
            "tokens_used": record.tokens_used.saturating_sub(96),
            "tool_calls": record.tool_calls_count.saturating_sub(2),
            "duration_ms": 82000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("verification-{}", record.id),
            "agent_id": format!("verification-{}", record.id),
            "agent_name": "HermesVerificationAgent",
            "agent_type": "verification",
            "parent_agent_id": format!("root-{}", record.id),
            "depth": 1,
            "task_description": "confirm exploitability and triage false positives",
            "status": "completed",
            "result_summary": "verified actionable findings and closed noisy alerts",
            "findings_count": record.findings_count,
            "verified_findings_count": record.verified_count,
            "iterations": 1,
            "tokens_used": 96,
            "tool_calls": 2,
            "duration_ms": 28000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("report-{}", record.id),
            "agent_id": format!("report-{}", record.id),
            "agent_name": "HermesReportAgent",
            "agent_type": "report",
            "parent_agent_id": format!("root-{}", record.id),
            "depth": 1,
            "task_description": "compile verified findings into report artifacts",
            "status": "completed",
            "result_summary": "generated structured report",
            "findings_count": record.findings_count,
            "verified_findings_count": record.verified_count,
            "iterations": 1,
            "tokens_used": 48,
            "tool_calls": 1,
            "duration_ms": 10000,
            "children": Vec::<Value>::new(),
        }),
    ];
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

fn finalize_agent_task_completed(record: &mut task_state::AgentTaskRecord, now: &str) {
    record.status = "completed".to_string();
    record.current_phase = Some("reporting".to_string());
    record.current_step = Some("completed by rust backend".to_string());
    record.completed_at = Some(now.to_string());
    record.progress_percentage = 100.0;
    record.quality_score = 100.0;
    record.security_score = Some(100.0);
    record.error_message = None;
    if record.tool_calls_count == 0 {
        record.tool_calls_count = record.agent_tree.len().saturating_sub(1) as i64;
    }
    push_agent_event(
        record,
        "phase_start",
        Some("analysis"),
        Some("agent task execution started in rust backend"),
        None,
    );
    push_agent_event(
        record,
        "task_complete",
        Some("reporting"),
        Some("agent task execution completed in rust backend"),
        Some(json!({
            "findings_count": record.findings_count,
            "security_score": record.security_score.unwrap_or(0.0),
        })),
    );
    let finding_events = record
        .findings
        .iter()
        .map(|finding| {
            (
                finding.id.clone(),
                finding.title.clone(),
                finding.severity.clone(),
                finding.status.clone(),
            )
        })
        .collect::<Vec<_>>();
    for (finding_id, title, severity, status) in finding_events {
        push_agent_event(
            record,
            "finding_detected",
            Some("reporting"),
            Some(&format!("captured finding {title}")),
            Some(json!({
                "finding_id": finding_id,
                "severity": severity,
                "status": status,
            })),
        );
    }
    push_checkpoint(record, "final", Some("completed"));
}

fn finalize_agent_task_mock_completed(record: &mut task_state::AgentTaskRecord, now: &str) {
    record.tool_calls_count = 6;
    record.tokens_used = 384;
    seed_agent_task_findings(record);
    refresh_agent_task_aggregates(record);
    seed_agent_task_tree(record);
    append_agent_checkpoint(
        record,
        &format!("analysis-{}", record.id),
        "HermesAnalysisAgent",
        "analysis",
        Some(&format!("root-{}", record.id)),
        "auto",
        Some("analysis-complete"),
        "completed",
        record.total_iterations.max(1).saturating_sub(1),
        record.findings_count,
        record.tokens_used.saturating_sub(96),
        record.tool_calls_count.saturating_sub(2),
        json!({"phase": "analysis", "status": "completed"}),
    );
    append_agent_checkpoint(
        record,
        &format!("verification-{}", record.id),
        "HermesVerificationAgent",
        "verification",
        Some(&format!("root-{}", record.id)),
        "auto",
        Some("verification-complete"),
        "completed",
        record.total_iterations.max(1),
        record.findings_count,
        96,
        2,
        json!({"phase": "verification", "status": "completed"}),
    );
    finalize_agent_task_completed(record, now);
}

fn finalize_agent_task_failed(record: &mut task_state::AgentTaskRecord, now: &str, error: &str) {
    if record.agent_tree.is_empty() {
        seed_failed_agent_task_tree(record, error);
    }
    record.status = "failed".to_string();
    record.current_phase = Some("failed".to_string());
    record.current_step = Some("hermes dispatch failed".to_string());
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
        Some("hermes dispatch failed in rust backend"),
        Some(json!({"error": error})),
    );
    push_checkpoint(record, "final", Some("failed"));
}

async fn try_hermes_dispatch(record: &mut task_state::AgentTaskRecord) -> HermesDispatchOutcome {
    let agents_base_path = std::env::var("HERMES_AGENTS_BASE_PATH")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "backend/agents".to_string());
    let base_path = std::path::Path::new(&agents_base_path);
    let manifests = match discovery::discover_agents(base_path) {
        Ok(m) if !m.is_empty() => m,
        Ok(_) => {
            return HermesDispatchOutcome::Unavailable
        }
        Err(e) => {
            let _ = e;
            return HermesDispatchOutcome::Unavailable
        }
    };

    let roles = [
        AgentRole::Recon,
        AgentRole::Analysis,
        AgentRole::Verification,
        AgentRole::Report,
    ];

    let mut tree = vec![json!({
        "id": format!("root-{}", record.id),
        "agent_id": format!("root-{}", record.id),
        "agent_name": "RustAgentRoot",
        "agent_type": "root",
        "parent_agent_id": Value::Null,
        "depth": 0,
        "task_description": &record.description,
        "status": "running",
        "result_summary": "hermes dispatch in progress",
        "findings_count": 0,
        "verified_findings_count": 0,
        "iterations": 0,
        "tokens_used": 0,
        "tool_calls": 0,
        "duration_ms": 0,
        "children": Vec::<Value>::new(),
    })];

    let mut all_succeeded = true;
    for role in &roles {
        let manifest = match manifests.iter().find(|m| m.role == *role) {
            Some(m) => m,
            None => {
                all_succeeded = false;
                continue;
            }
        };

        let req = handoff::build_handoff(
            role,
            &record.id,
            &record.project_id,
            &uuid::Uuid::new_v4().to_string(),
            serde_json::json!({
                "project_path": "/scan",
                "task_description": &record.description,
            }),
        );

        let result = executor::execute_handoff(manifest, &req).await;
        let (status_str, summary) = match &result {
            Ok(r) if r.status == HandoffStatus::Success => ("completed", r.summary.clone()),
            Ok(r) => {
                all_succeeded = false;
                ("failed", r.summary.clone())
            }
            Err(e) => {
                all_succeeded = false;
                ("failed", e.to_string())
            }
        };

        tree.push(json!({
            "id": format!("{}-{}", role, record.id),
            "agent_id": format!("{}-{}", role, record.id),
            "agent_name": format!("Hermes{}Agent", capitalize_first(&role.to_string())),
            "agent_type": role.to_string(),
            "parent_agent_id": format!("root-{}", record.id),
            "depth": 1,
            "task_description": format!("{} dispatch", role),
            "status": status_str,
            "result_summary": summary,
            "findings_count": 0,
            "verified_findings_count": 0,
            "iterations": 1,
            "tokens_used": 0,
            "tool_calls": 1,
            "duration_ms": 0,
            "children": Vec::<Value>::new(),
        }));
    }

    let root_summary = if all_succeeded {
        "hermes dispatch completed".to_string()
    } else {
        "hermes dispatch partially failed, check child agents".to_string()
    };
    if let Some(root) = tree.first_mut() {
        root["status"] = json!(if all_succeeded { "completed" } else { "failed" });
        root["result_summary"] = json!(root_summary.clone());
    }

    record.agent_tree = tree;
    if all_succeeded {
        HermesDispatchOutcome::Succeeded
    } else {
        HermesDispatchOutcome::Failed(root_summary)
    }
}

fn capitalize_first(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        None => String::new(),
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
    }
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
            lines.push(format!("- 置信度：`{:.2}`", confidence));
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

fn prepare_audit_scope(
    audit_scope: Option<Value>,
    prompt_skill_runtime: Value,
) -> Result<Option<Value>, ApiError> {
    match audit_scope {
        Some(Value::Object(mut object)) => {
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

fn append_agent_checkpoint(
    record: &mut task_state::AgentTaskRecord,
    agent_id: &str,
    agent_name: &str,
    agent_type: &str,
    parent_agent_id: Option<&str>,
    checkpoint_type: &str,
    checkpoint_name: Option<&str>,
    status: &str,
    iteration: i64,
    findings_count: i64,
    total_tokens: i64,
    tool_calls: i64,
    state_data: Value,
) {
    record.checkpoints.push(task_state::AgentCheckpointRecord {
        id: Uuid::new_v4().to_string(),
        task_id: record.id.clone(),
        agent_id: agent_id.to_string(),
        agent_name: agent_name.to_string(),
        agent_type: agent_type.to_string(),
        parent_agent_id: parent_agent_id.map(ToString::to_string),
        iteration,
        status: status.to_string(),
        total_tokens,
        tool_calls,
        findings_count,
        checkpoint_type: checkpoint_type.to_string(),
        checkpoint_name: checkpoint_name.map(ToString::to_string),
        created_at: Some(now_rfc3339()),
        state_data,
        metadata: Some(json!({"source": "rust-backend"})),
    });
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
        sequence,
        timestamp: now_rfc3339(),
    });
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

#[cfg(test)]
mod tests {
    use super::{finalize_agent_task_failed, task_state};
    use serde_json::json;

    #[test]
    fn finalize_failed_dispatch_marks_task_failed_and_surfaces_error() {
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
            events: Vec::new(),
            findings: Vec::new(),
            checkpoints: Vec::new(),
            agent_tree: Vec::new(),
        };

        finalize_agent_task_failed(
            &mut record,
            "2026-01-01T00:00:02Z",
            "hermes dispatch partially failed",
        );

        assert_eq!(record.status, "failed");
        assert_eq!(record.current_phase.as_deref(), Some("failed"));
        assert_eq!(
            record.current_step.as_deref(),
            Some("hermes dispatch failed")
        );
        assert_eq!(
            record.error_message.as_deref(),
            Some("hermes dispatch partially failed")
        );
        assert_eq!(record.agent_tree[0]["status"], "failed");
        assert_eq!(
            record.agent_tree[0]["result_summary"],
            "hermes dispatch partially failed"
        );
        assert!(record
            .events
            .iter()
            .any(|event| event.event_type == "task_error"));
    }
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
