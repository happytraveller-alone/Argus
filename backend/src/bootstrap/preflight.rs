use std::{process::Command, sync::Arc};

use anyhow::{anyhow, Result};
use tokio::{sync::Semaphore, task::JoinSet, time::{timeout, Duration}};

use crate::{config::AppConfig, state::{BootstrapStatus, RunnerPreflightCheckStatus, RunnerPreflightStatus}};

#[derive(Clone, Debug)]
struct RunnerPreflightSpec {
    name: &'static str,
    image: String,
    command: Vec<String>,
}

pub async fn run(config: &AppConfig) -> Result<RunnerPreflightStatus> {
    if !config.runner_preflight_enabled {
        return Ok(RunnerPreflightStatus {
            status: "skipped".to_string(),
            enabled: false,
            strict: config.runner_preflight_strict,
            checks: Vec::new(),
            error: None,
        });
    }

    let specs = configured_specs(config);
    let semaphore = Arc::new(Semaphore::new(config.runner_preflight_max_concurrency.max(1)));
    let mut join_set = JoinSet::new();

    for spec in specs {
        let permit = semaphore.clone().acquire_owned().await?;
        let timeout_seconds = config.runner_preflight_timeout_seconds;
        join_set.spawn(async move {
            let _permit = permit;
            run_single_preflight(spec, timeout_seconds).await
        });
    }

    let mut checks = Vec::new();
    while let Some(result) = join_set.join_next().await {
        match result {
            Ok(check) => checks.push(check),
            Err(error) => {
                checks.push(RunnerPreflightCheckStatus {
                    name: "spawn".to_string(),
                    success: false,
                    exit_code: None,
                    error: Some(error.to_string()),
                });
            }
        }
    }

    checks.sort_by(|left, right| left.name.cmp(&right.name));
    let failure_messages = checks
        .iter()
        .filter(|check| !check.success)
        .map(|check| format!("{}: {}", check.name, check.error.clone().unwrap_or_else(|| "unknown".to_string())))
        .collect::<Vec<_>>();

    let mut status = RunnerPreflightStatus {
        status: BootstrapStatus::Ok.as_str().to_string(),
        enabled: true,
        strict: config.runner_preflight_strict,
        checks,
        error: None,
    };

    if !failure_messages.is_empty() {
        status.status = BootstrapStatus::Degraded.as_str().to_string();
        status.error = Some(failure_messages.join(", "));
    }

    Ok(status)
}

async fn run_single_preflight(
    spec: RunnerPreflightSpec,
    timeout_seconds: u64,
) -> RunnerPreflightCheckStatus {
    let timeout_result = timeout(
        Duration::from_secs(timeout_seconds.max(1)),
        tokio::task::spawn_blocking(move || run_single_preflight_sync(spec)),
    )
    .await;

    match timeout_result {
        Ok(Ok(check)) => check,
        Ok(Err(error)) => RunnerPreflightCheckStatus {
            name: "spawn".to_string(),
            success: false,
            exit_code: None,
            error: Some(error.to_string()),
        },
        Err(_) => RunnerPreflightCheckStatus {
            name: "timeout".to_string(),
            success: false,
            exit_code: Some(124),
            error: Some("runner preflight timed out".to_string()),
        },
    }
}

fn run_single_preflight_sync(spec: RunnerPreflightSpec) -> RunnerPreflightCheckStatus {
    if let Err(error) = ensure_runner_image(&spec.image) {
        return RunnerPreflightCheckStatus {
            name: spec.name.to_string(),
            success: false,
            exit_code: Some(1),
            error: Some(error.to_string()),
        };
    }

    let output = Command::new("docker")
        .arg("run")
        .arg("--rm")
        .arg(&spec.image)
        .args(&spec.command)
        .output();

    match output {
        Ok(output) => RunnerPreflightCheckStatus {
            name: spec.name.to_string(),
            success: output.status.success(),
            exit_code: output.status.code(),
            error: if output.status.success() {
                None
            } else {
                Some(String::from_utf8_lossy(&output.stderr).trim().to_string())
            },
        },
        Err(error) => RunnerPreflightCheckStatus {
            name: spec.name.to_string(),
            success: false,
            exit_code: Some(1),
            error: Some(error.to_string()),
        },
    }
}

fn ensure_runner_image(image: &str) -> Result<()> {
    let inspect = Command::new("docker")
        .arg("image")
        .arg("inspect")
        .arg(image)
        .output()?;
    if inspect.status.success() {
        return Ok(());
    }

    let pull = Command::new("docker").arg("pull").arg(image).output()?;
    if pull.status.success() {
        Ok(())
    } else {
        Err(anyhow!(
            "pull failed: {}",
            String::from_utf8_lossy(&pull.stderr).trim()
        ))
    }
}

fn configured_specs(config: &AppConfig) -> Vec<RunnerPreflightSpec> {
    vec![
        RunnerPreflightSpec {
            name: "yasa",
            image: config.scanner_yasa_image.clone(),
            command: vec!["/opt/yasa/bin/yasa".to_string(), "--version".to_string()],
        },
        RunnerPreflightSpec {
            name: "opengrep",
            image: config.scanner_opengrep_image.clone(),
            command: vec!["opengrep".to_string(), "--version".to_string()],
        },
        RunnerPreflightSpec {
            name: "bandit",
            image: config.scanner_bandit_image.clone(),
            command: vec!["bandit".to_string(), "--version".to_string()],
        },
        RunnerPreflightSpec {
            name: "gitleaks",
            image: config.scanner_gitleaks_image.clone(),
            command: vec!["gitleaks".to_string(), "version".to_string()],
        },
        RunnerPreflightSpec {
            name: "phpstan",
            image: config.scanner_phpstan_image.clone(),
            command: vec![
                "php".to_string(),
                "/opt/phpstan/phpstan".to_string(),
                "--version".to_string(),
            ],
        },
        RunnerPreflightSpec {
            name: "pmd",
            image: config.scanner_pmd_image.clone(),
            command: vec!["pmd".to_string(), "--version".to_string()],
        },
        RunnerPreflightSpec {
            name: "flow-parser",
            image: config.flow_parser_runner_image.clone(),
            command: vec![
                "python3".to_string(),
                "/opt/flow-parser/flow_parser_runner.py".to_string(),
                "--help".to_string(),
            ],
        },
        RunnerPreflightSpec {
            name: "sandbox-runner",
            image: config.sandbox_runner_image.clone(),
            command: vec![
                "python3".to_string(),
                "-c".to_string(),
                "import requests; import httpx; import jwt; print('Sandbox Runner OK')".to_string(),
            ],
        },
    ]
}

#[cfg(test)]
mod tests {
    use crate::config::AppConfig;

    use super::configured_specs;

    #[test]
    fn configured_specs_cover_all_runner_families() {
        let config = AppConfig::for_tests();
        let names = configured_specs(&config)
            .into_iter()
            .map(|spec| spec.name)
            .collect::<Vec<_>>();
        assert_eq!(
            names,
            vec![
                "yasa",
                "opengrep",
                "bandit",
                "gitleaks",
                "phpstan",
                "pmd",
                "flow-parser",
                "sandbox-runner"
            ]
        );
    }
}
