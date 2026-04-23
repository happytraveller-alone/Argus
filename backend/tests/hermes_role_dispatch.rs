use backend_rust::runtime::hermes::contracts::{AgentRole, HandoffRequest, HandoffStatus};
use backend_rust::runtime::hermes::handoff::{build_handoff, serialize_handoff};
use backend_rust::runtime::hermes::parser::parse_hermes_output;

#[test]
fn can_build_handoff_for_each_role() {
    for role in &[
        AgentRole::Recon,
        AgentRole::Analysis,
        AgentRole::Verification,
        AgentRole::Report,
    ] {
        let req = build_handoff(
            role,
            "task-1",
            "proj-1",
            "corr-1",
            serde_json::json!({"project_path": "/scan"}),
        );
        assert_eq!(&req.role, role);
        assert_eq!(req.task_id, "task-1");
    }
}

#[test]
fn can_serialize_deserialize_handoff() {
    let req = build_handoff(
        &AgentRole::Analysis,
        "task-2",
        "proj-2",
        "corr-2",
        serde_json::json!({"project_path": "/scan"}),
    );
    let json = serialize_handoff(&req).unwrap();
    let decoded: HandoffRequest = serde_json::from_str(&json).unwrap();
    assert_eq!(decoded.role, AgentRole::Analysis);
    assert_eq!(decoded.task_id, "task-2");
}

#[test]
fn parser_handles_valid_json_output() {
    let raw = r#"{"status":"success","summary":"all good","structured_outputs":[],"diagnostics":null}"#;
    let result = parse_hermes_output(raw).unwrap();
    assert_eq!(result.status, HandoffStatus::Success);
    assert_eq!(result.summary, "all good");
}

#[test]
fn parser_handles_malformed_output_gracefully() {
    let raw = "this is not json at all";
    let result = parse_hermes_output(raw).unwrap();
    assert_eq!(result.status, HandoffStatus::Error);
    assert_eq!(result.summary, raw);
    assert!(result.structured_outputs.is_empty());
}
