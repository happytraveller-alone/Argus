use backend_rust::runtime::hermes::contracts::{
    AgentRole, HandoffRequest, HandoffResult, HandoffStatus,
};
use backend_rust::runtime::hermes::layout::{runtime_data_root, validate_isolation};

fn fixture(name: &str) -> String {
    std::fs::read_to_string(format!("tests/fixtures/hermes/{name}")).unwrap()
}

#[test]
fn handoff_schema_includes_required_fields() {
    let req = HandoffRequest {
        role: AgentRole::Recon,
        task_id: "t1".to_string(),
        project_id: "p1".to_string(),
        correlation_id: "c1".to_string(),
        payload: serde_json::json!({"project_path": "/scan"}),
    };
    let json = serde_json::to_value(&req).unwrap();
    assert!(json.get("role").is_some());
    assert!(json.get("task_id").is_some());
    assert!(json.get("project_id").is_some());
    assert!(json.get("correlation_id").is_some());
    assert!(json.get("payload").is_some());

    let fixture_json: serde_json::Value =
        serde_json::from_str(&fixture("handoff-request.json")).unwrap();
    assert_eq!(json, fixture_json);
}

#[test]
fn result_schema_includes_required_fields() {
    let result = HandoffResult {
        status: HandoffStatus::Success,
        summary: "done".to_string(),
        structured_outputs: vec![],
        diagnostics: None,
    };
    let json = serde_json::to_value(&result).unwrap();
    assert!(json.get("status").is_some());
    assert!(json.get("summary").is_some());
    assert!(json.get("structured_outputs").is_some());

    let fixture_json: serde_json::Value =
        serde_json::from_str(&fixture("handoff-result.json")).unwrap();
    assert_eq!(json, fixture_json);
}

#[test]
fn each_agent_resolves_to_its_own_data_dir() {
    let roles = [
        AgentRole::Recon,
        AgentRole::Analysis,
        AgentRole::Verification,
        AgentRole::Report,
    ];
    let paths: Vec<_> = roles.iter().map(runtime_data_root).collect();
    let unique: std::collections::HashSet<_> = paths.iter().collect();
    assert_eq!(
        paths.len(),
        unique.len(),
        "each role must have a unique data root"
    );
}

#[test]
fn no_two_roles_share_same_data_root() {
    let roles = vec![
        AgentRole::Recon,
        AgentRole::Analysis,
        AgentRole::Verification,
        AgentRole::Report,
    ];
    assert!(validate_isolation(&roles).is_ok());
}
