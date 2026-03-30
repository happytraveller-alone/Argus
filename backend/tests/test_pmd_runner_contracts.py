from pathlib import Path


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "docker" / "backend.Dockerfile").exists():
            return candidate
    raise AssertionError("failed to locate repository root from test path")


def _stage_block(dockerfile_text: str, stage_header: str) -> str:
    start = dockerfile_text.find(stage_header)
    assert start != -1, f"missing stage header: {stage_header}"
    next_stage = dockerfile_text.find("\nFROM ", start + len(stage_header))
    return dockerfile_text[start:] if next_stage == -1 else dockerfile_text[start:next_stage]


def test_backend_dockerfile_no_longer_installs_local_pmd_runtime() -> None:
    dockerfile_path = _repo_root() / "docker" / "backend.Dockerfile"
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

    runtime_base_block = _stage_block(dockerfile_text, "FROM python-base AS runtime-base")
    scanner_tools_base_block = _stage_block(dockerfile_text, "FROM runtime-base AS scanner-tools-base")
    runtime_block = _stage_block(dockerfile_text, "FROM runtime-base AS runtime")

    assert "openjdk-21-jre-headless" not in runtime_base_block
    assert "php-cli" not in runtime_base_block
    assert "unzip" not in runtime_base_block

    assert "apt-get install -y --no-install-recommends unzip" in scanner_tools_base_block

    assert "PMD_CACHE" not in runtime_block
    assert "pmd-dist-7.0.0-bin.zip" not in runtime_block
    assert "/usr/local/bin/pmd" not in runtime_block


def test_compose_exposes_scanner_pmd_image_without_compose_runner_service() -> None:
    compose_path = _repo_root() / "docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    assert (
        "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-pmd-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert "\n  pmd-runner:\n" not in compose_text
    assert "runner preflight / warmup" not in compose_text
    assert "动态拉起临时 runner 容器" in compose_text


def test_full_overlay_exposes_scanner_pmd_image_without_compose_runner_service() -> None:
    compose_path = _repo_root() / "docker-compose.full.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}" in compose_text
    assert "\n  pmd-runner:\n" not in compose_text
    assert "runner preflight / warmup" not in compose_text
    assert "动态拉起临时 runner 容器" in compose_text


def test_external_tools_manual_pmd_section_documents_runner_requirements() -> None:
    manual_test_path = _repo_root() / "backend" / "tests" / "test_external_tools_manual.py"
    manual_text = manual_test_path.read_text(encoding="utf-8")

    assert "SCANNER_PMD_IMAGE" in manual_text
    assert "按需" in manual_text
    assert "runner 容器" in manual_text
    assert "默认 `docker compose up` 会先拉取远程 backend 镜像" in manual_text
    assert "Docker SDK" in manual_text
    assert "动态拉起临时 runner 容器" in manual_text
    assert "手工 smoke test" in manual_text
    assert "默认自动验收" in manual_text
    assert "docker compose up" in manual_text
    assert "docker compose up --build" not in manual_text


def test_docker_publish_workflow_builds_pmd_runner() -> None:
    workflow_path = _repo_root() / ".github" / "workflows" / "docker-publish.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert "build_pmd_runner" in workflow_text
    assert "./docker/pmd-runner.Dockerfile" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-pmd-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
