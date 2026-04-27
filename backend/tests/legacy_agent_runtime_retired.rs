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

    assert_missing_path(&repo, format!("backend/src/runtime/{retired}"));
    assert_missing_path(&repo, &agents_path);

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
            "finalize_agent_task_mock_completed".to_string(),
            "docker exec".to_string(),
        ],
    );
    assert_file_lacks(
        repo.join("scripts/generate-release-branch.sh"),
        &[agents_path],
    );
}
