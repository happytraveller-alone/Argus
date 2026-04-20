from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List


BACKEND_ENV_FILE = (
    Path(__file__).resolve().parents[4] / "backend" / "docker" / "env" / "backend" / ".env"
)


def _load_env_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not BACKEND_ENV_FILE.exists():
        return values

    for raw_line in BACKEND_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


_ENV_FILE_VALUES = _load_env_file_values()


def _env_value(name: str) -> str | None:
    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value
    return _ENV_FILE_VALUES.get(name)


def _env_text(name: str, default: str) -> str:
    value = str(_env_value(name) or "").strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_value(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = _env_value(name)
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env_value(name)
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _default_ghcr_registry() -> str:
    return _env_text("GHCR_REGISTRY", "ghcr.io")


def _default_namespace(env_name: str, fallback: str) -> str:
    return _env_text(env_name, fallback)


def _default_tag(env_name: str, fallback: str = "latest") -> str:
    return _env_text(env_name, fallback)


def _default_image(name: str) -> str:
    return (
        f"{_default_ghcr_registry()}/"
        f"{_default_namespace('VULHUNTER_IMAGE_NAMESPACE', 'unbengable12')}/"
        f"{name}:{_default_tag('VULHUNTER_IMAGE_TAG')}"
    )


def _normalize_language_token(value: str) -> str:
    return str(value).strip().lower()


def _normalize_languages(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for item in values:
        token = _normalize_language_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _env_language_list(name: str, default: List[str]) -> List[str]:
    value = _env_value(name)
    if value is None:
        return list(default)

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return _normalize_languages(str(item) for item in parsed)

    return _normalize_languages(text.split(","))


class RuntimeSettings:
    def __init__(self) -> None:
        self.BACKEND_RUNTIME_STARTUP_BIN = _env_text(
            "BACKEND_RUNTIME_STARTUP_BIN",
            "/usr/local/bin/backend-runtime-startup",
        )
        self.FLOW_LIGHTWEIGHT_ENABLED = _env_bool("FLOW_LIGHTWEIGHT_ENABLED", True)
        self.LOGIC_AUTHZ_ENABLED = _env_bool("LOGIC_AUTHZ_ENABLED", True)
        self.FLOW_UNREACHABLE_POLICY = _env_text(
            "FLOW_UNREACHABLE_POLICY",
            "degrade_likely",
        )
        self.FLOW_PARSER_RUNNER_IMAGE = _env_text(
            "FLOW_PARSER_RUNNER_IMAGE",
            _default_image("vulhunter-flow-parser-runner"),
        )
        self.FLOW_PARSER_RUNNER_ENABLED = _env_bool(
            "FLOW_PARSER_RUNNER_ENABLED",
            True,
        )
        self.FLOW_PARSER_RUNNER_TIMEOUT_SECONDS = _env_int(
            "FLOW_PARSER_RUNNER_TIMEOUT_SECONDS",
            120,
        )
        self.SCAN_WORKSPACE_ROOT = _env_text(
            "SCAN_WORKSPACE_ROOT",
            "/tmp/vulhunter/scans",
        )
        self.FUNCTION_LOCATOR_LANGUAGES = _env_language_list(
            "FUNCTION_LOCATOR_LANGUAGES",
            ["python", "javascript", "typescript", "java", "kotlin", "c", "cpp"],
        )
        self.SANDBOX_RUNNER_IMAGE = _env_text(
            "SANDBOX_RUNNER_IMAGE",
            _default_image("vulhunter-sandbox-runner"),
        )
        self.SANDBOX_IMAGE = _env_text(
            "SANDBOX_IMAGE",
            _default_image("vulhunter-sandbox-runner"),
        )
        self.SANDBOX_RUNNER_ENABLED = _env_bool("SANDBOX_RUNNER_ENABLED", True)
        self.SANDBOX_TIMEOUT = _env_int("SANDBOX_TIMEOUT", 60)
        self.SANDBOX_MEMORY_LIMIT = _env_text("SANDBOX_MEMORY_LIMIT", "512m")
        self.SANDBOX_CPU_LIMIT = _env_float("SANDBOX_CPU_LIMIT", 1.0)
        self.LLM_FIRST_TOKEN_TIMEOUT = _env_int("LLM_FIRST_TOKEN_TIMEOUT", 45)
        self.LLM_STREAM_TIMEOUT = _env_int("LLM_STREAM_TIMEOUT", 120)
        self.AGENT_TIMEOUT_SECONDS = _env_int("AGENT_TIMEOUT_SECONDS", 1800)
        self.SUB_AGENT_TIMEOUT_SECONDS = _env_int("SUB_AGENT_TIMEOUT_SECONDS", 600)
        self.TOOL_TIMEOUT_SECONDS = _env_int("TOOL_TIMEOUT_SECONDS", 60)
        self.RUNNER_PREFLIGHT_ENABLED = _env_bool("RUNNER_PREFLIGHT_ENABLED", True)
        self.RUNNER_PREFLIGHT_STRICT = _env_bool("RUNNER_PREFLIGHT_STRICT", False)
        self.RUNNER_PREFLIGHT_TIMEOUT_SECONDS = _env_int(
            "RUNNER_PREFLIGHT_TIMEOUT_SECONDS",
            30,
        )
        self.RUNNER_PREFLIGHT_MAX_CONCURRENCY = _env_int(
            "RUNNER_PREFLIGHT_MAX_CONCURRENCY",
            2,
        )
        self.SCANNER_OPENGREP_IMAGE = _env_text(
            "SCANNER_OPENGREP_IMAGE",
            _default_image("vulhunter-opengrep-runner"),
        )
        self.SCANNER_BANDIT_IMAGE = _env_text(
            "SCANNER_BANDIT_IMAGE",
            _default_image("vulhunter-bandit-runner"),
        )
        self.SCANNER_GITLEAKS_IMAGE = _env_text(
            "SCANNER_GITLEAKS_IMAGE",
            _default_image("vulhunter-gitleaks-runner"),
        )
        self.SCANNER_PHPSTAN_IMAGE = _env_text(
            "SCANNER_PHPSTAN_IMAGE",
            _default_image("vulhunter-phpstan-runner"),
        )
        self.SCANNER_PMD_IMAGE = _env_text(
            "SCANNER_PMD_IMAGE",
            _default_image("vulhunter-pmd-runner"),
        )


settings = RuntimeSettings()


__all__ = ["RuntimeSettings", "settings"]
