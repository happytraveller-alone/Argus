use axum::{
    extract::{Path, Query, State},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    db::intelligent_task_state, error::ApiError,
    runtime::intelligent::types::IntelligentTaskRecord, state::AppState,
};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CreateIntelligentTaskRequest {
    project_id: String,
}

#[derive(Debug, Deserialize)]
struct ListQuery {
    limit: Option<usize>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(list_tasks).post(create_task))
        .route("/{task_id}", get(get_task))
        .route("/{task_id}/cancel", post(cancel_task))
}

async fn create_task(
    State(state): State<AppState>,
    Json(payload): Json<CreateIntelligentTaskRequest>,
) -> Result<Json<Value>, ApiError> {
    if payload.project_id.trim().is_empty() {
        return Err(ApiError::BadRequest("projectId is required".to_string()));
    }

    let record = state
        .intelligent_task_manager
        .submit(state.clone(), payload.project_id)
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
    Ok(Json(
        intelligent_task_state::list_records(&state, limit)
            .await
            .map_err(internal_error)?,
    ))
}

async fn get_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<IntelligentTaskRecord>, ApiError> {
    let record = intelligent_task_state::get_record(&state, &task_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("Intelligent task not found: {task_id}")))?;
    Ok(Json(record))
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
    Ok(Json(record))
}

fn internal_error(error: anyhow::Error) -> ApiError {
    ApiError::Internal(error.to_string())
}
