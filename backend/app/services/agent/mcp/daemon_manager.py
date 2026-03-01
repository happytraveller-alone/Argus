from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

from .health_probe import probe_mcp_endpoint_readiness


logger = logging.getLogger(__name__)


def _parse_args(raw_args: Any) -> List[str]:
    if isinstance(raw_args, list):
        return [str(item) for item in raw_args if str(item).strip()]
    text = str(raw_args or "").strip()
    if not text:
        return []
    try:
        return [str(item) for item in shlex.split(text) if str(item).strip()]
    except Exception:
        return [item for item in text.split(" ") if item]


def _parse_csv_values(raw_value: Any) -> List[str]:
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value]
    else:
        values = [part.strip() for part in str(raw_value or "").split(",")]
    return [item for item in values if item]


def _upsert_option(args: List[str], flag: str, value: str) -> List[str]:
    updated = [str(item) for item in args]
    for idx, item in enumerate(updated):
        text = str(item or "").strip()
        if text == flag:
            if idx + 1 < len(updated):
                updated[idx + 1] = value
            else:
                updated.append(value)
            return updated
        if text.startswith(f"{flag}="):
            updated[idx] = f"{flag}={value}"
            return updated
    updated.extend([flag, value])
    return updated


def _remove_option(args: List[str], flag: str) -> List[str]:
    updated: List[str] = []
    skip_next = False
    for item in args:
        if skip_next:
            skip_next = False
            continue
        text = str(item or "").strip()
        if text == flag:
            skip_next = True
            continue
        if text.startswith(f"{flag}="):
            continue
        updated.append(str(item))
    return updated


def _looks_like_node_command(command: Any) -> bool:
    command_text = str(command or "").strip()
    if not command_text:
        return False
    return Path(command_text).name.lower() in {"node", "nodejs"}


def _resolve_executable(command: str) -> Optional[str]:
    text = str(command or "").strip()
    if not text:
        return None
    if os.path.isabs(text):
        if os.path.isfile(text) and os.access(text, os.X_OK):
            return text
        return None

    resolved = shutil.which(text)
    if resolved:
        return resolved

    for base_dir in (
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        "/app/.venv/bin",
    ):
        candidate = os.path.join(base_dir, text)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def build_local_mcp_url(host: str, port: int) -> str:
    normalized_host = str(host or "127.0.0.1").strip() or "127.0.0.1"
    return f"http://{normalized_host}:{int(port)}/mcp"


def get_default_code_index_daemon_url(settings: Any) -> str:
    return build_local_mcp_url(
        str(getattr(settings, "MCP_CODE_INDEX_DAEMON_HOST", "127.0.0.1") or "127.0.0.1"),
        int(getattr(settings, "MCP_CODE_INDEX_DAEMON_PORT", 8765) or 8765),
    )


def get_default_qmd_daemon_url(settings: Any) -> str:
    return build_local_mcp_url(
        str(getattr(settings, "MCP_QMD_DAEMON_HOST", "localhost") or "localhost"),
        int(getattr(settings, "MCP_QMD_DAEMON_PORT", 8181) or 8181),
    )


def get_default_sequential_daemon_url(settings: Any) -> str:
    return build_local_mcp_url(
        str(getattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_HOST", "127.0.0.1") or "127.0.0.1"),
        int(getattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_PORT", 8771) or 8771),
    )


def get_default_filesystem_daemon_url(settings: Any) -> str:
    return build_local_mcp_url(
        str(getattr(settings, "MCP_FILESYSTEM_DAEMON_HOST", "127.0.0.1") or "127.0.0.1"),
        int(getattr(settings, "MCP_FILESYSTEM_DAEMON_PORT", 8770) or 8770),
    )


def resolve_code_index_backend_url(settings: Any) -> str:
    explicit = str(getattr(settings, "MCP_CODE_INDEX_BACKEND_URL", "") or "").strip()
    if explicit:
        return explicit
    if bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)):
        return get_default_code_index_daemon_url(settings)
    return ""


