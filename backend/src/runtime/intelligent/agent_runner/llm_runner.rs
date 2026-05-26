use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use async_trait::async_trait;
use serde_json::json;
use tracing::info_span;

use super::{
    AgentRunConfig, AgentRunResult, AgentRunner, AgentToolDef, LlmProtocol, TokenUsage, ToolResult,
};

#[async_trait]
pub trait ToolExecutor: Send + Sync {
    async fn execute(&self, tool_name: &str, input: serde_json::Value) -> ToolResult;
}

pub struct LlmAgentRunner {
    client: reqwest::Client,
    base_url: String,
    api_key: String,
    protocol: LlmProtocol,
    tool_executor: Arc<dyn ToolExecutor>,
}

impl LlmAgentRunner {
    pub fn new(
        base_url: impl Into<String>,
        api_key: impl Into<String>,
        protocol: LlmProtocol,
        tool_executor: Arc<dyn ToolExecutor>,
    ) -> Self {
        Self {
            client: reqwest::Client::new(),
            base_url: base_url.into(),
            api_key: api_key.into(),
            protocol,
            tool_executor,
        }
    }

    fn build_endpoint(&self) -> String {
        let base = self.base_url.trim_end_matches('/');
        match self.protocol {
            LlmProtocol::AnthropicCompatible => format!("{base}/v1/messages"),
            LlmProtocol::OpenAiCompatible => format!("{base}/v1/chat/completions"),
        }
    }

    fn build_request_anthropic(
        model: &str,
        system_prompt: &str,
        messages: &[serde_json::Value],
        tools: &[AgentToolDef],
    ) -> serde_json::Value {
        let tool_defs: Vec<serde_json::Value> = tools
            .iter()
            .map(|t| {
                json!({
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                })
            })
            .collect();
        json!({
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
            "tools": tool_defs,
        })
    }

    fn build_request_openai(
        model: &str,
        _system_prompt: &str,
        messages: &[serde_json::Value],
        tools: &[AgentToolDef],
    ) -> serde_json::Value {
        let tool_defs: Vec<serde_json::Value> = tools
            .iter()
            .map(|t| {
                json!({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                })
            })
            .collect();
        json!({
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": tool_defs,
        })
    }

    async fn post_with_retry(
        &self,
        url: &str,
        body: &serde_json::Value,
        max_retries: u32,
        turn_timeout: Duration,
    ) -> Result<serde_json::Value> {
        let mut attempt = 0u32;
        loop {
            let resp = tokio::time::timeout(turn_timeout, async {
                let mut req = self
                    .client
                    .post(url)
                    .header("content-type", "application/json");
                req = match self.protocol {
                    LlmProtocol::AnthropicCompatible => req
                        .header("x-api-key", &self.api_key)
                        .header("anthropic-version", "2023-06-01"),
                    LlmProtocol::OpenAiCompatible => {
                        req.header("Authorization", format!("Bearer {}", self.api_key))
                    }
                };
                req.json(body).send().await
            })
            .await
            .context("turn timeout")??;

            let status = resp.status();
            if status.is_success() {
                return resp
                    .json::<serde_json::Value>()
                    .await
                    .context("parse response");
            }
            let retry_eligible = status.as_u16() == 429 || status.is_server_error();
            if retry_eligible && attempt < max_retries {
                let wait_secs = {
                    let ra = resp
                        .headers()
                        .get("retry-after")
                        .and_then(|v| v.to_str().ok())
                        .and_then(|s| s.parse::<u64>().ok());
                    ra.unwrap_or(1u64 << attempt)
                };
                tracing::warn!(status = %status, attempt, wait_secs, "retrying after transient error");
                tokio::time::sleep(Duration::from_secs(wait_secs)).await;
                attempt += 1;
                continue;
            }
            anyhow::bail!("HTTP {status}");
        }
    }

    async fn run_turn_anthropic(
        &self,
        messages: &mut Vec<serde_json::Value>,
        model: &str,
        system_prompt: &str,
        tools: &[AgentToolDef],
        total_tokens: &mut TokenUsage,
        url: &str,
        config: &AgentRunConfig,
        turn: u32,
    ) -> Result<Option<AgentRunResult>> {
        let turn_timeout = Duration::from_millis(config.timeout_per_turn_ms);
        let body = Self::build_request_anthropic(model, system_prompt, messages, tools);
        let resp = self
            .post_with_retry(url, &body, config.max_retries, turn_timeout)
            .await
            .with_context(|| format!("turn {turn} request failed"))?;

        if let Some(usage) = resp.get("usage") {
            total_tokens.input_tokens += usage["input_tokens"].as_u64().unwrap_or(0);
            total_tokens.output_tokens += usage["output_tokens"].as_u64().unwrap_or(0);
        }

        let stop_reason = resp["stop_reason"].as_str().unwrap_or("");
        let content_blocks = resp["content"].as_array().cloned().unwrap_or_default();

        match stop_reason {
            "end_turn" | "max_tokens" => {
                if stop_reason == "max_tokens" {
                    tracing::warn!(turn, "stop_reason=max_tokens; extracting partial result");
                }
                let text = content_blocks
                    .iter()
                    .find(|b| b["type"] == "text")
                    .and_then(|b| b["text"].as_str())
                    .unwrap_or("{}");
                let payload = serde_json::from_str::<serde_json::Value>(text)
                    .unwrap_or_else(|_| json!({"raw": text}));
                return Ok(Some(AgentRunResult {
                    payload,
                    turns_used: turn + 1,
                    tokens: total_tokens.clone(),
                }));
            }
            "tool_use" => {
                messages.push(json!({"role": "assistant", "content": content_blocks.clone()}));
                let mut tool_results: Vec<serde_json::Value> = Vec::new();
                for block in &content_blocks {
                    if block["type"] != "tool_use" {
                        continue;
                    }
                    let tool_use_id = block["id"].as_str().unwrap_or("").to_string();
                    let tool_name = block["name"].as_str().unwrap_or("").to_string();
                    let input = block["input"].clone();
                    let result = self.tool_executor.execute(&tool_name, input).await;
                    tool_results.push(json!({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }));
                }
                messages.push(json!({"role": "user", "content": tool_results}));
                Ok(None)
            }
            other => anyhow::bail!("unexpected stop_reason: {other}"),
        }
    }

