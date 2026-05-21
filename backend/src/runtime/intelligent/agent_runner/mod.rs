pub mod llm_runner;
pub mod podman;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LlmProtocol {
    AnthropicCompatible,
    OpenAiCompatible,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentTool {
    Read { path: String },
    Grep { pattern: String, path: Option<String> },
    Glob { pattern: String },
    Exec { command: String, timeout_ms: Option<u64> },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub tool_use_id: String,
    pub content: String,
    pub is_error: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentToolDef {
    pub name: String,
    pub description: String,
    pub input_schema: serde_json::Value,
}

#[derive(Debug, Clone)]
pub struct AgentRunConfig {
    pub max_turns: u32,
    pub model: String,
    pub protocol: LlmProtocol,
    pub timeout_per_turn_ms: u64,
    pub max_retries: u32,
}

impl Default for AgentRunConfig {
    fn default() -> Self {
        Self {
            max_turns: 25,
            model: "claude-sonnet-4-6-20250514".to_string(),
            protocol: LlmProtocol::OpenAiCompatible,
            timeout_per_turn_ms: 120_000,
            max_retries: 3,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct TokenUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
}

#[derive(Debug, Clone)]
pub struct AgentRunResult {
    pub payload: serde_json::Value,
    pub turns_used: u32,
    pub tokens: TokenUsage,
}

#[async_trait]
pub trait AgentRunner: Send + Sync {
    async fn run_agent(
        &self,
        stage: &str,
        system_prompt: &str,
        user_message: serde_json::Value,
        tools: &[AgentToolDef],
        config: &AgentRunConfig,
    ) -> anyhow::Result<AgentRunResult>;
}

pub fn standard_tool_defs(tools: &[&str]) -> Vec<AgentToolDef> {
    tools
        .iter()
        .filter_map(|name| match *name {
            "Read" => Some(AgentToolDef {
                name: "read_file".to_string(),
                description: "Read a file from the workspace. Returns full file content."
                    .to_string(),
                input_schema: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path from workspace root"}
                    },
                    "required": ["path"]
                }),
            }),
            "Grep" => Some(AgentToolDef {
                name: "grep".to_string(),
                description: "Search for a regex pattern in files. Returns matching lines with file paths and line numbers.".to_string(),
                input_schema: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search for"},
                        "path": {"type": "string", "description": "Optional path to scope the search"}
                    },
                    "required": ["pattern"]
                }),
            }),
            "Glob" => Some(AgentToolDef {
                name: "glob".to_string(),
                description: "List files matching a glob pattern.".to_string(),
                input_schema: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.rs')"}
                    },
                    "required": ["pattern"]
                }),
            }),
            "Exec" => Some(AgentToolDef {
                name: "exec".to_string(),
                description: "Execute a shell command in the sandbox. Use for compiling/running PoC code.".to_string(),
                input_schema: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "timeout_ms": {"type": "integer", "description": "Timeout in milliseconds (default 30000)"}
                    },
                    "required": ["command"]
                }),
            }),
            _ => None,
        })
        .collect()
}