def resolve_qmd_backend_url(settings: Any) -> str:
    explicit = str(getattr(settings, "MCP_QMD_BACKEND_URL", "") or "").strip()
    if explicit:
        normalized = normalize_qmd_loopback_url(explicit)
        return normalized or explicit
    if bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)):
        normalized = normalize_qmd_loopback_url(get_default_qmd_daemon_url(settings))
        return normalized or get_default_qmd_daemon_url(settings)
    return ""


def resolve_sequential_backend_url(settings: Any) -> str:
    if bool(getattr(settings, "MCP_SEQUENTIAL_THINKING_FORCE_STDIO", True)):
        return ""
    explicit = str(getattr(settings, "MCP_SEQUENTIAL_THINKING_BACKEND_URL", "") or "").strip()
    if explicit:
        return explicit
    if bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)):
        return get_default_sequential_daemon_url(settings)
    return ""


def resolve_filesystem_backend_url(settings: Any) -> str:
    explicit = str(getattr(settings, "MCP_FILESYSTEM_BACKEND_URL", "") or "").strip()
    if explicit:
        return explicit
    if bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)):
        return get_default_filesystem_daemon_url(settings)
    return ""


def normalize_qmd_loopback_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return value
    parsed = urlparse(value)
    host = str(parsed.hostname or "").strip().lower()
    if host != "127.0.0.1":
        return value
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    netloc = f"localhost:{port}"
    return urlunparse(parsed._replace(netloc=netloc))


@dataclass
class MCPDaemonSpec:
    name: str
    url: str
    command: str
    args: List[str]
    fallback_commands: List[List[str]] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    startup_timeout_seconds: int = 45
    log_file: Optional[str] = None


@dataclass
class MCPDaemonLaunchResult:
    name: str
    ready: bool
    started: bool
    reason: str
    url: str
    pid: Optional[int] = None
    command: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ready": self.ready,
            "started": self.started,
            "reason": self.reason,
            "url": self.url,
            "pid": self.pid,
            "command": self.command,
        }


