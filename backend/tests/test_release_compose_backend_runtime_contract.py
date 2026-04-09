from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_release_compose_contract_uses_only_supported_commands_and_cloud_runners() -> None:
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    hybrid_text = (REPO_ROOT / "docker-compose.hybrid.yml").read_text(encoding="utf-8")

    assert "docker compose up" in compose_text
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in compose_text
    assert "docker-compose.full.yml" not in compose_text
    assert "docker-compose.release.yml" not in compose_text
    assert "docker-compose.release-cython.yml" not in compose_text
    assert "docker-compose.self-contained.yml" not in compose_text
    assert (
        "image: ${BACKEND_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-backend:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "image: ${FRONTEND_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-frontend:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-yasa-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT" not in compose_text
    assert "RUNNER_PREFLIGHT_BUILD_TIMEOUT_SECONDS" not in compose_text

    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in hybrid_text
    assert "docker-compose.full.yml" not in hybrid_text
    assert "build: !override" in hybrid_text
    assert hybrid_text.count("build: !override") == 2
    assert "frontend:\n    image: vulhunter/frontend-local:latest" in hybrid_text
    assert "backend:\n    image: vulhunter/backend-local:latest" in hybrid_text
    assert "target: runtime-plain" in hybrid_text
    assert "context: ./frontend" in hybrid_text
    assert "context: ." in hybrid_text
    assert (
        "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-yasa-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in hybrid_text
    assert "-runner-local:latest" not in hybrid_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT" not in hybrid_text
    assert "RUNNER_PREFLIGHT_BUILD_TIMEOUT_SECONDS" not in hybrid_text


def test_backend_runtime_targets_do_not_embed_local_runner_build_context() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
    runner_preflight_text = (REPO_ROOT / "backend" / "app" / "services" / "runner_preflight.py").read_text(
        encoding="utf-8"
    )

    runtime_cython_section = backend_text.split("FROM runtime-base AS runtime-cython", maxsplit=1)[1].split(
        "FROM runtime-base AS runtime",
        maxsplit=1,
    )[0]
    runtime_section = backend_text.split("FROM runtime-base AS runtime", maxsplit=1)[1].split(
        "FROM runtime-base AS runtime-plain",
        maxsplit=1,
    )[0]
    runtime_plain_section = backend_text.split("FROM runtime-base AS runtime-plain", maxsplit=1)[1]

    for section in (runtime_cython_section, runtime_section, runtime_plain_section):
        assert "/opt/backend-build-context" not in section
        assert "backend/docs/agent-tools" not in section
        assert "RUNNER_PREFLIGHT_BUILD_CONTEXT" not in section

    assert "subprocess.run(" not in runner_preflight_text
    assert "falling back to local build" not in runner_preflight_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT" not in runner_preflight_text
    assert "RUNNER_PREFLIGHT_BUILD_TIMEOUT_SECONDS" not in runner_preflight_text
