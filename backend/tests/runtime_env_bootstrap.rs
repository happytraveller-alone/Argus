use anyhow::Result;
use backend_rust::runtime::bootstrap;
use std::{env, fs, path::PathBuf};
use tempfile::TempDir;

fn prepare_dirs(tmp: &TempDir) -> (PathBuf, PathBuf) {
    let app_root = tmp.path().join("app");
    fs::create_dir_all(&app_root).expect("create app root");
    let docker_env_dir = tmp.path().join("docker-env");
    fs::create_dir_all(&docker_env_dir).expect("create docker env dir");
    (app_root, docker_env_dir)
}

#[test]
fn bootstraps_missing_docker_env_from_example() -> Result<()> {
    let tmp = TempDir::new()?;
    let (app_root, docker_env_dir) = prepare_dirs(&tmp);
    let example_text = "LLM_PROVIDER=openai\nLLM_API_KEY=\n";
    fs::write(docker_env_dir.join("env.example"), example_text)?;

    env::set_var(
        "BACKEND_DOCKER_ENV_DIR",
        docker_env_dir.display().to_string(),
    );
    bootstrap::ensure_backend_env_files(&app_root)?;

    let docker_env = fs::read_to_string(docker_env_dir.join(".env"))?;
    let app_env = fs::read_to_string(app_root.join(".env"))?;
    assert_eq!(docker_env, example_text);
    assert_eq!(app_env, example_text);

    env::remove_var("BACKEND_DOCKER_ENV_DIR");
    Ok(())
}

#[test]
fn reuses_existing_docker_env_for_app_env() -> Result<()> {
    let tmp = TempDir::new()?;
    let (app_root, docker_env_dir) = prepare_dirs(&tmp);
    let docker_env_text = "SECRET_KEY=already-present\n";
    fs::write(docker_env_dir.join(".env"), docker_env_text)?;
    fs::write(
        docker_env_dir.join("env.example"),
        "SECRET_KEY=from-example\n",
    )?;

    env::set_var(
        "BACKEND_DOCKER_ENV_DIR",
        docker_env_dir.display().to_string(),
    );
    bootstrap::ensure_backend_env_files(&app_root)?;

    let app_env = fs::read_to_string(app_root.join(".env"))?;
    assert_eq!(app_env, docker_env_text);

    env::remove_var("BACKEND_DOCKER_ENV_DIR");
    Ok(())
}
