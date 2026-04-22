use backend_rust::runtime::finding_payload::{
    execute, execute_from_request_path, normalize_push_finding_payload, FindingPayloadOperation,
};
use serde_json::json;
use std::fs;
use tempfile::TempDir;

#[test]
fn finding_payload_operation_requires_known_selector() {
    assert_eq!(
        serde_json::to_value(FindingPayloadOperation::from_cli("normalize").unwrap()).unwrap(),
        json!("normalize")
    );
    assert!(FindingPayloadOperation::from_cli("unknown").is_err());
}

#[test]
fn execute_from_request_path_rejects_invalid_json() {
    let temp_dir = TempDir::new().expect("temp dir");
    let request_path = temp_dir.path().join("request.json");
    fs::write(&request_path, "{invalid").expect("write request");

    let result = execute_from_request_path(FindingPayloadOperation::Normalize, &request_path);

    assert_eq!(result["ok"], false);
    assert!(result["error"]
        .as_str()
        .unwrap_or_default()
        .contains("invalid_finding_payload_request"));
}

#[test]
fn execute_from_request_path_returns_normalized_round_trip_for_valid_request() {
    let temp_dir = TempDir::new().expect("temp dir");
    let request_path = temp_dir.path().join("request.json");
    fs::write(
        &request_path,
        serde_json::to_string_pretty(&json!({
            "payload": {
                "finding": {
                    "file_path": "src/auth.py",
                    "line": 18,
                    "title": "SQL injection",
                    "description": "bad",
                    "type": "sql_injection"
                }
            },
            "ordering": {
                "payload": ["finding"],
                "payload.finding": [
                    "file_path",
                    "line",
                    "title",
                    "description",
                    "type"
                ]
            }
        }))
        .expect("serialize request"),
    )
    .expect("write request");

    let result = execute_from_request_path(FindingPayloadOperation::Normalize, &request_path);

    assert_eq!(result["ok"], true);
    assert_eq!(result["normalized_payload"]["file_path"], "src/auth.py");
    assert_eq!(result["normalized_payload"]["line_start"], 18);
    assert_eq!(result["normalized_payload"]["vulnerability_type"], "sql_injection");
    assert_eq!(result["repair_map"]["line"], "line_start");
}

#[test]
fn normalize_payload_repairs_nested_envelope_aliases_and_extra_metadata() {
    let (normalized, repair_map) = normalize_push_finding_payload(&json!({
        "finding": {
            "file_path": "src/auth.py",
            "line": 18,
            "end_line": 21,
            "title": "SQL injection",
            "description": "bad",
            "type": "sql_injection",
            "code": "cursor.execute(query + user_input)",
            "recommendation": "use parameters",
            "custom_extra": "custom-value"
        }
    }));

    assert_eq!(normalized["line_start"], 18);
    assert_eq!(normalized["line_end"], 21);
    assert_eq!(normalized["vulnerability_type"], "sql_injection");
    assert_eq!(normalized["code_snippet"], "cursor.execute(query + user_input)");
    assert_eq!(normalized["suggestion"], "use parameters");
    assert_eq!(
        normalized["finding_metadata"]["extra_tool_input"]["custom_extra"],
        "custom-value"
    );
    assert_eq!(repair_map["line"], "line_start");
    assert_eq!(repair_map["end_line"], "line_end");
    assert_eq!(repair_map["type"], "vulnerability_type");
    assert_eq!(repair_map["code"], "code_snippet");
    assert_eq!(repair_map["recommendation"], "suggestion");
    assert_eq!(
        repair_map["__extra.custom_extra"],
        "finding_metadata.extra_tool_input.custom_extra"
    );
}

#[test]
fn execute_returns_normalized_payload_and_repair_map() {
    let result = execute(
        FindingPayloadOperation::Normalize,
        json!({
            "payload": {
                "finding": {
                    "file_path": "src/auth.py",
                    "line": 18,
                    "title": "SQL injection",
                    "description": "bad",
                    "type": "sql_injection"
                }
            }
        }),
    );

    assert_eq!(result["ok"], true);
    assert_eq!(result["normalized_payload"]["line_start"], 18);
    assert_eq!(result["normalized_payload"]["vulnerability_type"], "sql_injection");
    assert_eq!(result["repair_map"]["line"], "line_start");
}

#[test]
fn execute_uses_ordering_hints_for_extra_tool_input_truncation() {
    let result = execute(
        FindingPayloadOperation::Normalize,
        json!({
            "payload": {
                "k0": "x".repeat(600),
                "k1": "x".repeat(600),
                "k2": "x".repeat(600),
                "k3": "x".repeat(600),
                "k4": "x".repeat(600),
                "k5": "x".repeat(600),
                "k6": "x".repeat(600),
                "k7": "x".repeat(600),
                "k8": "x".repeat(600),
                "k9": "x".repeat(600),
                "k10": "x".repeat(600),
                "k11": "x".repeat(600),
                "k12": "x".repeat(600),
                "k13": "x".repeat(600),
                "k14": "x".repeat(600),
                "k15": "x".repeat(600),
                "k16": "x".repeat(600),
                "k17": "x".repeat(600),
                "k18": "x".repeat(600),
                "k19": "x".repeat(600),
                "k20": "x".repeat(600),
                "k21": "x".repeat(600),
                "k22": "x".repeat(600),
                "k23": "x".repeat(600),
                "k24": "x".repeat(600),
                "file_path": "src/huge.py",
                "title": "huge",
                "description": "huge",
                "vulnerability_type": "demo"
            },
            "ordering": {
                "payload": [
                    "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9",
                    "k10", "k11", "k12", "k13", "k14", "k15", "k16", "k17", "k18",
                    "k19", "k20", "k21", "k22", "k23", "k24",
                    "file_path", "title", "description", "vulnerability_type"
                ]
            }
        }),
    );

    let extra = result["normalized_payload"]["finding_metadata"]["extra_tool_input"]
        .as_object()
        .expect("extra_tool_input object");
    assert!(result["normalized_payload"]["finding_metadata"]["extra_tool_input_truncated"]
        .as_bool()
        .unwrap_or(false));
    for kept in 0..=12 {
        assert!(extra.contains_key(&format!("k{kept}")));
    }
    assert!(!extra.contains_key("k13"));
}
