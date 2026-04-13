use axum::{
    extract::{Query, State},
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::{
    db::{projects, task_state},
    error::ApiError,
    state::AppState,
};

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

#[derive(Debug, Clone, Serialize)]
struct SearchTaskItem {
    id: String,
    project_id: String,
    name: String,
    description: String,
    task_type: String,
    status: String,
    created_at: String,
    updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct SearchFindingItem {
    id: String,
    task_id: String,
    title: String,
    description: String,
    vulnerability_type: String,
    severity: String,
    file_path: String,
    status: String,
    created_at: String,
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
    let (matched_projects, projects_total) = matched_projects(&state, &query).await?;
    let (matched_tasks, tasks_total) = matched_tasks(&state, &query).await?;
    let (matched_findings, findings_total) = matched_findings(&state, &query).await?;
    Ok(Json(json!({
        "findings": matched_findings,
        "tasks": matched_tasks,
        "projects": matched_projects,
        "total": {
            "findings_total": findings_total,
            "tasks_total": tasks_total,
            "projects_total": projects_total
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
    let (matched_projects, total) = matched_projects(&state, &query).await?;
    Ok(Json(json!({
        "data": matched_projects,
        "total": total,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    })))
}

async fn search_tasks(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let (matched_tasks, total) = matched_tasks(&state, &query).await?;
    Ok(Json(json!({
        "data": matched_tasks,
        "total": total,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    })))
}

async fn search_findings(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let (matched_findings, total) = matched_findings(&state, &query).await?;
    Ok(Json(json!({
        "data": matched_findings,
        "total": total,
        "limit": query.limit.unwrap_or(50),
        "offset": query.offset.unwrap_or(0),
    })))
}

async fn matched_projects(
    state: &AppState,
    query: &SearchQuery,
) -> Result<(Vec<SearchProjectItem>, usize), ApiError> {
    let keyword = query.keyword.trim().to_lowercase();
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(50);
    let mut items = projects::list_projects(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    items.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    let filtered = items
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
        .collect::<Vec<_>>();
    let total = filtered.len();
    let matched = filtered
        .into_iter()
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
    Ok((matched, total))
}

async fn matched_tasks(
    state: &AppState,
    query: &SearchQuery,
) -> Result<(Vec<SearchTaskItem>, usize), ApiError> {
    let keyword = query.keyword.trim().to_lowercase();
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(50);
    let snapshot = task_state::load_snapshot(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut tasks = snapshot.agent_tasks.into_values().collect::<Vec<_>>();
    tasks.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    let filtered = tasks
        .into_iter()
        .filter(|task| {
            if keyword.is_empty() {
                return true;
            }
            let haystack = format!(
                "{} {} {} {} {}",
                task.name.clone().unwrap_or_default(),
                task.description.clone().unwrap_or_default(),
                task.task_type,
                task.status,
                task.created_at
            )
            .to_lowercase();
            haystack.contains(&keyword)
        })
        .collect::<Vec<_>>();
    let total = filtered.len();
    let matched = filtered
        .into_iter()
        .skip(offset)
        .take(limit)
        .map(|task| SearchTaskItem {
            id: task.id,
            project_id: task.project_id,
            name: task.name.unwrap_or_default(),
            description: task.description.unwrap_or_default(),
            task_type: task.task_type,
            status: task.status,
            created_at: task.created_at,
            updated_at: task.completed_at.or(task.started_at),
        })
        .collect();
    Ok((matched, total))
}

async fn matched_findings(
    state: &AppState,
    query: &SearchQuery,
) -> Result<(Vec<SearchFindingItem>, usize), ApiError> {
    let keyword = query.keyword.trim().to_lowercase();
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(50);
    let snapshot = task_state::load_snapshot(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut findings = snapshot
        .agent_tasks
        .into_values()
        .flat_map(|task| task.findings.into_iter())
        .collect::<Vec<_>>();
    findings.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    let filtered = findings
        .into_iter()
        .filter(|finding| {
            if keyword.is_empty() {
                return true;
            }
            let haystack = format!(
                "{} {} {} {} {}",
                finding.title,
                finding.description.clone().unwrap_or_default(),
                finding.vulnerability_type,
                finding.file_path.clone().unwrap_or_default(),
                finding.code_snippet.clone().unwrap_or_default()
            )
            .to_lowercase();
            haystack.contains(&keyword)
        })
        .collect::<Vec<_>>();
    let total = filtered.len();
    let matched = filtered
        .into_iter()
        .skip(offset)
        .take(limit)
        .map(|finding| SearchFindingItem {
            id: finding.id,
            task_id: finding.task_id,
            title: finding.title,
            description: finding.description.unwrap_or_default(),
            vulnerability_type: finding.vulnerability_type,
            severity: finding.severity,
            file_path: finding.file_path.unwrap_or_default(),
            status: finding.status,
            created_at: finding.created_at,
        })
        .collect();
    Ok((matched, total))
}
