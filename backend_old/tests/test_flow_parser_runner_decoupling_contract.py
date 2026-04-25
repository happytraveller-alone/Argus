from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_flow_parser_runner_dockerfile_uses_non_legacy_host_artifact() -> None:
    dockerfile_text = (REPO_ROOT / "docker" / "flow-parser-runner.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "COPY backend/scripts/flow_parser_runner.py /opt/flow-parser/flow_parser_runner.py" in dockerfile_text
    assert "COPY backend/scripts/flow_parser_host.py /opt/flow-parser/flow_parser_host.py" in dockerfile_text
    assert "COPY backend_old/app /opt/flow-parser/app" not in dockerfile_text


def test_flow_parser_runner_publish_workflow_no_longer_tracks_backend_old_app() -> None:
    workflow_text = (
        REPO_ROOT / ".github" / "workflows" / "docker-publish-runners.yml"
    ).read_text(encoding="utf-8")

    assert "backend/scripts/**" in workflow_text
    assert "backend_old/app/**" not in workflow_text


def test_sandbox_runner_compose_comment_no_longer_points_to_backend_old_env() -> None:
    compose_text = (REPO_ROOT / "docker" / "docker-compose.sandbox-runner.yml").read_text(
        encoding="utf-8"
    )

    assert "docker/env/backend/.env" in compose_text
    assert "docker/env/backend_old/.env" not in compose_text
