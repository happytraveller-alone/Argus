import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "compose-up-with-fallback.sh"

_EXPLICIT_MIRROR_ENV = {
    "DOCKERHUB_LIBRARY_MIRROR": "docker.m.daocloud.io/library",
    "GHCR_REGISTRY": "ghcr.io",
    "VULHUNTER_IMAGE_NAMESPACE": "unbengable12",
    "NEXUS_WEB_IMAGE_NAMESPACE": "unbengable12",
    "VULHUNTER_IMAGE_TAG": "latest",
    "NEXUS_WEB_IMAGE_TAG": "latest",
    "FRONTEND_NPM_REGISTRY": "https://registry.npmmirror.com",
    "FRONTEND_NPM_REGISTRY_FALLBACK": "https://registry.npmjs.org",
    "SANDBOX_NPM_REGISTRY_PRIMARY": "https://registry.npmmirror.com",
    "SANDBOX_NPM_REGISTRY_FALLBACK": "https://registry.npmjs.org",
    "BACKEND_PYPI_INDEX_PRIMARY": "https://mirrors.aliyun.com/pypi/simple/",
    "BACKEND_PYPI_INDEX_FALLBACK": "https://pypi.org/simple",
    "SANDBOX_PYPI_INDEX_PRIMARY": "https://mirrors.aliyun.com/pypi/simple/",
    "SANDBOX_PYPI_INDEX_FALLBACK": "https://pypi.org/simple",
    "BACKEND_APT_MIRROR_PRIMARY": "mirrors.aliyun.com",
    "BACKEND_APT_MIRROR_FALLBACK": "deb.debian.org",
    "BACKEND_APT_SECURITY_PRIMARY": "mirrors.aliyun.com",
    "BACKEND_APT_SECURITY_FALLBACK": "security.debian.org",
    "SANDBOX_APT_MIRROR_PRIMARY": "mirrors.aliyun.com",
    "SANDBOX_APT_MIRROR_FALLBACK": "deb.debian.org",
    "SANDBOX_APT_SECURITY_PRIMARY": "mirrors.aliyun.com",
    "SANDBOX_APT_SECURITY_FALLBACK": "security.debian.org",
}


def _write_fake_docker(bin_dir: Path) -> None:
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "compose" ] && [ "${2:-}" = "version" ]; then
  echo "Docker Compose version fake"
  exit 0
fi

if [ "${STUB_DOCKER_EXIT_CODE:-0}" != "0" ]; then
  echo "${STUB_DOCKER_ERROR:-error from registry: denied}" >&2
fi

{
  printf 'COMPOSE_MENU=%s\n' "${COMPOSE_MENU-__UNSET__}"
  printf 'ARGS='
  printf '%s ' "$@"
  printf '\n'
} >>"${STUB_DOCKER_LOG:?}"

exit "${STUB_DOCKER_EXIT_CODE:-0}"
""",
        encoding="utf-8",
    )
    docker_path.chmod(docker_path.stat().st_mode | stat.S_IXUSR)


def _write_fake_curl(bin_dir: Path) -> None:
    curl_path = bin_dir / "curl"
    curl_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

url="${@: -1}"
printf 'URL=%s\\n' "$url" >>"${STUB_CURL_LOG:?}"

mode="${STUB_CURL_MODE:-success}"
case "$mode" in
  success)
    exit 0
    ;;
  timeout)
    exit 7
    ;;
  frontend-only)
    case "$url" in
      *":3000/"*|*":3000")
        exit 0
        ;;
      *)
        exit 7
        ;;
    esac
    ;;
  *)
    echo "unsupported STUB_CURL_MODE=$mode" >&2
    exit 2
    ;;
esac
""",
        encoding="utf-8",
    )
    curl_path.chmod(curl_path.stat().st_mode | stat.S_IXUSR)


def _write_fake_browser(bin_dir: Path, name: str = "wslview") -> None:
    browser_path = bin_dir / name
    browser_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

