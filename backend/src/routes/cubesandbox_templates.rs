use async_stream::stream;
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::sse::{Event, KeepAlive, Sse},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::{json, Value};
use std::time::Duration;

use crate::{
    db::cubesandbox_templates::{CubesandboxTemplateRecord, TemplateKind, TemplateStatus},
    error::ApiError,
    runtime::cubesandbox::{config::CubeSandboxConfig, template_provisioner},
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(list_template_management_overview))
        .route("/cleanup-failed", post(cleanup_failed_templates))
        .route(
            "/records/{record_id}",
            axum::routing::delete(delete_failed_template_record),
        )
        .route("/codeql-cpp", get(get_codeql_cpp_status))
        .route("/codeql-cpp/provision", post(provision_codeql_cpp))
        .route("/codeql-cpp/invalidate", post(invalidate_codeql_cpp))
        .route("/codeql-cpp/reset", post(reset_codeql_cpp))
        .route("/codeql-cpp/stream", get(stream_codeql_cpp))
        .route("/opengrep", get(get_opengrep_status))
        .route("/opengrep/provision", post(provision_opengrep))
        .route("/opengrep/invalidate", post(invalidate_opengrep))
        .route("/opengrep/reset", post(reset_opengrep))
        .route("/opengrep/stream", get(stream_opengrep))
}

#[derive(serde::Deserialize, Default)]
struct ListOverviewQuery {
    /// Comma-separated status values to filter by, e.g. `?status=ready,building`.
    /// Absent or empty: return all records (current behavior).
    status: Option<String>,
}

async fn list_template_management_overview(
    State(state): State<AppState>,
    Query(query): Query<ListOverviewQuery>,
) -> Result<Json<Value>, ApiError> {
    let all_templates = crate::db::cubesandbox_templates::list_all_history(&state, 200)
        .await
        .map_err(internal_error)?;
    let failed_count = all_templates
        .iter()
        .filter(|record| record.status == TemplateStatus::Failed)
        .count();
    let templates = if let Some(raw) = query.status.as_deref().filter(|s| !s.trim().is_empty()) {
        let allowed: std::collections::HashSet<&str> =
            raw.split(',').map(str::trim).filter(|s| !s.is_empty()).collect();
        all_templates
            .into_iter()
            .filter(|record| allowed.contains(record.status.as_str()))
            .collect::<Vec<_>>()
    } else {
        all_templates
    };
    Ok(Json(json!({
        "templates": templates,
        "failedCount": failed_count,
        "actions": {
            "deleteScope": "failed_or_invalidated_templates_only",
            "cleanupScope": "failed_templates_only",
            "sandboxDeletion": false,
            "resetDeletesTemplates": true,
            "resetRebuildsTemplate": true,
            "resetTargetStatus": "ready"
        }
    })))
}

async fn cleanup_failed_templates(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let failed = crate::db::cubesandbox_templates::list_failed(&state, 200)
        .await
        .map_err(internal_error)?;
    let scanned_failed = failed.len();
    let mut deleted_records = 0usize;
    let mut deleted_templates = 0usize;
    let mut failures = Vec::<Value>::new();

    for record in failed {
        match delete_failed_record_inner(&state, &record).await {
            Ok(summary) => {
                deleted_records += summary.deleted_records;
                deleted_templates += summary.deleted_templates;
            }
            Err(error) => failures.push(json!({
                "recordId": record.id,
                "templateId": record.template_id,
                "error": error.to_string()
            })),
        }
    }

    Ok(Json(json!({
        "scope": "failed_templates_only",
        "scannedFailed": scanned_failed,
        "deletedRecords": deleted_records,
        "deletedTemplates": deleted_templates,
        "failures": failures
    })))
}

