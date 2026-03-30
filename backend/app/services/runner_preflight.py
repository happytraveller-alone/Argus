from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker

from app.core.config import settings


logger = logging.getLogger(__name__)
DOCKER_EXCEPTION = getattr(getattr(docker, "errors", None), "DockerException", Exception)
DOCKER_NOT_FOUND = getattr(getattr(docker, "errors", None), "ImageNotFound", Exception)


@dataclass
class RunnerPreflightSpec:
    name: str
    image: str
    command: list[str]
    timeout_seconds: int
    dockerfile: str | None = None
    build_context: str | None = None
    build_args: dict[str, str] = field(default_factory=dict)


@dataclass
class RunnerPreflightResult:
    name: str
    image: str
    command: list[str]
    timeout_seconds: int
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    error: str | None
    container_id: str | None


def _clean_build_args(raw: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        cleaned[str(key)] = str(value)
    return cleaned


def _backend_build_context() -> str:
    configured = str(os.environ.get("RUNNER_PREFLIGHT_BUILD_CONTEXT", "")).strip()
    if configured:
        return configured
    return "/app"


def _common_runner_build_args() -> dict[str, str]:
    # 可选配置项：空字符串视为"未设置"，让 Dockerfile ARG 默认值生效
    # proxy 相关 key 明确传空字符串以清除宿主机代理继承
    return _clean_build_args(
        {
            "DOCKERHUB_LIBRARY_MIRROR": os.environ.get("DOCKERHUB_LIBRARY_MIRROR") or None,
            "BACKEND_APT_MIRROR_PRIMARY": os.environ.get("BACKEND_APT_MIRROR_PRIMARY") or None,
            "BACKEND_APT_SECURITY_PRIMARY": os.environ.get("BACKEND_APT_SECURITY_PRIMARY") or None,
            "BACKEND_APT_MIRROR_FALLBACK": os.environ.get("BACKEND_APT_MIRROR_FALLBACK") or None,
            "BACKEND_APT_SECURITY_FALLBACK": os.environ.get("BACKEND_APT_SECURITY_FALLBACK") or None,
            "BACKEND_PYPI_INDEX_PRIMARY": os.environ.get("BACKEND_PYPI_INDEX_PRIMARY") or None,
            "BACKEND_PYPI_INDEX_FALLBACK": os.environ.get("BACKEND_PYPI_INDEX_FALLBACK") or None,
            "BACKEND_PYPI_INDEX_CANDIDATES": os.environ.get("BACKEND_PYPI_INDEX_CANDIDATES") or None,
            "BACKEND_INSTALL_YASA": os.environ.get("BACKEND_INSTALL_YASA") or None,
            "YASA_VERSION": os.environ.get("YASA_VERSION") or None,
            "http_proxy": "",
            "https_proxy": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "all_proxy": "",
            "ALL_PROXY": "",
        }
    )


def get_configured_runner_preflight_specs() -> list[RunnerPreflightSpec]:
    build_context = _backend_build_context()
    common_args = _common_runner_build_args()
    return [
        RunnerPreflightSpec(
            name="yasa",
            image=str(getattr(settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:latest")),
            command=["/opt/yasa/bin/yasa", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/yasa-runner.Dockerfile",
            build_context=build_context,
            build_args=_clean_build_args(
                {
                    **common_args,
                    "YASA_BUILD_FROM_SOURCE": os.environ.get("YASA_BUILD_FROM_SOURCE", "0") or "0",
                    "YASA_UAST_VERSION": os.environ.get("YASA_UAST_VERSION") or None,
                }
            ),
        ),
        RunnerPreflightSpec(
            name="opengrep",
            image=str(getattr(settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:latest")),
            command=["opengrep", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/opengrep-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="bandit",
            image=str(getattr(settings, "SCANNER_BANDIT_IMAGE", "vulhunter/bandit-runner:latest")),
            command=["bandit", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/bandit-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="gitleaks",
            image=str(getattr(settings, "SCANNER_GITLEAKS_IMAGE", "vulhunter/gitleaks-runner:latest")),
            command=["gitleaks", "version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/gitleaks-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="phpstan",
            image=str(getattr(settings, "SCANNER_PHPSTAN_IMAGE", "vulhunter/phpstan-runner:latest")),
            command=["php", "/opt/phpstan/phpstan", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/phpstan-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="pmd",
            image=str(getattr(settings, "SCANNER_PMD_IMAGE", "vulhunter/pmd-runner:latest")),
            command=["pmd", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/pmd-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="flow-parser",
            image=str(getattr(settings, "FLOW_PARSER_RUNNER_IMAGE", "vulhunter/flow-parser-runner:latest")),
            command=["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/flow-parser-runner.Dockerfile",
            build_context=build_context,
            build_args=common_args,
        ),
        RunnerPreflightSpec(
            name="sandbox-runner",
            image=str(getattr(settings, "SANDBOX_RUNNER_IMAGE", "vulhunter/sandbox-runner:latest")),
            command=["python3", "-c", "import requests; import httpx; import jwt; print('Sandbox Runner OK')"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
            dockerfile="docker/sandbox-runner.Dockerfile",
            build_context=build_context,
            build_args=_clean_build_args(
                {
                    **common_args,
                    "SANDBOX_RUNNER_APT_MIRROR_PRIMARY": os.environ.get("SANDBOX_RUNNER_APT_MIRROR_PRIMARY", "mirrors.aliyun.com"),
                    "SANDBOX_RUNNER_APT_SECURITY_PRIMARY": os.environ.get("SANDBOX_RUNNER_APT_SECURITY_PRIMARY", "mirrors.aliyun.com"),
                    "SANDBOX_RUNNER_APT_MIRROR_FALLBACK": os.environ.get("SANDBOX_RUNNER_APT_MIRROR_FALLBACK", "deb.debian.org"),
                    "SANDBOX_RUNNER_APT_SECURITY_FALLBACK": os.environ.get("SANDBOX_RUNNER_APT_SECURITY_FALLBACK", "security.debian.org"),
                    "SANDBOX_RUNNER_PYPI_INDEX_PRIMARY": os.environ.get("SANDBOX_RUNNER_PYPI_INDEX_PRIMARY", "https://mirrors.aliyun.com/pypi/simple/"),
                    "SANDBOX_RUNNER_NPM_REGISTRY": os.environ.get("SANDBOX_RUNNER_NPM_REGISTRY", "https://registry.npmmirror.com"),
                }
            ),
        ),
    ]


def _ensure_runner_image(client, spec: RunnerPreflightSpec) -> None:
    try:
        client.images.get(spec.image)
        return
    except DOCKER_NOT_FOUND:
        pass

    build_context = Path(spec.build_context or _backend_build_context())
    if not build_context.exists():
        raise RuntimeError(f"runner build context not found for {spec.name}: {build_context}")
    if not spec.dockerfile:
        raise RuntimeError(f"runner image missing and no dockerfile configured for {spec.name}")

    dockerfile_path = build_context / spec.dockerfile
    if not dockerfile_path.exists():
        raise RuntimeError(
            f"runner dockerfile not found for {spec.name}: {dockerfile_path} "
            f"(build_context={build_context})"
        )

    logger.info("runner preflight build: %s (%s)", spec.name, spec.image)

    # 使用 subprocess 调用 docker build 以支持 BuildKit
    # Docker Python SDK 的 images.build() 不完全支持 BuildKit 特性如 --mount
    build_cmd = [
        "docker", "build",
        "--progress=plain",
        "-f", spec.dockerfile,
        "-t", spec.image,
        str(build_context),
    ]

    # 添加构建参数
    for key, value in spec.build_args.items():
        build_cmd.extend(["--build-arg", f"{key}={value}"])

    # 启用 BuildKit；构建超时通过环境变量配置，默认 900s（15分钟）
    env = os.environ.copy()
    env["DOCKER_BUILDKIT"] = "1"
    build_timeout = int(os.environ.get("RUNNER_PREFLIGHT_BUILD_TIMEOUT_SECONDS", 900) or 900)

    logger.info("running build command: %s", " ".join(build_cmd))

    last_error: Exception | None = None
    for attempt in range(1, 3):  # 最多 2 次尝试
        try:
            subprocess.run(
                build_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=build_timeout,
                check=True,
                cwd=str(build_context),  # Dockerfile 相对路径从构建上下文解析
            )
            logger.info("build completed for %s: %s", spec.name, spec.image)
            return
        except subprocess.CalledProcessError as e:
            last_error = e
            logger.warning(
                "build failed for %s (attempt %d/2): stdout=%s stderr=%s",
                spec.name, attempt, e.stdout[-2000:] if e.stdout else "", e.stderr[-2000:] if e.stderr else "",
            )
            if attempt < 2:
                time.sleep(5)
        except subprocess.TimeoutExpired as e:
            last_error = e
            logger.warning("build timeout for %s (attempt %d/2, >%ds)", spec.name, attempt, build_timeout)
            if attempt < 2:
                time.sleep(5)

    if isinstance(last_error, subprocess.CalledProcessError):
        raise RuntimeError(f"build failed for {spec.name}: {last_error.stderr}")
    raise RuntimeError(f"build timeout for {spec.name} (>{build_timeout}s)")


def run_runner_preflight_sync(spec: RunnerPreflightSpec) -> RunnerPreflightResult:
    container = None
    container_id: str | None = None
    try:
        client = docker.from_env()
        _ensure_runner_image(client, spec)
        container = client.containers.run(
            spec.image,
            spec.command,
            detach=True,
            auto_remove=False,
            environment={},
            working_dir=None,
        )
        container_id = getattr(container, "id", None)
        wait_result = container.wait(timeout=max(1, int(spec.timeout_seconds)))
        exit_code = int((wait_result or {}).get("StatusCode", 1))
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        success = exit_code == 0
        error = None if success else f"runner preflight failed with exit code {exit_code}"
        return RunnerPreflightResult(
            name=spec.name,
            image=spec.image,
            command=list(spec.command),
            timeout_seconds=spec.timeout_seconds,
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error=error,
            container_id=container_id,
        )
    except TimeoutError as exc:
        return RunnerPreflightResult(
            name=spec.name,
            image=spec.image,
            command=list(spec.command),
            timeout_seconds=spec.timeout_seconds,
            success=False,
            exit_code=124,
            stdout="",
            stderr="",
            error=str(exc),
            container_id=container_id,
        )
    except DOCKER_EXCEPTION as exc:
        return RunnerPreflightResult(
            name=spec.name,
            image=spec.image,
            command=list(spec.command),
            timeout_seconds=spec.timeout_seconds,
            success=False,
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
            container_id=container_id,
        )
    except Exception as exc:
        return RunnerPreflightResult(
            name=spec.name,
            image=spec.image,
            command=list(spec.command),
            timeout_seconds=spec.timeout_seconds,
            success=False,
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
            container_id=container_id,
        )
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


async def run_runner_preflight(spec: RunnerPreflightSpec) -> RunnerPreflightResult:
    return await asyncio.to_thread(run_runner_preflight_sync, spec)


async def run_configured_runner_preflights() -> list[RunnerPreflightResult]:
    if not bool(getattr(settings, "RUNNER_PREFLIGHT_ENABLED", True)):
        return []

    specs = get_configured_runner_preflight_specs()
    semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "RUNNER_PREFLIGHT_MAX_CONCURRENCY", 2) or 2)))
    results: list[RunnerPreflightResult] = []

    async def _run(spec: RunnerPreflightSpec) -> RunnerPreflightResult:
        async with semaphore:
            result = await run_runner_preflight(spec)
            if result.success:
                logger.info("runner preflight ok: %s", spec.name)
            else:
                logger.warning("runner preflight failed: %s (%s)", spec.name, result.error or result.stderr or "unknown")
            return result

    for result in await asyncio.gather(*[_run(spec) for spec in specs]):
        results.append(result)

    if bool(getattr(settings, "RUNNER_PREFLIGHT_STRICT", False)):
        failures = [result for result in results if not result.success]
        if failures:
            summary = ", ".join(f"{result.name}: {result.error or result.stderr or result.exit_code}" for result in failures)
            raise RuntimeError(f"runner preflight failed: {summary}")

    return results
