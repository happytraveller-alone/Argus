use serde_json::Value;
use std::{fs, path::PathBuf};

fn fixture_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("agentflow")
        .join("fixtures")
        .join(name)
}

fn load_fixture(name: &str) -> Value {
    let path = fixture_path(name);
    let content = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("read fixture {}: {err}", path.display()));
    serde_json::from_str(&content)
        .unwrap_or_else(|err| panic!("parse fixture {}: {err}", path.display()))
}

fn array_field<'a>(value: &'a Value, key: &str) -> &'a Vec<Value> {
    value
        .get(key)
        .and_then(Value::as_array)
        .unwrap_or_else(|| panic!("fixture field {key:?} should be an array"))
}

fn string_at<'a>(value: &'a Value, path: &[&str]) -> Option<&'a str> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_str()
}

fn has_static_origin(finding: &Value) -> bool {
    let source_kind = string_at(finding, &["source", "kind"]).unwrap_or_default();
    let source_origin = string_at(finding, &["source_origin"]).unwrap_or_default();
    let source_engine = string_at(finding, &["source", "engine"]).unwrap_or_default();
    [source_kind, source_origin, source_engine]
        .iter()
        .any(|value| value.to_ascii_lowercase().contains("static"))
}

fn assert_importable_agentflow_output(value: &Value) {
    assert_eq!(
        value.get("contract_version").and_then(Value::as_str),
        Some("argus-agentflow-p1/v1")
    );
    for finding in array_field(value, "findings") {
        assert!(
            !has_static_origin(finding),
            "direct findings must not originate from static/bootstrap inputs: {finding:#}"
        );
        assert_eq!(
            string_at(finding, &["source", "kind"]),
            Some("agentflow_native"),
            "accepted direct findings must carry native AgentFlow provenance"
        );
    }
}

#[test]
fn agentflow_fixture_matrix_accepts_happy_path_direct_finding() {
    let fixture = load_fixture("p1_happy_path_output.json");

    assert_importable_agentflow_output(&fixture);
    assert_eq!(
        fixture.get("status").and_then(Value::as_str),
        Some("completed")
    );
    assert_eq!(array_field(&fixture, "findings").len(), 1);
    assert_eq!(array_field(&fixture, "native_artifacts").len(), 2);

    let finding = &array_field(&fixture, "findings")[0];
    assert_eq!(
        finding.get("id").and_then(Value::as_str),
        Some("af-sql-001")
    );
    assert_eq!(
        finding.get("is_verified").and_then(Value::as_bool),
        Some(true)
    );
    assert_eq!(
        finding.get("status").and_then(Value::as_str),
        Some("verified")
    );
}

#[test]
fn agentflow_fixture_matrix_surfaces_failure_without_findings() {
    let fixture = load_fixture("p1_failure_path_output.json");

    assert_importable_agentflow_output(&fixture);
    assert_eq!(
        fixture.get("status").and_then(Value::as_str),
        Some("failed")
    );
    assert!(array_field(&fixture, "findings").is_empty());
    let user_message = string_at(&fixture, &["error", "user_message"]).unwrap_or_default();
    assert!(
        user_message.contains("智能审计运行失败"),
        "failure fixture should keep a Chinese-readable diagnostic: {user_message}"
    );
}

#[test]
fn agentflow_fixture_matrix_rejects_static_origin_direct_findings() {
    let fixture = load_fixture("p1_static_origin_rejected_output.json");
    let findings = array_field(&fixture, "findings");

    assert_eq!(
        findings.len(),
        1,
        "negative fixture should contain one rejected candidate"
    );
    assert!(
        has_static_origin(&findings[0]),
        "negative fixture must exercise the static-origin rejection guard"
    );
}

#[test]
fn agentflow_fixture_matrix_keeps_native_artifacts_out_of_direct_findings() {
    let fixture = load_fixture("p1_native_artifacts_only_output.json");

    assert_importable_agentflow_output(&fixture);
    assert!(array_field(&fixture, "findings").is_empty());
    assert_eq!(array_field(&fixture, "native_artifacts").len(), 2);
    assert_eq!(
        fixture
            .get("summary")
            .and_then(|summary| summary.get("direct_findings_count"))
            .and_then(Value::as_i64),
        Some(0),
        "native AgentFlow artifacts are evidence attachments, not direct findings"
    );
}
