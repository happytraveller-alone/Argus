from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


class FakeImages:
    def get(self, _image: str) -> object:
        return object()


class FakeContainer:
    def __init__(self, status_code: int = 0) -> None:
        self.id = "preflight-container-1"
        self.status_code = status_code
        self.wait_calls = 0
        self.log_calls: list[tuple[bool, bool]] = []
        self.remove_calls: list[dict[str, bool]] = []

    def wait(self, timeout: int) -> dict[str, int]:
        self.wait_calls += 1
        self.timeout = timeout
        return {"StatusCode": self.status_code}

    def logs(self, stdout: bool, stderr: bool) -> bytes:
        self.log_calls.append((stdout, stderr))
        if stdout:
            return b"ok"
        return b""

    def remove(self, force: bool) -> None:
        self.remove_calls.append({"force": force})


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.run_kwargs: dict[str, object] | None = None

    def run(self, image: str, command: list[str], **kwargs: object) -> FakeContainer:
        self.image = image
        self.command = command
        self.run_kwargs = kwargs
        return self.container


class FakeDockerClient:
    def __init__(self, container: FakeContainer) -> None:
        self.images = FakeImages()
        self.containers = FakeContainers(container)


def load_runner_preflight_module(container: FakeContainer):
    docker_module = types.SimpleNamespace(
        from_env=lambda: FakeDockerClient(container),
        errors=types.SimpleNamespace(DockerException=RuntimeError, ImageNotFound=LookupError),
    )
    settings_module = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            RUNNER_PREFLIGHT_TIMEOUT_SECONDS=30,
            SCANNER_OPENGREP_IMAGE="opengrep-runner:test",
            RUNNER_PREFLIGHT_ENABLED=True,
            RUNNER_PREFLIGHT_MAX_CONCURRENCY=2,
            RUNNER_PREFLIGHT_STRICT=False,
        )
    )

    previous_modules = {
        name: sys.modules.get(name)
        for name in (
            "docker",
            "app",
            "app.services",
            "app.services.agent",
            "app.services.agent.runtime_settings",
        )
    }
    sys.modules["docker"] = docker_module
    sys.modules["app"] = types.ModuleType("app")
    sys.modules["app.services"] = types.ModuleType("app.services")
    sys.modules["app.services.agent"] = types.ModuleType("app.services.agent")
    sys.modules["app.services.agent.runtime_settings"] = settings_module

    module_path = Path(__file__).resolve().parent / "release-templates" / "runner_preflight.py"
    spec = importlib.util.spec_from_file_location("runner_preflight_under_test", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class RunnerPreflightCleanupTest(unittest.TestCase):
    def test_configured_preflights_cover_static_runner_images(self) -> None:
        module = load_runner_preflight_module(FakeContainer())

        specs = module.get_configured_runner_preflight_specs()

        self.assertEqual(
            [(spec.name, spec.image, spec.command) for spec in specs],
            [
                ("opengrep", "opengrep-runner:test", ["opengrep-scan", "--self-test"]),
            ],
        )

    def test_successful_opengrep_preflight_removes_container_after_logs(self) -> None:
        container = FakeContainer()
        module = load_runner_preflight_module(container)
        spec = module.RunnerPreflightSpec(
            "opengrep",
            "opengrep-runner:test",
            ["opengrep-scan", "--self-test"],
            30,
        )

        result = module.run_runner_preflight_sync(spec)

        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.container_id, "preflight-container-1")
        self.assertEqual(container.wait_calls, 1)
        self.assertEqual(container.log_calls, [(True, False), (False, True)])
        self.assertEqual(container.remove_calls, [{"force": True}])

    def test_failed_preflight_also_removes_container_after_logs(self) -> None:
        container = FakeContainer(status_code=2)
        module = load_runner_preflight_module(container)
        spec = module.RunnerPreflightSpec(
            "opengrep",
            "opengrep-runner:test",
            ["opengrep-scan", "--self-test"],
            30,
        )

        result = module.run_runner_preflight_sync(spec)

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.container_id, "preflight-container-1")
        self.assertEqual(container.wait_calls, 1)
        self.assertEqual(container.log_calls, [(True, False), (False, True)])
        self.assertEqual(container.remove_calls, [{"force": True}])


if __name__ == "__main__":
    unittest.main()
