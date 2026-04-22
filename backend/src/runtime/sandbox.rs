use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

pub const MAX_RETAINED_LOG_CHARS: usize = 12_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SandboxRunSpec {
    pub image: String,
    pub command: Vec<String>,
    pub workspace_dir: String,
    pub working_dir: String,
    pub timeout_seconds: u64,
    pub memory_limit: String,
    pub cpu_limit: f64,
    pub network_mode: String,
    pub read_only: bool,
    pub user: String,
    pub cap_drop: Vec<String>,
    pub security_opt: Vec<String>,
    pub env: BTreeMap<String, String>,
    pub volumes: BTreeMap<String, BTreeMap<String, String>>,
    pub tmpfs: BTreeMap<String, String>,
    pub expected_exit_codes: BTreeSet<i32>,
    pub auto_remove: bool,
    pub detach: bool,
}

impl SandboxRunSpec {
    pub fn with_defaults(
        image: &str,
        command: Vec<String>,
        workspace_dir: &str,
    ) -> Result<Self, String> {
        let spec = Self {
            image: image.to_string(),
            command,
            workspace_dir: workspace_dir.to_string(),
            working_dir: "/workspace".to_string(),
            timeout_seconds: 60,
            memory_limit: "512m".to_string(),
            cpu_limit: 1.0,
            network_mode: "none".to_string(),
            read_only: false,
            user: "1000:1000".to_string(),
            cap_drop: vec!["ALL".to_string()],
            security_opt: vec!["no-new-privileges:true".to_string()],
            env: BTreeMap::new(),
            volumes: BTreeMap::new(),
            tmpfs: BTreeMap::new(),
            expected_exit_codes: BTreeSet::from([0]),
            auto_remove: false,
            detach: true,
        };
        spec.validate()?;
        Ok(spec)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.image.trim().is_empty() {
            return Err("image is required".to_string());
        }
        if self.workspace_dir.trim().is_empty() {
            return Err("workspace_dir is required".to_string());
        }
        if self.timeout_seconds == 0 {
            return Err("timeout_seconds must be positive".to_string());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SandboxRunResult {
    pub success: bool,
    pub exit_code: i32,
    pub error: Option<String>,
    pub stdout: String,
    pub stderr: String,
    pub image: String,
    pub image_candidates: Vec<String>,
    pub stdout_path: Option<String>,
    pub stderr_path: Option<String>,
    pub runner_meta_path: Option<String>,
    pub duration_seconds: f64,
    pub container_id: Option<String>,
    pub workspace_dir: Option<String>,
}

impl SandboxRunResult {
    pub fn has_output(&self) -> bool {
        !self.stdout.is_empty() || !self.stderr.is_empty()
    }
}

pub fn truncate_log_text(text: &str) -> String {
    if text.len() <= MAX_RETAINED_LOG_CHARS {
        return text.to_string();
    }

    let tail_chars = MAX_RETAINED_LOG_CHARS.saturating_sub(64);
    let omitted_chars = text.len().saturating_sub(tail_chars);
    format!(
        "[truncated {omitted_chars} chars]\n{}",
        &text[text.len() - tail_chars..]
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::{truncate_log_text, SandboxRunResult, SandboxRunSpec, MAX_RETAINED_LOG_CHARS};

    #[test]
    fn sandbox_run_spec_validation_matches_retired_python_contract() {
        let spec =
            SandboxRunSpec::with_defaults("alpine:latest", vec!["echo".to_string()], "/tmp/test")
                .expect("default spec should validate");
        assert_eq!(spec.network_mode, "none");
        assert!(spec.cap_drop.iter().any(|item| item == "ALL"));

        let invalid = SandboxRunSpec {
            image: String::new(),
            expected_exit_codes: BTreeSet::from([0]),
            ..spec.clone()
        };
        assert_eq!(invalid.validate(), Err("image is required".to_string()));
    }

    #[test]
    fn sandbox_run_result_has_output_matches_python_behavior() {
        let result = SandboxRunResult {
            success: true,
            exit_code: 0,
            error: None,
            stdout: "out".to_string(),
            stderr: String::new(),
            image: "alpine".to_string(),
            image_candidates: Vec::new(),
            stdout_path: None,
            stderr_path: None,
            runner_meta_path: None,
            duration_seconds: 0.0,
            container_id: None,
            workspace_dir: None,
        };
        assert!(result.has_output());
    }

    #[test]
    fn truncate_log_text_caps_large_outputs() {
        let text = "x".repeat(MAX_RETAINED_LOG_CHARS + 100);
        let truncated = truncate_log_text(&text);
        assert!(truncated.len() <= MAX_RETAINED_LOG_CHARS + 32);
        assert!(truncated.contains("[truncated"));
    }
}
