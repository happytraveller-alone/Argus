use std::fs;
use tempfile::TempDir;

fn write_agent_toml(dir: &std::path::Path, role: &str) {
    let content = format!(
        r#"id = "{role}"
role = "{role}"
image = "vulhunter/hermes-agent:latest"
container_name = "hermes-{role}"
enabled = true
dispatch_timeout_seconds = 300
terminal_cwd = "/scan"
project_mount = "/scan"
artifacts_dir = "artifacts"
runtime_home_dir = "data"

[input_contract]
fields = ["task_id", "project_id", "correlation_id", "payload"]

[output_contract]
fields = ["status", "summary", "structured_outputs", "diagnostics"]

[healthcheck]
command = "hermes --version"
interval_seconds = 30
"#
    );
    let role_dir = dir.join(role);
    fs::create_dir_all(&role_dir).unwrap();
    fs::write(role_dir.join("agent.toml"), content).unwrap();
}

#[test]
fn discovers_four_agents() {
    let tmp = TempDir::new().unwrap();
    for role in &["recon", "analysis", "verification", "report"] {
        write_agent_toml(tmp.path(), role);
    }

    let manifests = backend_rust::runtime::hermes::discovery::discover_agents(tmp.path()).unwrap();
    assert_eq!(manifests.len(), 4);
}

#[test]
fn only_known_roles_accepted() {
    let tmp = TempDir::new().unwrap();
    write_agent_toml(tmp.path(), "recon");

    let bad_content = r#"id = "unknown"
role = "unknown_role"
image = "vulhunter/hermes-agent:latest"
container_name = "hermes-unknown"
enabled = true
dispatch_timeout_seconds = 300
terminal_cwd = "/scan"
project_mount = "/scan"
artifacts_dir = "artifacts"
runtime_home_dir = "data"

[input_contract]
fields = ["task_id"]

[output_contract]
fields = ["status"]

[healthcheck]
command = "hermes --version"
interval_seconds = 30
"#;
    let bad_dir = tmp.path().join("unknown_role");
    fs::create_dir_all(&bad_dir).unwrap();
    fs::write(bad_dir.join("agent.toml"), bad_content).unwrap();

    let result = backend_rust::runtime::hermes::discovery::discover_agents(tmp.path());
    assert!(result.is_err(), "expected error for unknown role");
}

#[test]
fn malformed_agent_toml_fails_explicitly() {
    let tmp = TempDir::new().unwrap();
    let bad_dir = tmp.path().join("recon");
    fs::create_dir_all(&bad_dir).unwrap();
    fs::write(bad_dir.join("agent.toml"), "this is not valid toml ][").unwrap();

    let result = backend_rust::runtime::hermes::discovery::discover_agents(tmp.path());
    assert!(result.is_err(), "expected error for malformed toml");
}
