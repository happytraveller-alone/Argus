from pathlib import Path

from app.runtime import container_startup


def test_backend_startup_bootstraps_missing_docker_env_from_example(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir()
    docker_env_dir = tmp_path / "docker-env"
    docker_env_dir.mkdir()
    example_text = "LLM_PROVIDER=openai\nLLM_API_KEY=\n"
    (docker_env_dir / "env.example").write_text(example_text, encoding="utf-8")
    monkeypatch.setenv("BACKEND_DOCKER_ENV_DIR", str(docker_env_dir))

    container_startup._ensure_backend_env_files(app_root)

    assert (docker_env_dir / ".env").read_text(encoding="utf-8") == example_text
    assert (app_root / ".env").read_text(encoding="utf-8") == example_text


def test_backend_startup_reuses_existing_docker_env_for_app_env(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir()
    docker_env_dir = tmp_path / "docker-env"
    docker_env_dir.mkdir()
    docker_env_text = "SECRET_KEY=already-present\n"
    (docker_env_dir / ".env").write_text(docker_env_text, encoding="utf-8")
    (docker_env_dir / "env.example").write_text("SECRET_KEY=from-example\n", encoding="utf-8")
    monkeypatch.setenv("BACKEND_DOCKER_ENV_DIR", str(docker_env_dir))

    container_startup._ensure_backend_env_files(app_root)

    assert (docker_env_dir / ".env").read_text(encoding="utf-8") == docker_env_text
    assert (app_root / ".env").read_text(encoding="utf-8") == docker_env_text
