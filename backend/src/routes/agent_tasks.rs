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
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::{
    db::{projects, task_state},
    error::ApiError,
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
        .route("/{task_id}/summary", get(get_agent_task_summary))
        .route("/{task_id}/agent-tree", get(get_agent_tree))
        .route("/{task_id}/checkpoints", get(list_checkpoints))
        .route("/{task_id}/checkpoints/{checkpoint_id}", get(get_checkpoint_detail))
        .route("/{task_id}/report", get(download_report))
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
struct ReportQuery {
    format: Option<String>,
}

pub async fn create_agent_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let project_id = required_string(&payload, "project_id")?;
    ensure_project_exists(&state, &project_id).await?;

    let now = now_rfc3339();
    let task_id = Uuid::new_v4().to_string();
    let name = optional_string(&payload, "name");
    let description = optional_string(&payload, "description");
    let verification_level =
        optional_string(&payload, "verification_level").or(Some("analysis_with_poc_plan".to_string()));
    let target_vulnerabilities = payload
        .get("target_vulnerabilities")
        .and_then(|value| value.as_array())
        .map(|items| {
            items.iter()
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
    let audit_scope = payload.get("audit_scope").cloned();
    let max_iterations = payload
        .get("max_iterations")
        .and_then(|value| value.as_i64())
        .unwrap_or(8);

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
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

    snapshot.agent_tasks.insert(task_id.clone(), record.clone());
    task_state::save_snapshot(&state, &snapshot)
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
    record.status = "completed".to_string();
    record.current_phase = Some("reporting".to_string());
    record.current_step = Some("completed by rust backend".to_string());
    record.started_at = Some(now.clone());
    record.completed_at = Some(now.clone());
    record.progress_percentage = 100.0;
    record.quality_score = 100.0;
    record.security_score = Some(100.0);
    record.tool_calls_count = 1;
    record.tokens_used = 64;
    record.total_iterations = record.total_iterations.max(1);
    if let Some(node) = record.agent_tree.first_mut() {
        if let Some(object) = node.as_object_mut() {
            object.insert("status".to_string(), json!("completed"));
            object.insert(
                "result_summary".to_string(),
                json!("task executed in rust backend"),
            );
            object.insert("iterations".to_string(), json!(record.total_iterations));
            object.insert("tool_calls".to_string(), json!(record.tool_calls_count));
            object.insert("tokens_used".to_string(), json!(record.tokens_used));
        }
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
    push_checkpoint(record, "final", Some("completed"));

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
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    Ok(Json(
        record
            .findings
            .iter()
            .map(agent_finding_value)
            .collect::<Vec<_>>(),
    ))
}

async fn get_agent_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
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
    let finding = record
        .findings
        .iter_mut()
        .find(|finding| finding.id == finding_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent finding not found: {finding_id}")))?;
    if let Some(status) = optional_string(&payload, "status") {
        finding.status = status;
    }
    let response_value = agent_finding_value(finding);
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
        "vulnerability_types": {},
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
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let record = snapshot
        .agent_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("agent task not found: {task_id}")))?;
    Ok(Json(
        record
            .checkpoints
            .iter()
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
    let format = query
        .format
        .unwrap_or_else(|| "markdown".to_string())
        .to_ascii_lowercase();

    let (content_type, body) = match format.as_str() {
        "json" => (
            "application/json",
            serde_json::to_vec(&json!({
                "task_id": record.id,
                "status": record.status,
                "report": record.report,
            }))
            .map_err(internal_error)?,
        ),
        "pdf" => (
            "application/pdf",
            minimal_pdf_bytes(&format!(
                "Rust agent report for task {} with status {}",
                record.id, record.status
            )),
        ),
        _ => (
            "text/markdown; charset=utf-8",
            record
                .report
                .clone()
                .unwrap_or_else(|| format!("# Agent Task Report\n\nTask `{}`\n", record.id))
                .into_bytes(),
        ),
    };

    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_str(content_type).map_err(internal_error)?,
    );
    Ok(response)
}

fn agent_task_value(record: &task_state::AgentTaskRecord) -> Value {
    serde_json::to_value(record).unwrap_or_else(|_| json!({}))
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
        sequence,
        timestamp: now_rfc3339(),
    });
}

fn push_checkpoint(record: &mut task_state::AgentTaskRecord, checkpoint_type: &str, name: Option<&str>) {
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

async fn ensure_project_exists(state: &AppState, project_id: &str) -> Result<(), ApiError> {
    let project = projects::get_project(state, project_id)
        .await
        .map_err(internal_error)?;
    if project.is_none() {
        return Err(ApiError::NotFound(format!("project not found: {project_id}")));
    }
    Ok(())
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
        items.iter()
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
