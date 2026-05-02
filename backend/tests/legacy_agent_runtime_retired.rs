use std::{fs, path::PathBuf};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("backend crate should live below repo root")
        .to_path_buf()
}

fn retired_runtime_name() -> String {
    ['h', 'e', 'r', 'm', 'e', 's'].iter().collect()
}

fn assert_missing_path(repo: &std::path::Path, relative_path: impl AsRef<str>) {
    let relative_path = relative_path.as_ref();
    assert!(
        !repo.join(relative_path).exists(),
        "{relative_path} should be removed"
    );
}

fn assert_file_lacks(path: PathBuf, needles: &[String]) {
    let content = fs::read_to_string(&path).expect("read source file");
    for needle in needles {
        assert!(
            !content.contains(needle),
            "{} should not contain retired runtime marker {needle:?}",
            path.display()
        );
    }
}

fn joined(parts: &[&str]) -> String {
    parts.concat()
}

#[test]
fn legacy_agent_runtime_surface_is_retired() {
    let repo = repo_root();
    let retired = retired_runtime_name();
    let retired_upper = retired.to_ascii_uppercase();
    let dispatch_symbol = format!("try_{retired}_dispatch");
    let module_path = format!("runtime::{retired}");
    let module_export = format!("pub mod {retired}");
    let container_name = format!("{retired}-recon");
    let agent_image = format!("{retired}-agent");
    let agents_path = ["backend/", "agents"].concat();
    let fixtures_path = format!("backend/tests/fixtures/{retired}");
    let mock_completed_symbol = ["finalize_agent_task_", "mock", "_completed"].concat();

    assert_missing_path(&repo, format!("backend/src/runtime/{retired}"));
    assert_missing_path(&repo, &agents_path);
    assert_missing_path(&repo, fixtures_path);

    assert_file_lacks(repo.join("backend/src/runtime/mod.rs"), &[module_export]);
    assert_file_lacks(
        repo.join("docker-compose.yml"),
        &[
            format!("{retired_upper}_"),
            format!("./{agents_path}"),
            container_name,
            agent_image,
        ],
    );
    assert_file_lacks(
        repo.join("backend/src/routes/agent_tasks.rs"),
        &[
            module_path,
            dispatch_symbol,
            "DispatchOutcome".to_string(),
            mock_completed_symbol,
            "docker exec".to_string(),
        ],
    );
    assert_file_lacks(
        repo.join("scripts/generate-release-branch.sh"),
        &[agents_path],
    );
}

#[test]
fn retired_auxiliary_runtime_surface_is_removed() {
    let repo = repo_root();
    let flow_snake = joined(&["flow", "_parser"]);
    let flow_dash = joined(&["flow", "-parser"]);
    let code_flow = joined(&["code", "2", "flow"]);
    let sandbox_plain = joined(&["sand", "box"]);
    let sandbox_snake = joined(&["sand", "box", "_runner"]);
    let sandbox_dash = joined(&["sand", "box", "-runner"]);
    let flow_runner_env = joined(&["FLOW", "_PARSER", "_RUNNER"]);
    let retired_box_env = joined(&["SANDBOX", "_RUNNER"]);
    let sandbox_env = joined(&["SANDBOX", "_"]);

    for relative_path in [
        format!("backend/src/runtime/{flow_snake}.rs"),
        format!("backend/src/runtime/{code_flow}.rs"),
        format!("backend/src/runtime/{sandbox_plain}.rs"),
        format!("backend/scripts/{flow_snake}_host.py"),
        format!("backend/scripts/{flow_snake}_runner.py"),
        format!("docker/{flow_dash}-runner.Dockerfile"),
        format!("docker/{flow_dash}-runner.requirements.txt"),
        format!("docker/{sandbox_dash}.Dockerfile"),
        format!("docker/{sandbox_dash}.requirements.txt"),
        format!("docker/docker-compose.{sandbox_dash}.yml"),
    ] {
        assert_missing_path(&repo, relative_path);
    }

    let backend_needles = vec![
        flow_snake.clone(),
        flow_dash.clone(),
        code_flow,
        sandbox_snake.clone(),
        sandbox_dash.clone(),
        flow_runner_env.clone(),
        retired_box_env.clone(),
    ];

    for relative_path in [
        "backend/src/runtime/mod.rs",
        "backend/src/config.rs",
        "backend/src/bin/backend_runtime_startup.rs",
        "backend/src/runtime/runner.rs",
        ".github/workflows/docker-publish.yml",
        ".github/workflows/release.yml",
    ] {
        assert_file_lacks(repo.join(relative_path), &backend_needles);
    }

    let compose_needles = vec![
        flow_dash,
        sandbox_dash,
        flow_runner_env,
        retired_box_env,
        sandbox_env,
    ];

    for relative_path in [
        "docker-compose.yml",
        "scripts/release-templates/docker-compose.release-slim.yml",
        "frontend/tests/agentAuditToolEvidenceDialog.test.tsx",
        "frontend/tests/scanConfigExternalToolDetail.test.tsx",
        "frontend/tests/toolEvidenceRendering.test.tsx",
    ] {
        assert_file_lacks(repo.join(relative_path), &compose_needles);
    }
}
