use std::path::Path;

use anyhow::{Context, Result};

use super::contracts::AgentRole;
use super::layout::runtime_data_root;

pub struct BootstrapResult {
    pub seeded: bool,
    pub files_copied: Vec<String>,
}

const REQUIRED_SEED_FILES: &[&str] = &["config.yaml", ".env", "SOUL.md"];

pub fn bootstrap_agent(role: &AgentRole, base_path: &Path) -> Result<BootstrapResult> {
    let role_dir = base_path.join(role.to_string());
    let seed_home = role_dir.join("hermes-home");
    let data_dir = role_dir.join("data");

    std::fs::create_dir_all(&data_dir)
        .with_context(|| format!("failed to create data dir: {}", data_dir.display()))?;

    let mut files_copied = Vec::new();
    let mut any_missing = false;

    for filename in REQUIRED_SEED_FILES {
        let dest = data_dir.join(filename);
        if dest.exists() {
            continue;
        }
        any_missing = true;

        // Try .env.example as fallback for .env
        let src_name = if *filename == ".env" {
            ".env.example"
        } else {
            filename
        };
        let src = seed_home.join(src_name);

        if src.exists() {
            std::fs::copy(&src, &dest).with_context(|| {
                format!("failed to copy {} to {}", src.display(), dest.display())
            })?;
            files_copied.push(filename.to_string());
        }
    }

    // Ensure terminal.cwd directory exists (mapped to data/)
    let _ = runtime_data_root(role);

    Ok(BootstrapResult {
        seeded: any_missing,
        files_copied,
    })
}