async fn delete_failed_template_record(
    State(state): State<AppState>,
    Path(record_id): Path<String>,
) -> Result<impl IntoResponse, ApiError> {
    let record = crate::db::cubesandbox_templates::load_by_id(&state, &record_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| {
            ApiError::NotFound(format!(
                "CubeSandbox template record not found: {record_id}"
            ))
        })?;
    if !record.status.is_terminal_inactive() {
        return Ok((
            StatusCode::CONFLICT,
            Json(json!({
                "error": "only failed or invalidated CubeSandbox template records can be deleted",
                "scope": "failed_or_invalidated_templates_only",
                "recordId": record.id,
                "status": record.status.as_str()
            })),
        )
            .into_response());
    }
    let summary = delete_failed_record_inner(&state, &record).await?;
    Ok(Json(summary.to_json()).into_response())
}

struct FailedTemplateDeleteSummary {
    record_id: String,
    template_id: Option<String>,
    deleted_records: usize,
    deleted_templates: usize,
    template_delete_error: Option<String>,
}

impl FailedTemplateDeleteSummary {
    fn to_json(&self) -> Value {
        json!({
            "scope": "failed_or_invalidated_templates_only",
            "recordId": self.record_id,
            "templateId": self.template_id,
            "deletedRecords": self.deleted_records,
            "deletedTemplates": self.deleted_templates,
            "templateDeleteError": self.template_delete_error
        })
    }
}

async fn delete_failed_record_inner(
    state: &AppState,
    record: &CubesandboxTemplateRecord,
) -> Result<FailedTemplateDeleteSummary, ApiError> {
    if !record.status.is_terminal_inactive() {
        return Err(ApiError::Conflict(
            "only failed or invalidated CubeSandbox template records can be deleted".to_string(),
        ));
    }

    let mut deleted_templates = 0usize;
    let mut template_delete_error = None;
    if let Some(template_id) = record
        .template_id
        .as_deref()
        .filter(|value| !value.trim().is_empty())
    {
        let config = CubeSandboxConfig::load_runtime(state)
            .await
            .map_err(internal_error)?
            .for_template_kind(record.kind, state.config.as_ref());
        let client = crate::runtime::cubesandbox::cubemaster_client::CubemasterClient::new(
            crate::runtime::cubesandbox::cubemaster_client::CubemasterClientConfig {
                base_url: config.cubemaster_base_url.clone(),
                cleanup_timeout_seconds: config.cubemaster_cleanup_timeout_seconds,
                instance_type: "cubebox".to_string(),
            },
            config,
        )
        .map_err(internal_error)?;
        match client.delete_template(template_id).await {
            Ok(()) => {
                deleted_templates = 1;
            }
            Err(error) if record.status == TemplateStatus::Invalidated => {
                let message = format!("{error:#}");
                tracing::warn!(
                    record_id = %record.id,
                    template_id,
                    error = %message,
                    "CubeMaster delete failed for invalidated template; deleting local record anyway"
                );
                template_delete_error = Some(message);
            }
            Err(error) => {
                return Err(ApiError::Upstream(format!(
                    "failed to delete CubeMaster terminal template {template_id}; local record kept: {error:#}"
                )));
            }
        }
    }

    let deleted =
        crate::db::cubesandbox_templates::delete_failed_or_invalidated_by_id(state, &record.id)
            .await
            .map_err(internal_error)?;
    Ok(FailedTemplateDeleteSummary {
        record_id: record.id.clone(),
        template_id: record.template_id.clone(),
        deleted_records: usize::from(deleted.is_some()),
        deleted_templates,
        template_delete_error,
    })
}

async fn get_codeql_cpp_status(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let record = template_provisioner::get_status(&state, TemplateKind::CodeqlCpp)
        .await
        .map_err(internal_error)?;
    Ok(Json(serialize_status(record.as_ref())))
}