class MCPDaemonManager:
    def __init__(self) -> None:
        self._processes: Dict[str, subprocess.Popen[Any]] = {}
        self._log_handles: Dict[str, Any] = {}

    @classmethod
    def _endpoint_ready(cls, url: str) -> bool:
        ready, _reason = probe_mcp_endpoint_readiness(url, timeout=1.5)
        return bool(ready)

    @staticmethod
    def _build_code_index_args(settings: Any) -> List[str]:
        args = _parse_args(getattr(settings, "MCP_CODE_INDEX_DAEMON_ARGS", "--transport streamable-http"))
        port = int(getattr(settings, "MCP_CODE_INDEX_DAEMON_PORT", 8765) or 8765)
        indexer_path = str(
            getattr(settings, "MCP_CODE_INDEX_DAEMON_INDEXER_PATH", "/app/data/mcp/code-index")
            or "/app/data/mcp/code-index"
        )

        args = _remove_option(args, "--host")
        args = _upsert_option(args, "--transport", "streamable-http")
        args = _upsert_option(args, "--port", str(port))
        args = _upsert_option(args, "--indexer-path", indexer_path)
        return args

    @staticmethod
    def _build_qmd_args(settings: Any) -> List[str]:
        command = str(getattr(settings, "MCP_QMD_DAEMON_COMMAND", "qmd") or "qmd")
        node_mode = _looks_like_node_command(command)
        default_args = (
            "dist/index.js mcp --transport streamable-http"
            if node_mode
            else "mcp --transport streamable-http"
        )
        args = _parse_args(getattr(settings, "MCP_QMD_DAEMON_ARGS", default_args))
        port = int(getattr(settings, "MCP_QMD_DAEMON_PORT", 8181) or 8181)
        if node_mode:
            if not args:
                args = ["dist/index.js", "mcp"]
            first = str(args[0] or "").strip()
            first_lower = first.lower()
            if first.startswith("-"):
                args = ["dist/index.js", "mcp", *args]
            elif first_lower == "mcp":
                args = ["dist/index.js", *args]
            elif not first_lower.endswith(".js"):
                args = ["dist/index.js", *args]
            if len(args) < 2 or str(args[1] or "").strip().lower() != "mcp":
                args = [args[0], "mcp", *args[1:]]
        else:
            if not args or str(args[0]).strip().lower() != "mcp":
                args = ["mcp", *args]
        args = [
            str(item)
            for item in args
            if str(item).strip() != "--http"
            and not str(item).strip().startswith("--http=")
        ]
        args = _upsert_option(args, "--transport", "streamable-http")
        args = _upsert_option(args, "--port", str(port))
        return args

    @staticmethod
    def _build_sequential_args(settings: Any) -> List[str]:
        args = _parse_args(
            getattr(
                settings,
                "MCP_SEQUENTIAL_THINKING_DAEMON_ARGS",
                "dist/index.js --transport streamable-http --port 8771",
            )
        )
        port = int(getattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_PORT", 8771) or 8771)
        args = _remove_option(args, "--host")
        args = _upsert_option(args, "--transport", "streamable-http")
        args = _upsert_option(args, "--port", str(port))
        return args

    @staticmethod
    def _filesystem_allowed_dirs(settings: Any) -> List[str]:
        configured = _parse_csv_values(
            getattr(settings, "MCP_FILESYSTEM_DAEMON_ALLOWED_DIRS", "/tmp,/app")
        )
        normalized: List[str] = []
        for item in configured:
            candidate = os.path.normpath(str(item))
            if not os.path.isabs(candidate):
                candidate = os.path.abspath(candidate)
            if candidate not in normalized:
                normalized.append(candidate)
        if not normalized:
            normalized = ["/tmp", "/app"]
        return normalized

    @staticmethod
    def _filesystem_proxy_path(spec: MCPDaemonSpec) -> str:
        if spec.log_file:
            return str(Path(spec.log_file).with_name("filesystem.proxy.json"))
        return "/tmp/deepaudit/mcp-daemons/filesystem.proxy.json"

    @classmethod
    def _resolve_filesystem_backend_command(
        cls,
        spec: MCPDaemonSpec,
    ) -> tuple[Optional[str], List[str], str]:
        allowed_dirs = _parse_csv_values((spec.env or {}).get("MCP_FILESYSTEM_ALLOWED_DIRS", ""))
        if not allowed_dirs:
            allowed_dirs = ["/tmp", "/app"]

        filesystem_bin = _resolve_executable("mcp-server-filesystem")
        if filesystem_bin:
            return filesystem_bin, allowed_dirs, "binary"

        source_dir = str(spec.cwd or "").strip()
        if not source_dir:
            return None, [], "filesystem_source_dir_missing"
        source_path = Path(source_dir)
        if not source_path.is_dir():
            return None, [], f"filesystem_source_missing:{source_dir}"

        package_json = source_path / "package.json"
        if not package_json.exists():
            return None, [], f"filesystem_package_json_missing:{source_dir}"

        dist_entry = source_path / "dist/index.js"
        if not dist_entry.exists():
            prepared, reason = cls._prepare_node_source(
                MCPDaemonSpec(
                    name=spec.name,
                    url=spec.url,
                    command="node",
                    args=["dist/index.js"],
                    cwd=source_dir,
                ),
                name="filesystem",
            )
            if not prepared:
                return None, [], reason

        node_exec = _resolve_executable("node")
        if not node_exec:
            return None, [], "filesystem_node_missing"
        return node_exec, [str(dist_entry), *allowed_dirs], "node_source"

    @classmethod
    def _prepare_filesystem_proxy(cls, spec: MCPDaemonSpec) -> tuple[bool, str]:
        fastmcp_exec = _resolve_executable(str(spec.command or "").strip())
        if not fastmcp_exec:
            return False, "filesystem_fastmcp_missing"

        backend_command, backend_args, backend_mode = cls._resolve_filesystem_backend_command(spec)
        if not backend_command:
            return False, backend_mode or "filesystem_backend_unavailable"

        parsed = urlparse(str(spec.url or "").strip())
        host = str(parsed.hostname or "").strip() or "127.0.0.1"
        if parsed.port:
            port = int(parsed.port)
        elif str(parsed.scheme).lower() == "https":
            port = 443
        else:
            port = 80
        route_path = str(parsed.path or "").strip() or "/mcp"

        proxy_path = cls._filesystem_proxy_path(spec)
        proxy_file = Path(proxy_path)
        proxy_file.parent.mkdir(parents=True, exist_ok=True)
        proxy_payload = {
            "mcpServers": {
                "filesystem": {
                    "command": backend_command,
                    "args": [str(item) for item in backend_args],
                }
            }
        }
        proxy_file.write_text(
            json.dumps(proxy_payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        spec.command = fastmcp_exec
        spec.args = [
            "run",
            proxy_path,
            "--transport",
            "streamable-http",
            "--host",
            host,
            "--port",
            str(port),
            "--path",
            route_path,
        ]
        return True, f"ready:{backend_mode}"

    @classmethod
    def build_specs(cls, settings: Any, *, project_root: Optional[str]) -> List[MCPDaemonSpec]:
        if not bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)):
            return []

        log_dir = str(getattr(settings, "MCP_DAEMON_LOG_DIR", "/tmp/deepaudit/mcp-daemons") or "/tmp/deepaudit/mcp-daemons")
        filesystem_url = resolve_filesystem_backend_url(settings)
        code_index_url = resolve_code_index_backend_url(settings)
        sequential_url = resolve_sequential_backend_url(settings)
        qmd_url = resolve_qmd_backend_url(settings)

        filesystem_source_dir = str(
            getattr(
                settings,
                "MCP_FILESYSTEM_DAEMON_SOURCE_DIR",
                "/app/mcp-src/filesystem",
            )
            or "/app/mcp-src/filesystem"
        )
        filesystem_spec = MCPDaemonSpec(
            name="filesystem",
            url=filesystem_url,
            command=str(getattr(settings, "MCP_FILESYSTEM_DAEMON_COMMAND", "fastmcp") or "fastmcp"),
            args=_parse_args(getattr(settings, "MCP_FILESYSTEM_DAEMON_ARGS", "")),
            fallback_commands=[["/app/.venv/bin/fastmcp"], ["fastmcp"]],
            cwd=filesystem_source_dir,
            env={
                "MCP_FILESYSTEM_ALLOWED_DIRS": ",".join(cls._filesystem_allowed_dirs(settings)),
            },
            startup_timeout_seconds=max(
                10,
                int(getattr(settings, "MCP_FILESYSTEM_DAEMON_STARTUP_TIMEOUT_SECONDS", 45) or 45),
            ),
            log_file=str(Path(log_dir) / "filesystem.log"),
        )

        sequential_source_dir = str(
            getattr(
                settings,
                "MCP_SEQUENTIAL_THINKING_DAEMON_SOURCE_DIR",
                "/app/mcp-src/sequential-thinking",
            )
            or "/app/mcp-src/sequential-thinking"
        )
        sequential_force_stdio = bool(
            getattr(settings, "MCP_SEQUENTIAL_THINKING_FORCE_STDIO", True)
        )
        sequential_spec = None
        if not sequential_force_stdio:
            sequential_spec = MCPDaemonSpec(
                name="sequentialthinking",
                url=sequential_url,
                command=str(getattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_COMMAND", "node") or "node"),
                args=cls._build_sequential_args(settings),
                fallback_commands=[["mcp-server-sequential-thinking"]],
                cwd=sequential_source_dir,
                env={},
                startup_timeout_seconds=max(
                    10,
                    int(getattr(settings, "MCP_SEQUENTIAL_THINKING_DAEMON_STARTUP_TIMEOUT_SECONDS", 45) or 45),
                ),
                log_file=str(Path(log_dir) / "sequentialthinking.log"),
            )

        code_index_source_dir = str(
            getattr(
                settings,
                "MCP_CODE_INDEX_DAEMON_SOURCE_DIR",
                "/app/mcp-src/code-index-mcp",
            )
            or "/app/mcp-src/code-index-mcp"
        )
        code_index_cwd = code_index_source_dir if code_index_source_dir else project_root
        code_index_spec = MCPDaemonSpec(
            name="code_index",
            url=code_index_url,
            command=str(getattr(settings, "MCP_CODE_INDEX_DAEMON_COMMAND", "code-index-mcp") or "code-index-mcp"),
            args=cls._build_code_index_args(settings),
            fallback_commands=[["/app/.venv/bin/code-index-mcp"], ["/usr/local/bin/code-index-mcp"]],
            cwd=code_index_cwd,
            env={},
            startup_timeout_seconds=max(
                10,
                int(getattr(settings, "MCP_CODE_INDEX_DAEMON_STARTUP_TIMEOUT_SECONDS", 45) or 45),
            ),
            log_file=str(Path(log_dir) / "code_index.log"),
        )

        qmd_env: Dict[str, str] = {}
        qmd_data_dir = str(getattr(settings, "QMD_DATA_DIR", "") or "").strip()
        if qmd_data_dir:
            qmd_env["QMD_DATA_DIR"] = qmd_data_dir
        xdg_config_home = str(getattr(settings, "XDG_CONFIG_HOME", "") or "").strip()
        if xdg_config_home:
            qmd_env["XDG_CONFIG_HOME"] = xdg_config_home

        qmd_source_dir = str(
            getattr(
                settings,
                "MCP_QMD_DAEMON_SOURCE_DIR",
                "/app/mcp-src/qmd",
            )
            or "/app/mcp-src/qmd"
        )
        qmd_spec = MCPDaemonSpec(
            name="qmd",
            url=qmd_url,
            command=str(getattr(settings, "MCP_QMD_DAEMON_COMMAND", "node") or "node"),
            args=cls._build_qmd_args(settings),
            fallback_commands=[],
            cwd=qmd_source_dir if qmd_source_dir else project_root,
            env=qmd_env,
            startup_timeout_seconds=max(
                10,
                int(getattr(settings, "MCP_QMD_DAEMON_STARTUP_TIMEOUT_SECONDS", 60) or 60),
            ),
            log_file=str(Path(log_dir) / "qmd.log"),
        )
        specs: List[MCPDaemonSpec] = [filesystem_spec, code_index_spec]
        if sequential_spec is not None:
            specs.append(sequential_spec)
        specs.append(qmd_spec)
        return specs

    @staticmethod
    def _strip_node_entrypoint(args: List[str]) -> List[str]:
        normalized = [str(item) for item in (args or [])]
        if not normalized:
            return normalized
        first = str(normalized[0] or "").strip().lower()
        if first.endswith(".js"):
            return normalized[1:]
        return normalized

    def _command_candidates(self, spec: MCPDaemonSpec) -> Iterable[List[str]]:
        primary = str(spec.command or "").strip()
        if primary:
            resolved_primary = _resolve_executable(primary) or primary
            yield [resolved_primary, *spec.args]
        for fallback in spec.fallback_commands:
            candidate_prefix = [str(item) for item in fallback if str(item).strip()]
            if candidate_prefix:
                fallback_args = [str(item) for item in spec.args]
                if str(spec.name or "").strip() in {"filesystem", "sequentialthinking", "qmd"}:
                    fallback_args = self._strip_node_entrypoint(fallback_args)
                yield [*candidate_prefix, *fallback_args]

    def _open_log_handle(self, spec: MCPDaemonSpec):
        if not spec.log_file:
            return subprocess.DEVNULL, None
        path = Path(spec.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8")
        return handle, handle

    def _wait_ready(self, spec: MCPDaemonSpec, process: subprocess.Popen[Any]) -> bool:
        deadline = time.time() + max(5, int(spec.startup_timeout_seconds))
        while time.time() < deadline:
            if self._endpoint_ready(spec.url):
                return True
            if process.poll() is not None:
                return False
            time.sleep(0.35)
        return self._endpoint_ready(spec.url)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                return

    @staticmethod
    def _prepare_node_source(spec: MCPDaemonSpec, *, name: str) -> tuple[bool, str]:
        source_dir = str(spec.cwd or "").strip()
        if not source_dir:
            return False, f"{name}_source_dir_missing"
        source_path = Path(source_dir)
        if not source_path.is_dir():
            return False, f"{name}_source_missing:{source_dir}"
        package_json = source_path / "package.json"
        if not package_json.exists():
            return False, f"{name}_package_json_missing:{source_dir}"

        expected_entry = str(spec.args[0] or "").strip() if spec.args else "dist/index.js"
        if expected_entry.startswith("-"):
            expected_entry = "dist/index.js"
        dist_entry = source_path / expected_entry
        if dist_entry.exists():
            return True, "ready"

        env = dict(os.environ)
        env.setdefault("NODE_ENV", "production")
        env.setdefault("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com")

        pnpm_executable = _resolve_executable("pnpm")
        pnpm_error: Optional[Exception] = None
        if pnpm_executable:
            pnpm_install_cmd = (
                [pnpm_executable, "install", "--frozen-lockfile"]
                if (source_path / "pnpm-lock.yaml").exists()
                else [pnpm_executable, "install"]
            )
            pnpm_build_cmd = [pnpm_executable, "run", "build"]
            try:
                subprocess.run(
                    pnpm_install_cmd,
                    cwd=str(source_path),
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=180,
                )
                subprocess.run(
                    pnpm_build_cmd,
                    cwd=str(source_path),
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=180,
                )
                if dist_entry.exists():
                    return True, "ready"
            except Exception as exc:
                pnpm_error = exc
                logger.warning(
                    "Prepare node source with pnpm failed (%s): %s; fallback to npm",
                    name,
                    exc.__class__.__name__,
                )

        npm_executable = _resolve_executable("npm")
        if not npm_executable:
            if pnpm_error is not None:
                return False, f"{name}_pnpm_failed_and_npm_missing:{pnpm_error.__class__.__name__}"
            return False, f"{name}_npm_missing"

        install_cmd = (
            [npm_executable, "ci"]
            if (source_path / "package-lock.json").exists()
            else [npm_executable, "install"]
        )
        build_cmd = [npm_executable, "run", "build"]

        try:
            subprocess.run(
                install_cmd,
                cwd=str(source_path),
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
            )
            subprocess.run(
                build_cmd,
                cwd=str(source_path),
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
            )
        except Exception as exc:
            return False, f"{name}_build_failed:{exc.__class__.__name__}"

        if not dist_entry.exists():
            return False, f"{name}_dist_missing_after_build:{expected_entry}"
        return True, "ready"

    @staticmethod
    def _prepare_code_index_source(spec: MCPDaemonSpec) -> tuple[bool, str]:
        command = str(spec.command or "").strip()
        if _resolve_executable(command):
            return True, "ready"
        source_dir = str(spec.cwd or "").strip()
        if not source_dir:
            return False, "code_index_source_dir_missing"
        source_path = Path(source_dir)
        if not source_path.is_dir():
            return False, f"code_index_source_missing:{source_dir}"
        has_build_manifest = (source_path / "pyproject.toml").exists() or (source_path / "setup.py").exists()
        if not has_build_manifest:
            return False, f"code_index_build_manifest_missing:{source_dir}"
        return True, "ready"

    @staticmethod
    def _normalize_qmd_cli_args(args: List[str]) -> List[str]:
        normalized = [str(item) for item in (args or []) if str(item).strip()]
        if normalized and str(normalized[0]).strip().lower().endswith(".js"):
            normalized = normalized[1:]
        if not normalized or str(normalized[0]).strip().lower() != "mcp":
            normalized = ["mcp", *normalized]
        return normalized

    def _prepare_spec(self, spec: MCPDaemonSpec) -> tuple[bool, str]:
        spec_name = str(spec.name or "").strip()
        if spec_name == "filesystem":
            return self._prepare_filesystem_proxy(spec)
        if spec_name == "sequentialthinking":
            return self._prepare_node_source(spec, name="sequentialthinking")
        if spec_name == "qmd" and _looks_like_node_command(spec.command):
            prepared, reason = self._prepare_node_source(spec, name="qmd")
            if prepared:
                return prepared, reason
            qmd_exec = _resolve_executable("qmd")
            if qmd_exec:
                spec.command = qmd_exec
                spec.args = self._normalize_qmd_cli_args(spec.args)
                spec.cwd = None
                return True, f"ready_fallback_qmd_cli:{reason}"
            return False, reason
        if spec_name == "code_index":
            return self._prepare_code_index_source(spec)
        return True, "ready"

    def ensure_daemon(self, spec: MCPDaemonSpec) -> MCPDaemonLaunchResult:
        if self._endpoint_ready(spec.url):
            return MCPDaemonLaunchResult(
                name=spec.name,
                ready=True,
                started=False,
                reason="already_running",
                url=spec.url,
            )

        prepared, prepare_reason = self._prepare_spec(spec)
        if not prepared:
            return MCPDaemonLaunchResult(
                name=spec.name,
                ready=False,
                started=False,
                reason=prepare_reason,
                url=spec.url,
            )

        existing = self._processes.get(spec.name)
        if existing is not None and existing.poll() is None:
            if self._wait_ready(spec, existing):
                return MCPDaemonLaunchResult(
                    name=spec.name,
                    ready=True,
                    started=False,
                    reason="managed_process_running",
                    url=spec.url,
                    pid=getattr(existing, "pid", None),
                )
            self._terminate_process(existing)

        last_reason = "command_not_found"
        has_non_missing_reason = False
        for candidate in self._command_candidates(spec):
            if not candidate:
                continue
            command_text = " ".join(candidate)
            out_stream, handle = self._open_log_handle(spec)
            env = {**os.environ, **(spec.env or {})}
            cwd = str(spec.cwd or "").strip() or None
            if cwd:
                try:
                    os.makedirs(cwd, exist_ok=True)
                except Exception:
                    pass
            try:
                process = subprocess.Popen(
                    candidate,
                    cwd=cwd,
                    env=env,
                    stdout=out_stream,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except FileNotFoundError:
                if not has_non_missing_reason:
                    last_reason = "command_not_found"
                if handle is not None:
                    handle.close()
                continue
            except Exception as exc:
                last_reason = f"spawn_failed:{exc.__class__.__name__}"
                has_non_missing_reason = True
                if handle is not None:
                    handle.close()
                continue

            if self._wait_ready(spec, process):
                self._processes[spec.name] = process
                if handle is not None:
                    self._log_handles[spec.name] = handle
                return MCPDaemonLaunchResult(
                    name=spec.name,
                    ready=True,
                    started=True,
                    reason="started",
                    url=spec.url,
                    pid=getattr(process, "pid", None),
                    command=command_text,
                )

            self._terminate_process(process)
            if handle is not None:
                handle.close()
            last_reason = f"startup_timeout_or_failed:{command_text}"
            has_non_missing_reason = True

        return MCPDaemonLaunchResult(
            name=spec.name,
            ready=False,
            started=False,
            reason=last_reason,
            url=spec.url,
        )

    def autostart(self, specs: Iterable[MCPDaemonSpec]) -> Dict[str, MCPDaemonLaunchResult]:
        results: Dict[str, MCPDaemonLaunchResult] = {}
        for spec in specs:
            result = self.ensure_daemon(spec)
            results[spec.name] = result
            if result.ready:
                logger.info("[MCP Daemon] %s ready (%s)", spec.name, result.reason)
            else:
                logger.warning("[MCP Daemon] %s unavailable (%s)", spec.name, result.reason)
        return results

    def stop_all(self) -> None:
        for name, process in list(self._processes.items()):
            self._terminate_process(process)
            self._processes.pop(name, None)
        for name, handle in list(self._log_handles.items()):
            try:
                handle.close()
            except Exception:
                pass
            self._log_handles.pop(name, None)
