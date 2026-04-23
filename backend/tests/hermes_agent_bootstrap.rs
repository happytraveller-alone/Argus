use std::fs;
use tempfile::TempDir;

use backend_rust::runtime::hermes::bootstrap::bootstrap_agent;
use backend_rust::runtime::hermes::contracts::AgentRole;

fn setup_agent_dir(base: &std::path::Path, role: &str) {
    let role_dir = base.join(role);
    let hermes_home = role_dir.join("hermes-home");
    let data_dir = role_dir.join("data");
    fs::create_dir_all(&hermes_home).unwrap();
    fs::create_dir_all(&data_dir).unwrap();
    fs::write(hermes_home.join("config.yaml"), "model: claude-opus-4-7\n").unwrap();
    fs::write(hermes_home.join(".env.example"), "ANTHROPIC_API_KEY=\n").unwrap();
    fs::write(hermes_home.join("SOUL.md"), "# Soul\n").unwrap();
}

#[test]
fn first_boot_copies_seed_files() {
    let tmp = TempDir::new().unwrap();
    setup_agent_dir(tmp.path(), "recon");

    let role = AgentRole::Recon;
    let result = bootstrap_agent(&role, tmp.path()).unwrap();

    assert!(result.seeded);
    assert!(result.files_copied.contains(&"config.yaml".to_string()));
    assert!(result.files_copied.contains(&"SOUL.md".to_string()));

    let data_dir = tmp.path().join("recon").join("data");
    assert!(data_dir.join("config.yaml").exists());
    assert!(data_dir.join("SOUL.md").exists());
}

#[test]
fn second_boot_does_not_clobber_existing_state() {
    let tmp = TempDir::new().unwrap();
    setup_agent_dir(tmp.path(), "recon");

    let role = AgentRole::Recon;

    bootstrap_agent(&role, tmp.path()).unwrap();

    let data_config = tmp.path().join("recon").join("data").join("config.yaml");
    fs::write(&data_config, "model: modified\n").unwrap();

    let result = bootstrap_agent(&role, tmp.path()).unwrap();

    assert!(!result.seeded);
    assert!(result.files_copied.is_empty());

    let content = fs::read_to_string(&data_config).unwrap();
    assert_eq!(content, "model: modified\n");
}

#[test]
fn required_seed_files_enforced() {
    let tmp = TempDir::new().unwrap();
    let role_dir = tmp.path().join("recon");
    let hermes_home = role_dir.join("hermes-home");
    let data_dir = role_dir.join("data");
    fs::create_dir_all(&hermes_home).unwrap();
    fs::create_dir_all(&data_dir).unwrap();
    fs::write(hermes_home.join("config.yaml"), "model: claude-opus-4-7\n").unwrap();

    let role = AgentRole::Recon;
    let result = bootstrap_agent(&role, tmp.path()).unwrap();

    assert!(result.files_copied.contains(&"config.yaml".to_string()));
    assert!(!result.files_copied.contains(&"SOUL.md".to_string()));
}
