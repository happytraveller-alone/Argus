use axum::{
    extract::{Path, Query, State},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    db::cubesandbox_task_state, error::ApiError,
    runtime::cubesandbox::types::CubeSandboxTaskStatus, state::AppState,
};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SubmitCubeSandboxTaskRequest {
    code: String,
    timeout_seconds: Option<u64>,
    metadata: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct ListQuery {
    limit: Option<usize>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(list_tasks).post(submit_task))
        .route("/{task_id}", get(get_task).delete(delete_task))
        .route("/{task_id}/interrupt", post(interrupt_task))
}

async fn submit_task(
    State(state): State<AppState>,
    Json(payload): Json<SubmitCubeSandboxTaskRequest>,
) -> Result<Json<Value>, ApiError> {
    if payload.code.trim().is_empty() {
        return Err(ApiError::BadRequest("code is required".to_string()));
    }
    let record = state
        .cube_sandbox_task_manager
        .submit(
            state.clone(),
            payload.code,
            payload.timeout_seconds,
            payload.metadata,
        )
        .await
        .map_err(internal_error)?;

    Ok(Json(json!({
        "taskId": record.task_id,
        "status": record.status,
        "createdAt": record.created_at,
        "links": {
            "self": format!("/api/v1/cubesandbox-tasks/{}", record.task_id)
        }
    })))
}

async fn list_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<crate::runtime::cubesandbox::types::CubeSandboxTaskRecord>>, ApiError> {
    Ok(Json(
        cubesandbox_task_state::list_records(&state, query.limit.unwrap_or(50).clamp(1, 200))
            .await
            .map_err(internal_error)?,
    ))
}

async fn get_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<crate::runtime::cubesandbox::types::CubeSandboxTaskRecord>, ApiError> {
    let record = cubesandbox_task_state::get_record(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("CubeSandbox task not found: {task_id}")))?;
    Ok(Json(record))
}

async fn interrupt_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<crate::runtime::cubesandbox::types::CubeSandboxTaskRecord>, ApiError> {
    let record = state
        .cube_sandbox_task_manager
        .interrupt(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("CubeSandbox task not found: {task_id}")))?;
    Ok(Json(record))
}

async fn delete_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    let record = cubesandbox_task_state::get_record(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("CubeSandbox task not found: {task_id}")))?;
    if !record.status.is_terminal() {
        return Err(ApiError::Conflict(
            "cannot delete non-terminal CubeSandbox task".to_string(),
        ));
    }
    let deleted = cubesandbox_task_state::delete_record(&state, &task_id)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({
        "deleted": deleted.is_some(),
        "taskId": task_id,
        "terminalStatus": match record.status {
            CubeSandboxTaskStatus::Completed => "completed",
            CubeSandboxTaskStatus::Failed => "failed",
            CubeSandboxTaskStatus::Interrupted => "interrupted",
            CubeSandboxTaskStatus::CleanupFailed => "cleanup_failed",
            _ => "non_terminal"
        }
    })))
}

fn internal_error(error: anyhow::Error) -> ApiError {
    ApiError::Internal(error.to_string())
}
