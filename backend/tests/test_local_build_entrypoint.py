from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_dockerfile_uses_official_docker_cli_image_for_local_builds() -> None:
    dockerfile_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "ARG DOCKER_CLI_IMAGE=docker:cli" in dockerfile_text
    assert "ARG DOCKER_CLI_IMAGE=docker.m.daocloud.io/docker:cli" not in dockerfile_text


def test_full_overlay_prefers_official_dockerhub_mirror_for_local_builds() -> None:
    compose_text = (REPO_ROOT / "docker-compose.full.yml").read_text(encoding="utf-8")

    assert "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-docker.io/library}" in compose_text
    assert "DOCKER_CLI_IMAGE=${DOCKER_CLI_IMAGE:-docker:cli}" in compose_text


def test_local_build_script_builds_services_sequentially_before_up() -> None:
    script_text = (REPO_ROOT / "scripts" / "compose-up-local-build.sh").read_text(encoding="utf-8")

    assert 'export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"' in script_text
    assert 'export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"' in script_text
    assert '"${COMPOSE[@]}" build backend' in script_text
    assert '"${COMPOSE[@]}" build frontend' in script_text
    assert '"${COMPOSE[@]}" build nexus-web' in script_text
    assert '"${COMPOSE[@]}" up -d' in script_text
