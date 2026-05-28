use axum::{
    extract::{Path as AxumPath, Query, State},
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::{
    db::cwe_catalog::{self, CweCatalogEntry, CweCatalogListParams},
    error::ApiError,
    state::AppState,
};

#[derive(Debug, Clone, Deserialize)]
pub struct CweCatalogQuery {
    pub keyword: Option<String>,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CweCatalogListResponse {
    pub data: Vec<CweCatalogEntry>,
    pub total: usize,
    pub limit: usize,
    pub offset: usize,
    pub source_version: Option<String>,
    pub source_date: Option<String>,
    pub source_sha256: Option<String>,
    pub translation_source: Option<String>,
    pub translation_reviewed_at: Option<String>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(list_cwe_catalog))
        .route("/{cwe_id}", get(get_cwe_catalog_entry))
}

async fn list_cwe_catalog(
    State(state): State<AppState>,
    Query(query): Query<CweCatalogQuery>,
) -> Result<Json<CweCatalogListResponse>, ApiError> {
    let pool = state
        .db_pool
        .as_ref()
        .ok_or_else(|| ApiError::Internal("CWE catalog database is unavailable".to_string()))?;
    let result = cwe_catalog::list_active_entries(
        pool,
        CweCatalogListParams {
            keyword: query.keyword,
            limit: query.limit,
            offset: query.offset,
        },
    )
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;

    Ok(Json(CweCatalogListResponse {
        data: result.entries,
        total: result.total,
        limit: result.limit,
        offset: result.offset,
        source_version: result.source_version,
        source_date: result.source_date,
        source_sha256: result.source_sha256,
        translation_source: result.translation_source,
        translation_reviewed_at: result.translation_reviewed_at,
    }))
}

async fn get_cwe_catalog_entry(
    State(state): State<AppState>,
    AxumPath(cwe_id): AxumPath<String>,
) -> Result<Json<CweCatalogEntry>, ApiError> {
    let pool = state
        .db_pool
        .as_ref()
        .ok_or_else(|| ApiError::Internal("CWE catalog database is unavailable".to_string()))?;
    let entry = cwe_catalog::lookup_active_entry(pool, &cwe_id)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .ok_or_else(|| ApiError::NotFound(format!("CWE catalog entry not found: {cwe_id}")))?;
    Ok(Json(entry))
}
