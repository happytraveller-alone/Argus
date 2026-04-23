use super::contracts::HandoffResult;

pub fn project_result(result: &HandoffResult, task_id: &str) -> serde_json::Value {
    serde_json::json!({
        "task_id": task_id,
        "status": format!("{:?}", result.status).to_lowercase(),
        "summary": result.summary,
        "structured_outputs": result.structured_outputs,
        "diagnostics": result.diagnostics,
    })
}