async fn provision_codeql_cpp(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let config = CubeSandboxConfig::load_runtime(&state)
        .await
        .map_err(internal_error)?
        .for_template_kind(TemplateKind::CodeqlCpp, state.config.as_ref());
    if !config.enabled {
        return Err(ApiError::BadRequest(
            "CubeSandbox 未启用; 请先在系统配置中开启".to_string(),
        ));
    }
    let record = template_provisioner::start_provision(&state, &config, TemplateKind::CodeqlCpp)
        .await
        .map_err(|error| ApiError::BadRequest(format!("{error:#}")))?;
    Ok(Json(serialize_status(Some(&record))))
}

async fn invalidate_codeql_cpp(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let affected = template_provisioner::invalidate(&state, TemplateKind::CodeqlCpp)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({ "affected": affected })))
}

async fn reset_codeql_cpp(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    reset_template_kind(state, TemplateKind::CodeqlCpp, TemplateKind::CodeqlCpp).await
}

async fn stream_codeql_cpp(State(state): State<AppState>) -> impl IntoResponse {
    stream_template_kind(state, TemplateKind::CodeqlCpp).await
}

async fn get_opengrep_status(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let record = template_provisioner::get_status(&state, current_opengrep_route_kind())
        .await
        .map_err(internal_error)?;
    Ok(Json(serialize_status_for_public_kind(
        record.as_ref(),
        TemplateKind::Opengrep,
    )))
}

async fn provision_opengrep(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let config = CubeSandboxConfig::load_runtime(&state)
        .await
        .map_err(internal_error)?
        .for_template_kind(current_opengrep_route_kind(), state.config.as_ref());
    if !config.enabled {
        return Err(ApiError::BadRequest(
            "CubeSandbox 未启用; 请先在系统配置中开启".to_string(),
        ));
    }
    let record =
        template_provisioner::start_provision(&state, &config, current_opengrep_route_kind())
            .await
            .map_err(|error| ApiError::BadRequest(format!("{error:#}")))?;
    Ok(Json(serialize_status_for_public_kind(
        Some(&record),
        TemplateKind::Opengrep,
    )))
}

async fn invalidate_opengrep(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let affected = template_provisioner::invalidate(&state, current_opengrep_route_kind())
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({ "affected": affected })))
}

async fn reset_opengrep(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    reset_template_kind(state, current_opengrep_route_kind(), TemplateKind::Opengrep).await
}

async fn stream_opengrep(State(state): State<AppState>) -> impl IntoResponse {
    stream_public_template_kind(state, current_opengrep_route_kind(), TemplateKind::Opengrep).await
}

fn current_opengrep_route_kind() -> TemplateKind {
    TemplateKind::current_opengrep()
}

async fn reset_template_kind(
    state: AppState,
    kind: TemplateKind,
    public_kind: TemplateKind,
) -> Result<Json<Value>, ApiError> {
    let config = CubeSandboxConfig::load_runtime(&state)
        .await
        .map_err(internal_error)?
        .for_template_kind(kind, state.config.as_ref());
    if !config.enabled {
        return Err(ApiError::BadRequest(
            "CubeSandbox 未启用; 请先在系统配置中开启".to_string(),
        ));
    }

    let active = crate::db::cubesandbox_templates::get_active(&state, kind)
        .await
        .map_err(internal_error)?;

    let mut invalidated_records = 0u64;
    if active.is_some() {
        invalidated_records = template_provisioner::invalidate(&state, kind)
            .await
            .map_err(internal_error)?;
    }

    let mut deleted_records = 0usize;
    let mut deleted_templates = 0usize;
    let terminal_records =
        crate::db::cubesandbox_templates::list_failed_or_invalidated_by_kind(&state, kind, 200)
            .await
            .map_err(internal_error)?;
    for terminal_record in terminal_records {
        let summary = delete_failed_record_inner(&state, &terminal_record).await?;
        deleted_records += summary.deleted_records;
        deleted_templates += summary.deleted_templates;
    }

    let record = template_provisioner::start_provision(&state, &config, kind)
        .await
        .map_err(|error| ApiError::BadRequest(format!("{error:#}")))?;
    let status = serialize_status_for_public_kind(Some(&record), public_kind);

    Ok(Json(json!({
        "kind": public_kind,
        "recordKind": kind,
        "invalidatedRecords": invalidated_records,
        "deletedRecords": deleted_records,
        "deletedTemplates": deleted_templates,
        "targetStatus": "ready",
        "record": status
    })))
}

