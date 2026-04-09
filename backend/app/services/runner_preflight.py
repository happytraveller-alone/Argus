from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

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


def get_configured_runner_preflight_specs() -> list[RunnerPreflightSpec]:
    return [
        RunnerPreflightSpec(
            name="yasa",
            image=str(getattr(settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:latest")),
            command=["/opt/yasa/bin/yasa", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="opengrep",
            image=str(getattr(settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:latest")),
            command=["opengrep", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="bandit",
            image=str(getattr(settings, "SCANNER_BANDIT_IMAGE", "vulhunter/bandit-runner:latest")),
            command=["bandit", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="gitleaks",
            image=str(getattr(settings, "SCANNER_GITLEAKS_IMAGE", "vulhunter/gitleaks-runner:latest")),
            command=["gitleaks", "version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="phpstan",
            image=str(getattr(settings, "SCANNER_PHPSTAN_IMAGE", "vulhunter/phpstan-runner:latest")),
            command=["php", "/opt/phpstan/phpstan", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="pmd",
            image=str(getattr(settings, "SCANNER_PMD_IMAGE", "vulhunter/pmd-runner:latest")),
            command=["pmd", "--version"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="flow-parser",
            image=str(getattr(settings, "FLOW_PARSER_RUNNER_IMAGE", "vulhunter/flow-parser-runner:latest")),
            command=["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
        RunnerPreflightSpec(
            name="sandbox-runner",
            image=str(getattr(settings, "SANDBOX_RUNNER_IMAGE", "vulhunter/sandbox-runner:latest")),
            command=["python3", "-c", "import requests; import httpx; import jwt; print('Sandbox Runner OK')"],
            timeout_seconds=int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30)),
        ),
    ]


def _ensure_runner_image(client, spec: RunnerPreflightSpec) -> None:
    try:
        client.images.get(spec.image)
        return
    except DOCKER_NOT_FOUND:
        pass

    # 优先尝试从 registry 拉取
    try:
        logger.info("runner preflight pull: %s (%s)", spec.name, spec.image)
        client.images.pull(spec.image)
        logger.info("pull completed for %s: %s", spec.name, spec.image)
        return
    except Exception as exc:
        logger.warning("pull failed for %s (%s): %s", spec.name, spec.image, exc)
        raise RuntimeError(f"pull failed for {spec.name}: {exc}") from exc


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
