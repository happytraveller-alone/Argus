use axum::{
    extract::{Query, State},
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::{db::projects, error::ApiError, state::AppState};

#[derive(Debug, Clone, Deserialize)]
pub struct SearchQuery {
    pub keyword: String,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
    pub sort_by: Option<String>,
    pub sort_order: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct SearchProjectItem {
    id: String,
    name: String,
    description: String,
    source_type: String,
    repository_type: String,
    default_branch: String,
    created_at: String,
    updated_at: String,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/search", get(search_global))
        .route("/projects/search", get(search_projects))
        .route("/tasks/search", get(search_tasks))
        .route("/findings/search", get(search_findings))
}

async fn search_global(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let matched_projects = matched_projects(&state, &query).await?;
    Ok(Json(json!({
        "findings": [],
        "tasks": [],
        "projects": matched_projects,
        "total": {
            "findings_total": 0,
            "tasks_total": 0,
            "projects_total": matched_projects.len()
        },
        "keyword": query.keyword,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    })))
}

async fn search_projects(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let matched_projects = matched_projects(&state, &query).await?;
    Ok(Json(json!({
        "data": matched_projects,
        "total": matched_projects.len(),
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    })))
}

async fn search_tasks(Query(query): Query<SearchQuery>) -> Json<serde_json::Value> {
    Json(json!({
        "data": [],
        "total": 0,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    }))
}

async fn search_findings(Query(query): Query<SearchQuery>) -> Json<serde_json::Value> {
    Json(json!({
        "data": [],
        "total": 0,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    }))
}

async fn matched_projects(
    state: &AppState,
    query: &SearchQuery,
) -> Result<Vec<SearchProjectItem>, ApiError> {
    let keyword = query.keyword.trim().to_lowercase();
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(50);
    let mut items = projects::list_projects(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    items.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    let matched = items
        .into_iter()
        .filter(|project| {
            if keyword.is_empty() {
                return true;
            }
            let haystack = format!(
                "{} {} {} {}",
                project.name, project.description, project.repository_type, project.default_branch
            )
            .to_lowercase();
            haystack.contains(&keyword)
        })
        .skip(offset)
        .take(limit)
        .map(|project| SearchProjectItem {
            id: project.id,
            name: project.name,
            description: project.description,
            source_type: project.source_type,
            repository_type: project.repository_type,
            default_branch: project.default_branch,
            created_at: project.created_at,
            updated_at: project.updated_at,
        })
        .collect();
    Ok(matched)
}
