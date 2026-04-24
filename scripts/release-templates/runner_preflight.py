from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import docker

from app.services.agent.runtime_settings import settings


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
    timeout_seconds = int(getattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30))
    return [
        RunnerPreflightSpec("opengrep", str(getattr(settings, "SCANNER_OPENGREP_IMAGE", "")), ["opengrep-scan", "--self-test"], timeout_seconds),
    ]


def _ensure_runner_image(client, spec: RunnerPreflightSpec) -> None:
    try:
        client.images.get(spec.image)
        return
    except DOCKER_NOT_FOUND:
        pass

    logger.info("runner preflight pull: %s (%s)", spec.name, spec.image)
    try:
        client.images.pull(spec.image)
    except Exception as exc:  # pragma: no cover - exercised in integration
        raise RuntimeError(
            f"runner image unavailable for {spec.name}: {spec.image}. "
            "Release slim-source mode does not perform local fallback builds."
        ) from exc


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
        return RunnerPreflightResult(spec.name, spec.image, list(spec.command), spec.timeout_seconds, False, 124, "", "", str(exc), container_id)
    except DOCKER_EXCEPTION as exc:
        return RunnerPreflightResult(spec.name, spec.image, list(spec.command), spec.timeout_seconds, False, 1, "", "", str(exc), container_id)
    except Exception as exc:
        return RunnerPreflightResult(spec.name, spec.image, list(spec.command), spec.timeout_seconds, False, 1, "", "", str(exc), container_id)
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

    async def _run(spec: RunnerPreflightSpec) -> RunnerPreflightResult:
        async with semaphore:
            return await run_runner_preflight(spec)

    results = list(await asyncio.gather(*[_run(spec) for spec in specs]))
    if bool(getattr(settings, "RUNNER_PREFLIGHT_STRICT", False)):
        failures = [result for result in results if not result.success]
        if failures:
            summary = ", ".join(
                f"{result.name}: {result.error or result.stderr or result.exit_code}" for result in failures
            )
            raise RuntimeError(f"runner preflight failed: {summary}")
    return results
