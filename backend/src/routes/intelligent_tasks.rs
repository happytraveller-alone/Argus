use async_stream::stream;
use axum::{
    extract::{Path, Query, State},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse,
    },
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::broadcast;

use crate::{
    db::{intelligent_task_state, projects},
    error::ApiError,
    runtime::intelligent::{
        audit_pipeline::types::AuditConfigOverride,
        types::{IntelligentTaskFinding, IntelligentTaskRecord},
    },
    state::AppState,
};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CreateIntelligentTaskRequest {
    project_id: String,
    #[serde(default)]
    audit_config_override: Option<AuditConfigOverride>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ListQuery {
    limit: Option<usize>,
    skip: Option<usize>,
    project_id: Option<String>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(list_tasks).post(create_task))
        .route("/{task_id}", get(get_task).delete(delete_task))
        .route("/{task_id}/cancel", post(cancel_task))
        .route("/{task_id}/stream", get(stream_task))
        .route(
            "/{task_id}/findings/{finding_id}/verdict",
            post(set_finding_verdict),
        )
}

async fn create_task(
    State(state): State<AppState>,
    Json(payload): Json<CreateIntelligentTaskRequest>,
) -> Result<Json<Value>, ApiError> {
    if payload.project_id.trim().is_empty() {
        return Err(ApiError::BadRequest("projectId is required".to_string()));
    }

    // Security M1: validate user-supplied bounds before submission.
    if let Some(override_cfg) = &payload.audit_config_override {
        if let Err(msg) = override_cfg.validate() {
            return Err(ApiError::BadRequest(msg.to_string()));
        }
    }

    let record = state
        .intelligent_task_manager
        .submit(
            state.clone(),
            payload.project_id,
            payload.audit_config_override,
        )
        .await
        .map_err(internal_error)?;

    Ok(Json(json!({
        "taskId": record.task_id,
        "projectId": record.project_id,
        "status": record.status,
        "createdAt": record.created_at,
        "links": {
            "self": format!("/api/v1/intelligent-tasks/{}", record.task_id)
        }
    })))
}

async fn list_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<IntelligentTaskRecord>>, ApiError> {
    let limit = query.limit.unwrap_or(50).clamp(1, 200);
    let skip = query.skip.unwrap_or(0);
    let records = match query.project_id.as_deref() {
        Some(project_id) if !project_id.trim().is_empty() => {
            intelligent_task_state::list_records_by_project(&state, project_id, skip, limit)
                .await
                .map_err(internal_error)?
        }
        _ => intelligent_task_state::list_records(&state, skip, limit)
            .await
            .map_err(internal_error)?,
    };
    Ok(Json(bind_project_names(&state, records).await?))
}

async fn get_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<IntelligentTaskRecord>, ApiError> {
    let record = intelligent_task_state::get_record(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("Intelligent task not found: {task_id}")))?;
    Ok(Json(bind_project_name(&state, record).await?))
}

async fn cancel_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<IntelligentTaskRecord>, ApiError> {
    let record = state
        .intelligent_task_manager
        .cancel(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("Intelligent task not found: {task_id}")))?;
    Ok(Json(bind_project_name(&state, record).await?))
}

async fn delete_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    let record = intelligent_task_state::get_record(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("Intelligent task not found: {task_id}")))?;
    if !record.status.is_terminal() {
        return Err(ApiError::Conflict(
            "cannot delete non-terminal intelligent task".to_string(),
        ));
    }

    let deleted = intelligent_task_state::delete_record(&state, &task_id)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({
        "deleted": deleted.is_some(),
        "taskId": task_id,
        "terminalStatus": record.status,
    })))
}

