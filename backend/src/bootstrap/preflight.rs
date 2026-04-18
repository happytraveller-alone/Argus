use std::{path::PathBuf, process::Command, sync::Arc};

use anyhow::{anyhow, Result};
use tokio::{
    sync::Semaphore,
    task::JoinSet,
    time::{timeout, Duration},
};

use crate::{
    scan::{opengrep, pmd},
    state::{AppState, BootstrapStatus, RunnerPreflightCheckStatus, RunnerPreflightStatus},
};

#[derive(Clone, Debug)]
struct RunnerPreflightSpec {
    name: &'static str,
    image: String,
    command: Vec<String>,
    mounts: Vec<(PathBuf, String)>,
}

pub async fn run(state: &AppState) -> Result<RunnerPreflightStatus> {
    let config = &state.config;
    if !config.runner_preflight_enabled {
        return Ok(RunnerPreflightStatus {
            status: "skipped".to_string(),
            enabled: false,
            strict: config.runner_preflight_strict,
            checks: Vec::new(),
            error: None,
        });
    }

    let (specs, cleanup_dirs) = configured_specs(state).await?;
    let semaphore = Arc::new(Semaphore::new(
        config.runner_preflight_max_concurrency.max(1),
    ));
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
        .map(|check| {
            format!(
                "{}: {}",
                check.name,
                check.error.clone().unwrap_or_else(|| "unknown".to_string())
            )
        })
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

    for cleanup_dir in cleanup_dirs {
        let _ = tokio::fs::remove_dir_all(cleanup_dir).await;
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

    let mut command = Command::new("docker");
    command.arg("run").arg("--rm");
    for (host_path, container_path) in &spec.mounts {
        command
            .arg("-v")
            .arg(format!("{}:{}", host_path.display(), container_path));
    }
    command.arg(&spec.image).args(&spec.command);
    let output = command.output();

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

async fn configured_specs(state: &AppState) -> Result<(Vec<RunnerPreflightSpec>, Vec<PathBuf>)> {
    let config = &state.config;
    let mut cleanup_dirs = Vec::new();
    let mut specs = vec![
        RunnerPreflightSpec {
            name: "opengrep",
            image: config.scanner_opengrep_image.clone(),
            command: vec!["opengrep".to_string(), "--version".to_string()],
            mounts: Vec::new(),
        },
        RunnerPreflightSpec {
            name: "pmd",
            image: config.scanner_pmd_image.clone(),
            command: vec!["pmd".to_string(), "--version".to_string()],
            mounts: Vec::new(),
        },
        RunnerPreflightSpec {
            name: "flow-parser",
            image: config.flow_parser_runner_image.clone(),
            command: vec![
                "python3".to_string(),
                "/opt/flow-parser/flow_parser_runner.py".to_string(),
                "--help".to_string(),
            ],
            mounts: Vec::new(),
        },
        RunnerPreflightSpec {
            name: "sandbox-runner",
            image: config.sandbox_runner_image.clone(),
            command: vec![
                "python3".to_string(),
                "-c".to_string(),
                "import requests; import httpx; import jwt; print('Sandbox Runner OK')".to_string(),
            ],
            mounts: Vec::new(),
        },
    ];

    if let Some(opengrep_spec) = specs.iter_mut().find(|spec| spec.name == "opengrep") {
        if let Some((workspace_dir, command, mounts)) =
            build_opengrep_preflight_inputs(state).await?
        {
            opengrep_spec.command = command;
            opengrep_spec.mounts = mounts;
            cleanup_dirs.push(workspace_dir);
        }
    }

    if let Some(pmd_spec) = specs.iter_mut().find(|spec| spec.name == "pmd") {
        if let Some((workspace_dir, command, mounts)) = build_pmd_preflight_inputs(state).await? {
            pmd_spec.command = command;
            pmd_spec.mounts = mounts;
            cleanup_dirs.push(workspace_dir);
        }
    }

    Ok((specs, cleanup_dirs))
}

async fn build_opengrep_preflight_inputs(
    state: &AppState,
) -> Result<Option<(PathBuf, Vec<String>, Vec<(PathBuf, String)>)>> {
    let workspace_dir =
        std::env::temp_dir().join(format!("opengrep-preflight-{}", uuid::Uuid::new_v4()));
    let rules_dir = opengrep::materialize_rule_directory(state, &workspace_dir).await?;
    let Some(_rules_dir) = rules_dir else {
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Ok(None);
    };

    let command = opengrep::build_validate_command("/work/opengrep-rules");
    Ok(Some((
        workspace_dir.clone(),
        command,
        vec![(workspace_dir, "/work".to_string())],
    )))
}

async fn build_pmd_preflight_inputs(
    state: &AppState,
) -> Result<Option<(PathBuf, Vec<String>, Vec<(PathBuf, String)>)>> {
    let workspace_dir =
        std::env::temp_dir().join(format!("pmd-preflight-{}", uuid::Uuid::new_v4()));
    let source_dir = workspace_dir.join("source");
    tokio::fs::create_dir_all(&source_dir).await?;
    tokio::fs::write(
        source_dir.join("Demo.java"),
        "public class Demo { public void run() { try { int a = 1; } catch (Exception e) {} } }\n",
    )
    .await?;
    let assets = pmd::load_builtin_rulesets(state).await?;
    let Some(_rules_dir) = pmd::materialize_ruleset_directory(state, &workspace_dir).await? else {
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Ok(None);
    };
    let Some(ruleset) = pmd::select_preflight_ruleset(&assets) else {
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Ok(None);
    };
    let command = pmd::build_check_command("/work/source", &format!("/work/pmd-rules/{ruleset}"));
    Ok(Some((
        workspace_dir.clone(),
        command,
        vec![(workspace_dir, "/work".to_string())],
    )))
}

#[cfg(test)]
mod tests {
    use crate::{config::AppConfig, state::AppState};

    use super::configured_specs;

    #[tokio::test]
    async fn configured_specs_cover_all_runner_families() {
        let config = AppConfig::for_tests();
        let state = AppState::from_config(config)
            .await
            .expect("state should build");
        let (specs, cleanup_dirs) = configured_specs(&state).await.expect("specs should build");
        let names = specs.iter().map(|spec| spec.name).collect::<Vec<_>>();
        assert_eq!(
            names,
            vec!["opengrep", "pmd", "flow-parser", "sandbox-runner"]
        );

        let opengrep = specs
            .iter()
            .find(|spec| spec.name == "opengrep")
            .expect("opengrep spec should exist");
        assert_eq!(
            opengrep.command,
            vec!["opengrep", "--config", "/work/opengrep-rules", "--validate"]
        );
        assert_eq!(opengrep.mounts.len(), 1);

        let pmd = specs
            .iter()
            .find(|spec| spec.name == "pmd")
            .expect("pmd spec should exist");
        assert_eq!(pmd.command.first().map(String::as_str), Some("pmd"));
        assert!(pmd.command.iter().any(|part| part == "-R"));
        assert!(pmd
            .command
            .iter()
            .any(|part| part.starts_with("/work/pmd-rules/")));
        assert_eq!(pmd.mounts.len(), 1);

        for cleanup_dir in cleanup_dirs {
            let _ = tokio::fs::remove_dir_all(cleanup_dir).await;
        }
    }
}