printf 'BROWSER=%s\\n' "$0" >>"${STUB_BROWSER_LOG:?}"
printf 'URL=%s\\n' "${1:-}" >>"${STUB_BROWSER_LOG:?}"
""",
        encoding="utf-8",
    )
    browser_path.chmod(browser_path.stat().st_mode | stat.S_IXUSR)


def _run_compose_wrapper(
    tmp_path: Path, args: list[str], extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    _write_fake_docker(tmp_path)
    _write_fake_curl(tmp_path)
    log_path = tmp_path / "docker-invocation.log"
    curl_log_path = tmp_path / "curl-invocation.log"

    env = os.environ.copy()
    env.update(_EXPLICIT_MIRROR_ENV)
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["PHASE_RETRY_COUNT"] = "1"
    env["STUB_DOCKER_LOG"] = str(log_path)
    env["STUB_CURL_LOG"] = str(curl_log_path)
    env.setdefault("VULHUNTER_READY_TIMEOUT_SECONDS", "2")

    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    return result


def _read_log(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_compose_wrapper_defaults_apt_probe_codename_to_trixie() -> None:
    script_text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'APT_PROBE_CODENAME="${APT_PROBE_CODENAME:-trixie}"' in script_text


def test_attached_up_disables_compose_menu_by_default(tmp_path: Path) -> None:
    result = _run_compose_wrapper(tmp_path, ["up"])
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "COMPOSE_MENU=false" in log_output
    assert "ARGS=compose up " in log_output


def test_attached_up_with_global_file_flags_disables_compose_menu(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path, ["-f", "docker-compose.yml", "-f", "docker-compose.full.yml", "up", "--build"]
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "COMPOSE_MENU=false" in log_output
    assert "ARGS=compose -f docker-compose.yml -f docker-compose.full.yml up --build " in log_output


def test_attached_explicit_local_build_flags_are_preserved(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path,
        ["-f", "docker-compose.yml", "-f", "docker-compose.full.yml", "up", "--build"],
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "ARGS=compose -f docker-compose.yml -f docker-compose.full.yml up --build " in log_output


def test_detached_up_keeps_compose_menu_unset(tmp_path: Path) -> None:
    result = _run_compose_wrapper(tmp_path, ["up", "-d"])
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "COMPOSE_MENU=__UNSET__" in log_output


def test_explicit_compose_menu_is_preserved(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path,
        ["up"],
        extra_env={"COMPOSE_MENU": "true"},
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "COMPOSE_MENU=true" in log_output


def test_detached_up_prints_ready_banner_after_successful_probes(tmp_path: Path) -> None:
    result = _run_compose_wrapper(tmp_path, ["up", "-d"])
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output
    assert "services ready" in combined_output
    assert "frontend: http://localhost:3000" in combined_output
    assert "backend docs: http://localhost:8000/docs" in combined_output
    curl_log = _read_log(tmp_path / "curl-invocation.log")
    assert "URL=http://127.0.0.1:3000/" in curl_log
    assert "URL=http://127.0.0.1:8000/health" in curl_log


def test_detached_up_can_open_browser_after_ready(tmp_path: Path) -> None:
    _write_fake_browser(tmp_path, "wslview")
    browser_log_path = tmp_path / "browser-invocation.log"
    result = _run_compose_wrapper(
        tmp_path,
        ["up", "-d"],
        extra_env={
            "VULHUNTER_OPEN_BROWSER": "1",
            "STUB_BROWSER_LOG": str(browser_log_path),
        },
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output
    browser_log = _read_log(browser_log_path)
    assert "URL=http://localhost:3000" in browser_log


def test_detached_up_ready_timeout_warns_without_failing(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path,
        ["up", "-d"],
        extra_env={
            "STUB_CURL_MODE": "timeout",
            "VULHUNTER_READY_TIMEOUT_SECONDS": "1",
        },
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output
    assert "timed out waiting for frontend/backend readiness" in combined_output


def test_wrapper_defaults_to_remote_up_without_build(tmp_path: Path) -> None:
    result = _run_compose_wrapper(tmp_path, [])
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output
    log_output = _read_log(tmp_path / "docker-invocation.log")

    assert "ARGS=compose up -d " in log_output
    assert "--build" not in log_output


def test_wrapper_logs_resolved_remote_images(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path,
        ["up"],
        extra_env={
            "VULHUNTER_IMAGE_NAMESPACE": "acme-sec",
            "NEXUS_WEB_IMAGE_NAMESPACE": "acme-ui",
            "VULHUNTER_IMAGE_TAG": "v9",
            "NEXUS_WEB_IMAGE_TAG": "v2",
        },
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output
    assert "BACKEND_IMAGE_RESOLVED=ghcr.io/acme-sec/vulhunter-backend:v9" in combined_output
    assert "FRONTEND_IMAGE_RESOLVED=ghcr.io/acme-sec/vulhunter-frontend:v9" in combined_output
    assert "NEXUS_WEB_IMAGE_RESOLVED=ghcr.io/acme-ui/nexus-web:v2" in combined_output


def test_wrapper_failure_surfaces_remote_image_hint(tmp_path: Path) -> None:
    result = _run_compose_wrapper(
        tmp_path,
        ["up"],
        extra_env={
            "STUB_DOCKER_EXIT_CODE": "1",
            "STUB_DOCKER_ERROR": "error from registry: denied",
        },
    )
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 1, combined_output
    assert "anonymous GHCR pull failed or the image namespace/tag is incorrect" in combined_output
    assert "ghcr.io/unbengable12/vulhunter-backend:latest" in combined_output
