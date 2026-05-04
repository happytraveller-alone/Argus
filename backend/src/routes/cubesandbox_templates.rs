use async_stream::stream;
use axum::{
    extract::State,
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
        .route("/codeql-cpp", get(get_codeql_cpp_status))
        .route("/codeql-cpp/provision", post(provision_codeql_cpp))
        .route("/codeql-cpp/invalidate", post(invalidate_codeql_cpp))
        .route("/codeql-cpp/stream", get(stream_codeql_cpp))
        .route("/opengrep", get(get_opengrep_status))
        .route("/opengrep/provision", post(provision_opengrep))
        .route("/opengrep/invalidate", post(invalidate_opengrep))
        .route("/opengrep/stream", get(stream_opengrep))
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

async fn stream_opengrep(State(state): State<AppState>) -> impl IntoResponse {
    stream_public_template_kind(state, current_opengrep_route_kind(), TemplateKind::Opengrep).await
}

fn current_opengrep_route_kind() -> TemplateKind {
    TemplateKind::current_opengrep()
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
            loop {
                match rx.recv().await {
                    Ok(event) => {
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
                    Err(_) => break,
                }
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
}