    async fn run_turn_openai(
        &self,
        messages: &mut Vec<serde_json::Value>,
        model: &str,
        tools: &[AgentToolDef],
        total_tokens: &mut TokenUsage,
        url: &str,
        config: &AgentRunConfig,
        turn: u32,
    ) -> Result<Option<AgentRunResult>> {
        let turn_timeout = Duration::from_millis(config.timeout_per_turn_ms);
        let body = Self::build_request_openai(model, "", messages, tools);
        let resp = self
            .post_with_retry(url, &body, config.max_retries, turn_timeout)
            .await
            .with_context(|| format!("turn {turn} request failed"))?;

        if let Some(usage) = resp.get("usage") {
            total_tokens.input_tokens += usage["prompt_tokens"].as_u64().unwrap_or(0);
            total_tokens.output_tokens += usage["completion_tokens"].as_u64().unwrap_or(0);
        }

        let choice = &resp["choices"][0];
        let finish_reason = choice["finish_reason"].as_str().unwrap_or("");
        let message = &choice["message"];

        match finish_reason {
            "stop" | "length" => {
                if finish_reason == "length" {
                    tracing::warn!(turn, "finish_reason=length; extracting partial result");
                }
                let text = message["content"].as_str().unwrap_or("{}");
                let payload = serde_json::from_str::<serde_json::Value>(text)
                    .unwrap_or_else(|_| json!({"raw": text}));
                return Ok(Some(AgentRunResult {
                    payload,
                    turns_used: turn + 1,
                    tokens: total_tokens.clone(),
                }));
            }
            "tool_calls" => {
                messages.push(message.clone());
                let tool_calls = message["tool_calls"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default();
                for tc in &tool_calls {
                    let tool_call_id = tc["id"].as_str().unwrap_or("").to_string();
                    let tool_name = tc["function"]["name"].as_str().unwrap_or("").to_string();
                    let args_str = tc["function"]["arguments"].as_str().unwrap_or("{}");
                    let input: serde_json::Value =
                        serde_json::from_str(args_str).unwrap_or(json!({}));
                    let result = self.tool_executor.execute(&tool_name, input).await;
                    messages.push(json!({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result.content,
                    }));
                }
                Ok(None)
            }
            other => anyhow::bail!("unexpected finish_reason: {other}"),
        }
    }
}

#[async_trait]
impl AgentRunner for LlmAgentRunner {
    async fn run_agent(
        &self,
        stage: &str,
        system_prompt: &str,
        user_message: serde_json::Value,
        tools: &[AgentToolDef],
        config: &AgentRunConfig,
    ) -> Result<AgentRunResult> {
        let url = self.build_endpoint();

        let user_content = match &user_message {
            serde_json::Value::String(s) => match self.protocol {
                LlmProtocol::AnthropicCompatible => json!([{"type": "text", "text": s}]),
                LlmProtocol::OpenAiCompatible => json!(s),
            },
            other => other.clone(),
        };

        let mut messages: Vec<serde_json::Value> = match self.protocol {
            LlmProtocol::AnthropicCompatible => {
                vec![json!({"role": "user", "content": user_content})]
            }
            LlmProtocol::OpenAiCompatible => vec![
                json!({"role": "system", "content": system_prompt}),
                json!({"role": "user", "content": user_content}),
            ],
        };

        let mut total_tokens = TokenUsage::default();

        for turn in 0..config.max_turns {
            let span = info_span!("agent_turn", stage, turn_number = turn);
            let _enter = span.enter();

            let result = match self.protocol {
                LlmProtocol::AnthropicCompatible => {
                    self.run_turn_anthropic(
                        &mut messages,
                        &config.model,
                        system_prompt,
                        tools,
                        &mut total_tokens,
                        &url,
                        config,
                        turn,
                    )
                    .await?
                }
                LlmProtocol::OpenAiCompatible => {
                    self.run_turn_openai(
                        &mut messages,
                        &config.model,
                        tools,
                        &mut total_tokens,
                        &url,
                        config,
                        turn,
                    )
                    .await?
                }
            };

            if let Some(final_result) = result {
                return Ok(final_result);
            }
        }

        anyhow::bail!("agent exceeded max_turns={}", config.max_turns)
    }
}
