use std::collections::HashSet;
use std::path::PathBuf;

use anyhow::{bail, Result};

use super::contracts::AgentRole;

pub fn agents_root() -> PathBuf {
    PathBuf::from("backend/agents")
}

pub fn agent_dir(role: &AgentRole) -> PathBuf {
    agents_root().join(role.to_string())
}

pub fn agent_manifest_path(role: &AgentRole) -> PathBuf {
    agent_dir(role).join("agent.toml")
}

pub fn hermes_seed_home(role: &AgentRole) -> PathBuf {
    agent_dir(role).join("hermes-home")
}

pub fn runtime_data_root(role: &AgentRole) -> PathBuf {
    agent_dir(role).join("data")
}

pub fn validate_isolation(roles: &[AgentRole]) -> Result<()> {
    let mut seen = HashSet::new();
    for role in roles {
        let data_root = runtime_data_root(role);
        let key = data_root.to_string_lossy().to_string();
        if !seen.insert(key.clone()) {
            bail!("isolation violation: two roles share data root {key}");
        }
    }
    Ok(())
}