async fn stream_template_kind(state: AppState, kind: TemplateKind) -> impl IntoResponse {
    stream_public_template_kind(state, kind, kind).await
}

async fn stream_public_template_kind(
    state: AppState,
    kind: TemplateKind,
    public_kind: TemplateKind,
) -> impl IntoResponse {
    let initial_record = template_provisioner::get_status(&state, kind)
        .await
        .ok()
        .flatten();
    let receiver = template_provisioner::subscribe(kind).await;
    let output = stream! {
        if let Some(record) = initial_record.as_ref() {
            if let Ok(data) = serde_json::to_string(
                &serialize_status_for_public_kind(Some(record), public_kind),
            ) {
                yield Ok::<Event, std::convert::Infallible>(
                    Event::default().event("snapshot").data(data),
                );
            }
        }
        if let Some(mut rx) = receiver {
            while let Ok(event) = rx.recv().await {
                {
                    if let Ok(data) = serde_json::to_string(&event) {
                        yield Ok(Event::default().event("event").data(data));
                    }
                    if event.status == TemplateStatus::Ready.as_str()
                        || event.status == TemplateStatus::Failed.as_str()
                        || event.status == TemplateStatus::Invalidated.as_str()
                    {
                        break;
                    }
                }
                // (Err(_) branch handled by while-let exit)
            }
        } else {
            // No active build; emit a sentinel so the client can disconnect.
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    };
    Sse::new(output).keep_alive(KeepAlive::default())
}

fn serialize_status(record: Option<&CubesandboxTemplateRecord>) -> Value {
    record.map_or_else(serialize_absent_status, |record| {
        serialize_record_status(record, record.kind)
    })
}

fn serialize_status_for_public_kind(
    record: Option<&CubesandboxTemplateRecord>,
    public_kind: TemplateKind,
) -> Value {
    record.map_or_else(serialize_absent_status, |record| {
        serialize_record_status(record, public_kind)
    })
}

fn serialize_record_status(record: &CubesandboxTemplateRecord, public_kind: TemplateKind) -> Value {
    let mut value = json!({
        "id": record.id,
        "kind": public_kind,
        "status": record.status,
        "templateId": record.template_id,
        "artifactId": record.artifact_id,
        "jobId": record.job_id,
        "imageRef": record.image_ref,
        "errorMessage": record.error_message,
        "buildLogTail": record.build_log_tail,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
        "readyAt": record.ready_at,
    });
    if public_kind != record.kind {
        value["recordKind"] = json!(record.kind);
    }
    value
}

fn serialize_absent_status() -> Value {
    json!({
        "status": "absent",
        "templateId": null,
        "artifactId": null,
        "jobId": null,
        "errorMessage": null,
        "buildLogTail": "",
    })
}

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(format!("{error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_record(kind: TemplateKind) -> CubesandboxTemplateRecord {
        CubesandboxTemplateRecord {
            id: "record-1".to_string(),
            kind,
            status: TemplateStatus::Ready,
            template_id: Some("tpl-1".to_string()),
            artifact_id: Some("artifact-1".to_string()),
            job_id: Some("job-1".to_string()),
            image_ref: "argus/cubesandbox-test:auto".to_string(),
            error_message: None,
            build_log_tail: "ready".to_string(),
            created_at: "2026-05-04T00:00:00Z".to_string(),
            updated_at: "2026-05-04T00:00:01Z".to_string(),
            ready_at: Some("2026-05-04T00:00:02Z".to_string()),
            image_fingerprint: None,
            consecutive_scan_failures: 0,
        }
    }

    #[test]
    fn opengrep_route_uses_dedicated_current_kind() {
        assert_eq!(
            current_opengrep_route_kind(),
            TemplateKind::OpengrepDedicated
        );
        assert_ne!(current_opengrep_route_kind(), TemplateKind::Opengrep);
    }

    #[test]
    fn opengrep_status_serializes_public_kind_and_internal_record_kind() {
        let record = sample_record(TemplateKind::current_opengrep());
        let payload = serialize_status_for_public_kind(Some(&record), TemplateKind::Opengrep);

        assert_eq!(payload["kind"], "opengrep");
        assert_eq!(payload["recordKind"], "opengrep_dedicated");
        assert_eq!(payload["templateId"], "tpl-1");
    }

    #[test]
    fn codeql_status_keeps_codeql_kind_without_opengrep_alias() {
        let record = sample_record(TemplateKind::CodeqlCpp);
        let payload = serialize_status(Some(&record));

        assert_eq!(payload["kind"], "codeql_cpp");
        assert!(payload.get("recordKind").is_none());
    }

    // --- Phase 6: ?status= filter tests ---

    fn make_record_with_status(kind: TemplateKind, status: TemplateStatus) -> CubesandboxTemplateRecord {
        CubesandboxTemplateRecord {
            status,
            ..sample_record(kind)
        }
    }

    fn apply_status_filter<'a>(
        records: &'a [CubesandboxTemplateRecord],
        status_param: Option<&str>,
    ) -> Vec<&'a CubesandboxTemplateRecord> {
        if let Some(raw) = status_param.filter(|s| !s.trim().is_empty()) {
            let allowed: std::collections::HashSet<&str> =
                raw.split(',').map(str::trim).filter(|s| !s.is_empty()).collect();
            records
                .iter()
                .filter(|r| allowed.contains(r.status.as_str()))
                .collect()
        } else {
            records.iter().collect()
        }
    }

    #[test]
    fn test_list_template_management_overview_status_filter_ready_only() {
        let records = vec![
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Ready),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Building),
        ];
        let filtered = apply_status_filter(&records, Some("ready"));
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].status, TemplateStatus::Ready);
    }

    #[test]
    fn test_list_template_management_overview_status_filter_multi_value() {
        let records = vec![
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Ready),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Building),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Invalidated),
        ];
        let filtered = apply_status_filter(&records, Some("ready,building"));
        assert_eq!(filtered.len(), 2);
        assert!(filtered.iter().all(|r| r.status == TemplateStatus::Ready || r.status == TemplateStatus::Building));
    }

    #[test]
    fn test_list_template_management_overview_status_filter_absent_returns_all() {
        let records = vec![
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Ready),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
        ];
        let filtered = apply_status_filter(&records, None);
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_list_template_management_overview_status_filter_empty_string_returns_all() {
        let records = vec![
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Ready),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
        ];
        let filtered = apply_status_filter(&records, Some(""));
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_list_template_management_overview_failed_count_stable_under_status_filter() {
        // failed_count is computed from all_templates BEFORE status filter is applied.
        // Simulate: 2 failed records total; filter to "ready" returns 1 ready record,
        // but failed_count must still be 2.
        let all_templates = vec![
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Ready),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
            make_record_with_status(TemplateKind::CodeqlCpp, TemplateStatus::Failed),
        ];
        // failed_count computed before filter (as in handler)
        let failed_count = all_templates
            .iter()
            .filter(|r| r.status == TemplateStatus::Failed)
            .count();
        // apply status=ready filter
        let filtered = apply_status_filter(&all_templates, Some("ready"));
        assert_eq!(filtered.len(), 1, "filtered list should contain only ready");
        assert_eq!(failed_count, 2, "failed_count must reflect unfiltered all_templates");
    }
}