async fn stream_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> impl IntoResponse {
    // Subscribe to broadcast FIRST to avoid race window between replay and live events.
    let live_rx: Option<broadcast::Receiver<_>> =
        state.intelligent_task_manager.subscribe(&task_id).await;

    // Load persisted record (may be None if task doesn't exist yet, treat as empty replay).
    let persisted = intelligent_task_state::get_record(&state, &task_id)
        .await
        .unwrap_or(None);

    let replay_events: Vec<_> = persisted
        .as_ref()
        .map(|r| r.event_log.clone())
        .unwrap_or_default();
    let is_terminal = persisted
        .as_ref()
        .map(|r| r.status.is_terminal())
        .unwrap_or(false);
    let replay_count = replay_events.len();

    let output = stream! {
        // Replay all persisted events.
        for evt in replay_events {
            if let Ok(data) = serde_json::to_string(&evt) {
                yield Ok::<Event, std::convert::Infallible>(Event::default().data(data));
            }
        }

        // If task was already terminal when we loaded it, close the stream.
        if is_terminal {
            return;
        }

        // If no broadcast receiver (task not live), nothing more to send.
        let Some(mut rx) = live_rx else {
            return;
        };

        // Drain live broadcast, skipping the first `replay_count` events that
        // were already covered by the replay above.
        let mut skipped = 0usize;
        loop {
            match rx.recv().await {
                Ok(evt) => {
                    if skipped < replay_count {
                        skipped += 1;
                        continue;
                    }
                    if let Ok(data) = serde_json::to_string(&evt) {
                        yield Ok(Event::default().data(data));
                    }
                }
                Err(broadcast::error::RecvError::Closed) => break,
                Err(broadcast::error::RecvError::Lagged(n)) => {
                    // Missed some events due to slow consumer; adjust skip counter.
                    skipped = skipped.saturating_sub(n as usize);
                }
            }
        }
    };

    Sse::new(output).keep_alive(KeepAlive::default())
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SetVerdictRequest {
    verdict: Option<String>,
}

async fn set_finding_verdict(
    State(state): State<AppState>,
    Path((task_id, finding_id)): Path<(String, String)>,
    Json(payload): Json<SetVerdictRequest>,
) -> Result<Json<IntelligentTaskFinding>, ApiError> {
    // Validate verdict value.
    if let Some(ref v) = payload.verdict {
        if v != "verified" && v != "false_positive" {
            return Err(ApiError::BadRequest(format!(
                "invalid verdict: {v}. Allowed: verified, false_positive, null"
            )));
        }
    }

    let updated = intelligent_task_state::update_record(&state, &task_id, |record| {
        for finding in &mut record.findings {
            if finding.id == finding_id {
                finding.user_verdict = payload.verdict.clone();
                break;
            }
        }
    })
    .await
    .map_err(internal_error)?
    .ok_or_else(|| ApiError::NotFound(format!("Intelligent task not found: {task_id}")))?;

    // Return just the updated finding.
    let finding = updated
        .findings
        .iter()
        .find(|f| f.id == finding_id)
        .cloned()
        .ok_or_else(|| {
            ApiError::NotFound(format!("Finding not found: {finding_id} in task {task_id}"))
        })?;

    Ok(Json(finding))
}

fn internal_error(error: anyhow::Error) -> ApiError {
    ApiError::Internal(error.to_string())
}

async fn bind_project_names(
    state: &AppState,
    records: Vec<IntelligentTaskRecord>,
) -> Result<Vec<IntelligentTaskRecord>, ApiError> {
    let mut bound = Vec::with_capacity(records.len());
    for record in records {
        bound.push(bind_project_name(state, record).await?);
    }
    Ok(bound)
}

async fn bind_project_name(
    state: &AppState,
    mut record: IntelligentTaskRecord,
) -> Result<IntelligentTaskRecord, ApiError> {
    let project = projects::get_project(state, &record.project_id)
        .await
        .map_err(internal_error)?;
    record.project_name = match project {
        Some(project) => Some(project.name),
        None => {
            tracing::warn!(
                task_id = %record.task_id,
                project_id = %record.project_id,
                "project binding missing for intelligent task; rendering as orphan"
            );
            Some("<项目已删除>".to_string())
        }
    };
    Ok(record)
}
