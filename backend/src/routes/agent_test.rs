use axum::{body::Body, response::Response, routing::post, Json, Router};
use http::{header, HeaderValue, StatusCode};
use serde::Deserialize;
use serde_json::{json, Value};
use time::OffsetDateTime;

use crate::runtime::queue as runtime_queue;
use crate::state::AppState;

#[derive(Debug, Deserialize)]
struct ReconTestRequest {
    project_path: String,
    project_name: Option<String>,
    framework_hint: Option<String>,
    max_iterations: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct AnalysisTestRequest {
    project_path: String,
    project_name: Option<String>,
    high_risk_areas: Option<Vec<String>>,
    entry_points: Option<Vec<String>>,
    task_description: Option<String>,
    max_iterations: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct VerificationTestRequest {
    project_path: String,
    findings: Vec<Value>,
    max_iterations: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct BusinessLogicTestRequest {
    project_path: String,
    entry_points_hint: Option<Vec<String>>,
    framework_hint: Option<String>,
    max_iterations: Option<i64>,
    quick_mode: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct BusinessLogicReconTestRequest {
    project_path: String,
    project_name: Option<String>,
    framework_hint: Option<String>,
    max_iterations: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct BusinessLogicAnalysisTestRequest {
    project_path: String,
    risk_point: Value,
    max_iterations: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct ReportTestRequest {
    project_path: String,
    findings: Option<Vec<Value>>,
    max_iterations: Option<i64>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/recon/run", post(run_recon))
        .route("/analysis/run", post(run_analysis))
        .route("/verification/run", post(run_verification))
        .route("/business-logic/run", post(run_business_logic))
        .route("/business-logic-recon/run", post(run_business_logic_recon))
        .route(
            "/business-logic-analysis/run",
            post(run_business_logic_analysis),
        )
        .route("/report/run", post(run_report))
}

async fn run_recon(Json(payload): Json<ReconTestRequest>) -> Response<Body> {
    sse_response(
        "recon",
        json!({
            "project_path": payload.project_path,
            "project_name": payload.project_name.unwrap_or_else(|| "test-project".to_string()),
            "framework_hint": payload.framework_hint,
            "max_iterations": payload.max_iterations.unwrap_or(6),
        }),
    )
}

async fn run_analysis(Json(payload): Json<AnalysisTestRequest>) -> Response<Body> {
    sse_response(
        "analysis",
        json!({
            "project_path": payload.project_path,
            "project_name": payload.project_name.unwrap_or_else(|| "test-project".to_string()),
            "high_risk_areas": payload.high_risk_areas.unwrap_or_default(),
            "entry_points": payload.entry_points.unwrap_or_default(),
            "task_description": payload.task_description.unwrap_or_default(),
            "max_iterations": payload.max_iterations.unwrap_or(8),
        }),
    )
}

async fn run_verification(Json(payload): Json<VerificationTestRequest>) -> Response<Body> {
    sse_response(
        "verification",
        json!({
            "project_path": payload.project_path,
            "findings": payload.findings,
            "max_iterations": payload.max_iterations.unwrap_or(6),
        }),
    )
}

async fn run_business_logic(Json(payload): Json<BusinessLogicTestRequest>) -> Response<Body> {
    sse_response(
        "business_logic",
        json!({
            "project_path": payload.project_path,
            "entry_points_hint": payload.entry_points_hint.unwrap_or_default(),
            "framework_hint": payload.framework_hint,
            "max_iterations": payload.max_iterations.unwrap_or(8),
            "quick_mode": payload.quick_mode.unwrap_or(false),
        }),
    )
}

async fn run_business_logic_recon(
    Json(payload): Json<BusinessLogicReconTestRequest>,
) -> Response<Body> {
    sse_response(
        "business_logic_recon",
        json!({
            "project_path": payload.project_path,
            "project_name": payload.project_name.unwrap_or_else(|| "test-project".to_string()),
            "framework_hint": payload.framework_hint,
            "max_iterations": payload.max_iterations.unwrap_or(10),
        }),
    )
}

async fn run_business_logic_analysis(
    Json(payload): Json<BusinessLogicAnalysisTestRequest>,
) -> Response<Body> {
    sse_response(
        "business_logic_analysis",
        json!({
            "project_path": payload.project_path,
            "risk_point": payload.risk_point,
            "max_iterations": payload.max_iterations.unwrap_or(10),
        }),
    )
}

async fn run_report(Json(payload): Json<ReportTestRequest>) -> Response<Body> {
    sse_response(
        "report",
        json!({
            "project_path": payload.project_path,
            "findings": payload.findings.unwrap_or_default(),
            "max_iterations": payload.max_iterations.unwrap_or(4),
        }),
    )
}

fn sse_response(kind: &str, payload: Value) -> Response<Body> {
    let project_name = payload
        .get("project_name")
        .and_then(Value::as_str)
        .unwrap_or("test-project");
    let project_path = payload
        .get("project_path")
        .and_then(Value::as_str)
        .unwrap_or("");
    let ts = OffsetDateTime::now_utc().unix_timestamp();
    let queue_payload = queue_snapshot(kind, &payload);
    let events = vec![
        json!({
            "id": 1,
            "type": "phase_start",
            "message": format!("{kind} test started in rust backend"),
            "metadata": { "kind": kind },
            "ts": ts,
        }),
        json!({
            "id": 2,
            "type": "tool_call",
            "tool_name": "prepare_project",
            "tool_input": {
                "project_name": project_name,
                "project_path": project_path,
                "request": payload,
            },
            "message": format!("prepare project for {kind}"),
            "ts": ts,
        }),
        json!({
            "id": 3,
            "type": "tool_result",
            "tool_name": "prepare_project",
            "tool_output": format!("prepared project {}", project_name),
            "metadata": { "tool_status": "completed" },
            "ts": ts,
        }),
        json!({
            "id": 4,
            "type": "queue_snapshot",
            "data": queue_payload,
            "message": "queue snapshot updated",
            "ts": ts,
        }),
        json!({
            "id": 5,
            "type": "result",
            "data": {
                "test_mode": kind,
                "project_name": project_name,
                "request": payload,
                "summary": format!("{kind} test completed in rust backend"),
            },
            "message": format!("{kind} result ready"),
            "ts": ts,
        }),
        json!({
            "id": 6,
            "type": "done",
            "message": format!("{kind} test finished in rust backend"),
            "ts": ts,
        }),
    ];

    let body = events
        .into_iter()
        .map(|event| format!("data: {}\n\n", event))
        .collect::<String>();

    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    response
}

fn queue_snapshot(kind: &str, payload: &Value) -> Value {
    runtime_queue::queue_snapshot(kind, payload)
}
