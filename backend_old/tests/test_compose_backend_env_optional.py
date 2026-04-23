from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_backend_env_file_is_optional_and_env_dir_is_mounted() -> None:
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "env_file:" in compose_text
    assert "path: ./docker/env/backend/.env" in compose_text
    assert "required: false" in compose_text
    assert "./docker/env/backend:/docker/env/backend" in compose_text
    assert not (REPO_ROOT / "docker-compose.hybrid.yml").exists()
    assert not (REPO_ROOT / "docker-compose.full.yml").exists()
