from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NAMESPACE = "happytraveller-alone"


def test_reusable_publish_workflow_defaults_to_repo_owner_with_optional_override() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(encoding="utf-8")

    assert "VULHUNTER_IMAGE_NAMESPACE: ${{ vars.GHCR_NAMESPACE || github.repository_owner }}" in workflow_text
    assert "Publishing to ghcr.io/${VULHUNTER_IMAGE_NAMESPACE} from repository owner ${GITHUB_REPOSITORY_OWNER} requires GHCR_USERNAME and GHCR_TOKEN secrets." in workflow_text


def test_active_compose_files_default_to_current_repo_owner_namespace() -> None:
    compose_paths = [
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / "docker-compose.hybrid.yml",
        REPO_ROOT / "scripts" / "release-templates" / "docker-compose.release-slim.yml",
        REPO_ROOT / "scripts" / "release-templates" / "docker-compose.hybrid.release-slim.yml",
    ]

    expected_namespace = f"VULHUNTER_IMAGE_NAMESPACE: ${{VULHUNTER_IMAGE_NAMESPACE:-{DEFAULT_NAMESPACE}}}"
    expected_bandit = (
        "SCANNER_BANDIT_IMAGE: "
        f"${{SCANNER_BANDIT_IMAGE:-${{GHCR_REGISTRY:-ghcr.io}}/${{VULHUNTER_IMAGE_NAMESPACE:-{DEFAULT_NAMESPACE}}}/"
        "vulhunter-bandit-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    )

    for compose_path in compose_paths:
        compose_text = compose_path.read_text(encoding="utf-8")

        assert expected_namespace in compose_text, compose_path.as_posix()
        assert expected_bandit in compose_text, compose_path.as_posix()


def test_docs_and_env_example_explain_ghcr_owner_rules() -> None:
    backend_env_text = (REPO_ROOT / "docker" / "env" / "backend" / "env.example").read_text(encoding="utf-8")
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_en_text = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")

    assert f"SANDBOX_IMAGE=ghcr.io/{DEFAULT_NAMESPACE}/vulhunter-sandbox-runner:latest" in backend_env_text
    assert "ghcr.io/<GitHub用户或组织>/<image>:<tag>" in readme_text
    assert "`GHCR_NAMESPACE`" in readme_text
    assert "ghcr.io/<GitHub user or organization>/<image>:<tag>" in readme_en_text
    assert "`GHCR_NAMESPACE`" in readme_en_text
