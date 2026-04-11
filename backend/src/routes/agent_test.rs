use axum::{
    body::Body,
    response::Response,
    routing::post,
    Json, Router,
};
use http::{header, HeaderValue, StatusCode};
use serde_json::{json, Value};

use crate::state::AppState;

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
}

async fn run_recon(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("recon", payload)
}

async fn run_analysis(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("analysis", payload)
}

async fn run_verification(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("verification", payload)
}

async fn run_business_logic(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("business_logic", payload)
}

async fn run_business_logic_recon(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("business_logic_recon", payload)
}

async fn run_business_logic_analysis(Json(payload): Json<Value>) -> Response<Body> {
    sse_response("business_logic_analysis", payload)
}

fn sse_response(kind: &str, payload: Value) -> Response<Body> {
    let body = format!(
        "data: {}\n\ndata: {}\n\n",
        json!({
            "type": "phase_start",
            "message": format!("{kind} test started in rust backend"),
            "metadata": { "kind": kind }
        }),
        json!({
            "type": "task_complete",
            "message": format!("{kind} test finished in rust backend"),
            "metadata": { "request": payload }
        }),
    );

    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    response
}
