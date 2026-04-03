import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_dockerfile_derives_docker_cli_image_from_selected_mirror() -> None:
    dockerfile_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli" in dockerfile_text
    assert "ARG DOCKER_CLI_IMAGE=docker.m.daocloud.io/docker:cli" not in dockerfile_text


def test_local_build_script_prefers_daocloud_defaults_for_local_builds() -> None:
    script_text = (REPO_ROOT / "scripts" / "compose-up-local-build.sh").read_text(encoding="utf-8")

    assert 'export DOCKERHUB_LIBRARY_MIRROR="${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}"' in script_text
    assert 'export DOCKER_CLI_IMAGE="${DOCKER_CLI_IMAGE:-docker:cli}"' in script_text


def test_local_build_script_builds_services_sequentially_before_up() -> None:
    script_text = (REPO_ROOT / "scripts" / "compose-up-local-build.sh").read_text(encoding="utf-8")

    assert 'export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"' in script_text
    assert 'export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"' in script_text
    assert '"${COMPOSE[@]}" build backend' in script_text
    assert '"${COMPOSE[@]}" build frontend' in script_text
    assert '"${COMPOSE[@]}" build nexus-web' in script_text
    assert '"${COMPOSE[@]}" build nexus-itemDetail' in script_text
    assert '"${COMPOSE[@]}" up -d' in script_text


def _write_fake_docker(bin_dir: Path) -> Path:
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "compose" ]; then
  {
    printf 'ARGS='
    printf '%s ' "$@"
    printf '\\n'
  } >>"${STUB_DOCKER_LOG:?}"
fi
""",
        encoding="utf-8",
    )
    docker_path.chmod(docker_path.stat().st_mode | stat.S_IXUSR)
    return docker_path


def test_local_build_script_bootstraps_backend_env_from_example(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    lib_dir = scripts_dir / "lib"
    backend_env_dir = repo_root / "docker" / "env" / "backend"
    scripts_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    backend_env_dir.mkdir(parents=True)

    (scripts_dir / "compose-up-local-build.sh").write_text(
        (REPO_ROOT / "scripts" / "compose-up-local-build.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (lib_dir / "compose-env.sh").write_text(
        (REPO_ROOT / "scripts" / "lib" / "compose-env.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo_root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo_root / "docker-compose.full.yml").write_text("services: {}\n", encoding="utf-8")
    env_example = backend_env_dir / "env.example"
    env_example.write_text("LLM_API_KEY=example-key\n", encoding="utf-8")

    script_path = scripts_dir / "compose-up-local-build.sh"
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_path = tmp_path / "docker.log"
    _write_fake_docker(fake_bin)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["STUB_DOCKER_LOG"] = str(log_path)

    result = subprocess.run(
        [str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    env_file = backend_env_dir / ".env"
    assert env_file.exists()
    assert env_file.read_text(encoding="utf-8") == env_example.read_text(encoding="utf-8")
    assert "自动生成 backend Docker 环境文件" in combined_output

    log_output = log_path.read_text(encoding="utf-8")
    assert "ARGS=compose -f" in log_output
    assert "build backend" in log_output
    assert "build frontend" in log_output
    assert "build nexus-web" in log_output
    assert "build nexus-itemDetail" in log_output
    assert "up -d" in log_output
