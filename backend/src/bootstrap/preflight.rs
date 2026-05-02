use std::{path::PathBuf, process::Command, sync::Arc};

use anyhow::{anyhow, Result};
use tokio::{
    sync::Semaphore,
    task::JoinSet,
    time::{timeout, Duration},
};

use crate::state::{AppState, BootstrapStatus, RunnerPreflightCheckStatus, RunnerPreflightStatus};

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

    let output = Command::new("docker").args(docker_run_args(&spec)).output();

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

fn docker_run_args(spec: &RunnerPreflightSpec) -> Vec<String> {
    let mut args = vec!["run".to_string(), "--rm".to_string()];
    for (host_path, container_path) in &spec.mounts {
        args.push("-v".to_string());
        args.push(format!("{}:{}", host_path.display(), container_path));
    }
    args.push(spec.image.clone());
    args.extend(spec.command.clone());
    args
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
            command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
            mounts: Vec::new(),
        },
        RunnerPreflightSpec {
            name: "codeql",
            image: config.scanner_codeql_image.clone(),
            command: vec!["codeql-scan".to_string(), "--self-test".to_string()],
            mounts: Vec::new(),
        },
        RunnerPreflightSpec {
            name: "codeql-compile-sandbox",
            image: config.scanner_codeql_compile_sandbox_image.clone(),
            command: vec![
                "codeql-compile-sandbox".to_string(),
                "--self-test".to_string(),
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

    Ok((specs, cleanup_dirs))
}

async fn build_opengrep_preflight_inputs(
    _state: &AppState,
) -> Result<Option<(PathBuf, Vec<String>, Vec<(PathBuf, String)>)>> {
    // Preflight only verifies the opengrep binary is functional.
    // Rule validation happens at scan time via the named workspace volume.
    // Bind-mounting a temp dir fails in Docker-in-Docker because the Docker
    // daemon resolves host paths, not container paths.
    Ok(None)
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use crate::{config::AppConfig, state::AppState};

    use super::{configured_specs, docker_run_args, RunnerPreflightSpec};

    #[tokio::test]
    async fn configured_specs_include_static_runner_preflights() {
        let config = AppConfig::for_tests();
        let state = AppState::from_config(config)
            .await
            .expect("state should build");
        let (specs, cleanup_dirs) = configured_specs(&state).await.expect("specs should build");
        let mut names = specs.iter().map(|spec| spec.name).collect::<Vec<_>>();
        names.sort_unstable();
        assert_eq!(names, vec!["codeql", "codeql-compile-sandbox", "opengrep"]);

        let opengrep = specs
            .iter()
            .find(|spec| spec.name == "opengrep")
            .expect("opengrep spec should exist");
        assert_eq!(opengrep.command, vec!["opengrep-scan", "--self-test"]);
        assert!(opengrep.mounts.is_empty());

        let codeql = specs
            .iter()
            .find(|spec| spec.name == "codeql")
            .expect("codeql spec should exist");
        assert_eq!(codeql.command, vec!["codeql-scan", "--self-test"]);
        assert!(codeql.mounts.is_empty());

        let compile_sandbox = specs
            .iter()
            .find(|spec| spec.name == "codeql-compile-sandbox")
            .expect("codeql compile sandbox spec should exist");
        assert_eq!(
            compile_sandbox.command,
            vec!["codeql-compile-sandbox", "--self-test"]
        );
        assert!(compile_sandbox.mounts.is_empty());

        for cleanup_dir in cleanup_dirs {
            let _ = tokio::fs::remove_dir_all(cleanup_dir).await;
        }
    }

    #[test]
    fn static_runner_preflight_docker_run_uses_rm_cleanup() {
        let cases = [
            RunnerPreflightSpec {
                name: "opengrep",
                image: "opengrep-runner:test".to_string(),
                command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
                mounts: vec![(
                    PathBuf::from("/tmp/argus-preflight"),
                    "/workspace".to_string(),
                )],
            },
            RunnerPreflightSpec {
                name: "codeql",
                image: "codeql-runner:test".to_string(),
                command: vec!["codeql-scan".to_string(), "--self-test".to_string()],
                mounts: Vec::new(),
            },
            RunnerPreflightSpec {
                name: "codeql-compile-sandbox",
                image: "codeql-compile-sandbox:test".to_string(),
                command: vec![
                    "codeql-compile-sandbox".to_string(),
                    "--self-test".to_string(),
                ],
                mounts: Vec::new(),
            },
        ];

        for spec in cases {
        let args = docker_run_args(&spec);

        assert_eq!(args.first().map(String::as_str), Some("run"));
        assert!(
            args.iter().any(|arg| arg == "--rm"),
            "{} preflight must remove its validation container",
            spec.name
        );
        }
    }
}
