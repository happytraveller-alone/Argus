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
    let record = template_provisioner::get_status(&state, TemplateKind::Opengrep)
        .await
        .map_err(internal_error)?;
    Ok(Json(serialize_status(record.as_ref())))
}

async fn provision_opengrep(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let config = CubeSandboxConfig::load_runtime(&state)
        .await
        .map_err(internal_error)?
        .for_template_kind(TemplateKind::Opengrep, state.config.as_ref());
    if !config.enabled {
        return Err(ApiError::BadRequest(
            "CubeSandbox 未启用; 请先在系统配置中开启".to_string(),
        ));
    }
    let record = template_provisioner::start_provision(&state, &config, TemplateKind::Opengrep)
        .await
        .map_err(|error| ApiError::BadRequest(format!("{error:#}")))?;
    Ok(Json(serialize_status(Some(&record))))
}

async fn invalidate_opengrep(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let affected = template_provisioner::invalidate(&state, TemplateKind::Opengrep)
        .await
        .map_err(internal_error)?;
    Ok(Json(json!({ "affected": affected })))
}

async fn stream_opengrep(State(state): State<AppState>) -> impl IntoResponse {
    stream_template_kind(state, TemplateKind::Opengrep).await
}

async fn stream_template_kind(state: AppState, kind: TemplateKind) -> impl IntoResponse {
    let initial_record = template_provisioner::get_status(&state, kind)
        .await
        .ok()
        .flatten();
    let receiver = template_provisioner::subscribe(kind).await;
    let output = stream! {
        if let Some(record) = initial_record.as_ref() {
            if let Ok(data) = serde_json::to_string(&serialize_status(Some(record))) {
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
    match record {
        Some(record) => json!({
            "id": record.id,
            "kind": record.kind,
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
        }),
        None => json!({
            "status": "absent",
            "templateId": null,
            "artifactId": null,
            "jobId": null,
            "errorMessage": null,
            "buildLogTail": "",
        }),
    }
}

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(format!("{error}"))
}
