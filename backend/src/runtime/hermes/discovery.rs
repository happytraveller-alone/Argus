use std::path::Path;

use anyhow::{bail, Context, Result};

use super::contracts::AgentManifest;

pub fn discover_agents(base_path: &Path) -> Result<Vec<AgentManifest>> {
    let mut manifests = Vec::new();

    let entries = std::fs::read_dir(base_path)
        .with_context(|| format!("failed to read agents directory: {}", base_path.display()))?;

    for entry in entries {
        let entry = entry.context("failed to read directory entry")?;
        let path = entry.path();

        if !path.is_dir() {
            continue;
        }

        let manifest_path = path.join("agent.toml");
        if !manifest_path.exists() {
            continue;
        }

        let content = std::fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read {}", manifest_path.display()))?;

        let manifest: AgentManifest = toml::from_str(&content)
            .with_context(|| format!("failed to parse {}", manifest_path.display()))?;

        validate_manifest(&manifest)
            .with_context(|| format!("invalid manifest at {}", manifest_path.display()))?;

        manifests.push(manifest);
    }

    Ok(manifests)
}

fn validate_manifest(manifest: &AgentManifest) -> Result<()> {
    if manifest.id.is_empty() {
        bail!("manifest id is empty");
    }
    if manifest.image.is_empty() {
        bail!("manifest image is empty");
    }
    if manifest.container_name.is_empty() {
        bail!("manifest container_name is empty");
    }
    if manifest.input_contract.fields.is_empty() {
        bail!("manifest input_contract.fields is empty");
    }
    if manifest.output_contract.fields.is_empty() {
        bail!("manifest output_contract.fields is empty");
    }
    Ok(())
}
