use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::fs;

use super::{
    importer::validate_no_static_candidates,
    pipeline::{render_p1_pipeline, validate_p1_pipeline},
};
use crate::llm::is_supported_protocol_provider;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PreflightCheck {
    pub name: String,
    pub ok: bool,
    pub reason_code: Option<String>,
    pub message: String,
    pub metadata: Option<Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PreflightReport {
    pub ok: bool,
    pub stage: Option<String>,
    pub reason_code: Option<String>,
    pub message: String,
    pub checks: Vec<PreflightCheck>,
    pub metadata: Value,
}

#[derive(Clone, Debug, Default)]
pub struct PreflightInput<'a> {
    pub llm_config: &'a Value,
    pub audit_scope: Option<&'a Value>,
    pub runner_command: Option<&'a str>,
    pub pipeline_path: Option<&'a Path>,
    pub output_dir: Option<&'a Path>,
    pub max_parallel_nodes: usize,
}

pub async fn run_preflight(input: PreflightInput<'_>) -> PreflightReport {
    let mut checks = Vec::new();
    checks.push(check_llm_config(input.llm_config));
    if let Some(scope) = input.audit_scope {
        checks.push(match validate_no_static_candidates(scope) {
            Ok(()) => pass("static_input_gate", "未检测到静态扫描候选输入"),
            Err(error) => fail("static_input_gate", error.reason_code, error.message),
        });
    }
    checks.push(check_runner_command(input.runner_command));
    checks.push(check_pipeline(input.pipeline_path).await);
    checks.push(check_output_dir(input.output_dir).await);
    checks.push(check_resource_budget(input.max_parallel_nodes));

    let first_fail = checks.iter().find(|check| !check.ok);
    PreflightReport {
        ok: first_fail.is_none(),
        stage: first_fail.map(|check| check.name.clone()),
        reason_code: first_fail.and_then(|check| check.reason_code.clone()),
        message: first_fail
            .map(|check| check.message.clone())
            .unwrap_or_else(|| "AgentFlow 智能审计预检通过。".to_string()),
        checks,
        metadata: json!({
            "runtime": "agentflow",
            "serve_enabled": false,
            "remote_target": false,
            "dynamic_experts": false,
        }),
    }
}

fn check_llm_config(config: &Value) -> PreflightCheck {
    let provider = config
        .get("llmProvider")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let model = config
        .get("llmModel")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let base_url = config
        .get("llmBaseUrl")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let api_key = config
        .get("llmApiKey")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let mut missing = Vec::new();
    if model.trim().is_empty() {
        missing.push("model");
    }
    if base_url.trim().is_empty() {
        missing.push("baseUrl");
    }
    if !is_supported_protocol_provider(provider) {
        missing.push("provider");
    }
    if api_key.trim().is_empty() {
        missing.push("apiKey");
    }
    if missing.is_empty() {
        pass("llm_config", "LLM 配置具备智能审计启动所需字段")
    } else {
        PreflightCheck {
            name: "llm_config".to_string(),
            ok: false,
            reason_code: Some("missing_fields".to_string()),
            message: format!(
                "智能审计初始化失败：LLM 缺少必填配置 {}。",
                missing.join("、")
            ),
            metadata: Some(json!({"missing_fields": missing})),
        }
    }
}

fn check_runner_command(command: Option<&str>) -> PreflightCheck {
    match command.map(str::trim).filter(|value| !value.is_empty()) {
        Some(command) => pass_with_metadata(
            "runner",
            "AgentFlow runner 命令已配置",
            json!({"command": command}),
        ),
        None => fail(
            "runner",
            "runner_missing",
            "AgentFlow runner 未配置，无法启动智能审计任务",
        ),
    }
}

async fn check_pipeline(path: Option<&Path>) -> PreflightCheck {
    if let Err(error) = validate_p1_pipeline(&render_p1_pipeline()) {
        return fail("pipeline", error.reason_code, error.message);
    }
    if let Some(path) = path {
        if fs::metadata(path).await.is_err() {
            return fail(
                "pipeline",
                "pipeline_invalid",
                format!("AgentFlow pipeline 文件不存在：{}", path.display()),
            );
        }
    }
    pass("pipeline", "AgentFlow P1 pipeline 合同有效")
}

async fn check_output_dir(path: Option<&Path>) -> PreflightCheck {
    let Some(path) = path else {
        return fail(
            "output_dir",
            "output_dir_unwritable",
            "AgentFlow 输出目录未配置",
        );
    };
    match fs::create_dir_all(path).await.and_then(|_| {
        std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(path.join(".argus-write-test"))
            .map(|_| ())
    }) {
        Ok(()) => {
            let _ = fs::remove_file(path.join(".argus-write-test")).await;
            pass("output_dir", "AgentFlow 输出目录可写")
        }
        Err(error) => fail(
            "output_dir",
            "output_dir_unwritable",
            format!("AgentFlow 输出目录不可写：{error}"),
        ),
    }
}

fn check_resource_budget(max_parallel_nodes: usize) -> PreflightCheck {
    if max_parallel_nodes == 0 {
        fail(
            "resource",
            "resource_unavailable",
            "AgentFlow 并发资源预算为 0，无法启动智能审计",
        )
    } else {
        pass_with_metadata(
            "resource",
            "AgentFlow 资源预算满足 P1 启动要求",
            json!({"max_parallel_nodes": max_parallel_nodes}),
        )
    }
}

fn pass(name: &str, message: &str) -> PreflightCheck {
    PreflightCheck {
        name: name.to_string(),
        ok: true,
        reason_code: None,
        message: message.to_string(),
        metadata: None,
    }
}

fn pass_with_metadata(name: &str, message: &str, metadata: Value) -> PreflightCheck {
    PreflightCheck {
        name: name.to_string(),
        ok: true,
        reason_code: None,
        message: message.to_string(),
        metadata: Some(metadata),
    }
}

fn fail(name: &str, reason_code: &str, message: impl Into<String>) -> PreflightCheck {
    PreflightCheck {
        name: name.to_string(),
        ok: false,
        reason_code: Some(reason_code.to_string()),
        message: message.into(),
        metadata: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn agentflow_preflight_reports_runner_missing_without_leaking_api_key() {
        let llm = json!({"llmProvider": "openai_compatible", "llmModel": "gpt-5", "llmBaseUrl": "https://api.example/v1", "llmApiKey": "sk-secret"});
        let report = run_preflight(PreflightInput {
            llm_config: &llm,
            runner_command: None,
            max_parallel_nodes: 1,
            ..Default::default()
        })
        .await;
        assert!(!report.ok);
        assert_eq!(report.reason_code.as_deref(), Some("runner_missing"));
        assert!(!serde_json::to_string(&report)
            .unwrap()
            .contains("sk-secret"));
    }

    #[tokio::test]
    async fn agentflow_preflight_rejects_forbidden_static_scope() {
        let llm = json!({"llmProvider": "openai_compatible", "llmModel": "gpt-5", "llmBaseUrl": "https://api.example/v1", "llmApiKey": "sk-secret"});
        let scope = json!({"candidate_origin": "phpstan"});
        let report = run_preflight(PreflightInput {
            llm_config: &llm,
            audit_scope: Some(&scope),
            runner_command: Some("agentflow"),
            max_parallel_nodes: 1,
            output_dir: Some(Path::new("/tmp")),
            ..Default::default()
        })
        .await;
        assert!(!report.ok);
        assert_eq!(
            report.reason_code.as_deref(),
            Some("forbidden_static_input")
        );
    }
}
