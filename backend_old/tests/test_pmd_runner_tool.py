import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.agent.tools.external_tools as external_tools
from app.services.agent.tools.external_tools import PMDTool


SECURITY_RULESET = "category/java/security.xml,category/java/errorprone.xml,category/apex/security.xml"
QUICKSTART_RULESET = "category/java/security.xml,category/jsp/security.xml,category/javascript/security.xml"
ALL_RULESET = (
    "category/java/security.xml,"
    "category/jsp/security.xml,"
    "category/javascript/security.xml,"
    "category/html/security.xml,"
    "category/xml/security.xml,"
    "category/plsql/security.xml,"
    "category/apex/security.xml,"
    "category/visualforce/security.xml"
)


class _SandboxProbe:
    is_available = True

    async def initialize(self):
        raise AssertionError("PMD tool should not initialize sandbox manager")

    async def execute_tool_command(self, *_args, **_kwargs):
        raise AssertionError("PMD tool should not execute via sandbox manager")

    def get_diagnosis(self):
        return "sandbox should be unused"


def _create_project(project_root: Path) -> tuple[Path, Path]:
    source_dir = project_root / "src" / "main" / "java"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "App.java").write_text("class App {}\n", encoding="utf-8")

    local_ruleset = project_root / "config" / "pmd" / "custom.xml"
    local_ruleset.parent.mkdir(parents=True, exist_ok=True)
    local_ruleset.write_text("<ruleset name='local'/>\n", encoding="utf-8")

    return source_dir, local_ruleset


def _build_report(file_path: str = "/scan/project/src/main/java/App.java") -> dict:
    return {
        "files": [
            {
                "filename": file_path,
                "violations": [
                    {
                        "beginline": 7,
                        "endline": 9,
                        "rule": "HardCodedCryptoKey",
                        "ruleset": "Security",
                        "priority": 2,
                        "message": "Hard coded key",
                    }
                ],
            }
        ]
    }


_REPORT_UNSET = object()


def _runner_option(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return command[index + 1]


def _build_runner_result(
    *,
    success: bool,
    exit_code: int,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    error: str | None = None,
):
    return SimpleNamespace(
        success=success,
        container_id="pmd-tool-1",
        exit_code=exit_code,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        error=error,
    )


def test_read_pmd_log_excerpt_reads_bounded_tail_excerpt(tmp_path):
    log_path = tmp_path / "stderr.log"
    log_path.write_text(("HEAD " * 2000) + "\nfinal tail marker /tmp/secret/workspace/logs/stderr.log\n", encoding="utf-8")

    excerpt = external_tools._read_pmd_log_excerpt(str(log_path), read_bytes=128, limit=120)

    assert excerpt is not None
    assert "tail marker" in excerpt
    assert "HEAD HEAD HEAD" not in excerpt
    assert "/tmp/secret/workspace/logs/stderr.log" not in excerpt


def test_build_pmd_failure_summary_truncates_and_redacts_details(tmp_path):
    stderr_path = tmp_path / "stderr.log"
    stderr_path.write_text(
        ("prefix " * 2000) + "\njava.lang.IllegalStateException at /tmp/secret/workspace/logs/stderr.log tail\n",
        encoding="utf-8",
    )
    process_result = _build_runner_result(
        success=False,
        exit_code=2,
        error="runner exploded in /tmp/secret/workspace/output/report.json " + ("X" * 800),
        stderr_path=str(stderr_path),
    )

    summary = external_tools._build_pmd_failure_summary(process_result)

    assert "exit_code=2" in summary
    assert "/tmp/secret/workspace" not in summary
    assert "stdout.log" not in summary
    assert "report.json" not in summary
    assert "..." in summary
    assert len(summary) < 700


def test_prepare_pmd_workspace_only_ignores_nested_workspace_subtree(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    nested_source_dir = project_root / "src" / "main" / "java"
    nested_source_dir.mkdir(parents=True, exist_ok=True)
    (nested_source_dir / "App.java").write_text("class App {}\n", encoding="utf-8")
    (project_root / "src" / "shared.txt").write_text("keep me\n", encoding="utf-8")

    scan_workspace_root = project_root / "src" / "scans"
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(scan_workspace_root),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        external_tools,
        "uuid4",
        lambda: SimpleNamespace(hex="feedfacefeedfacefeedfacefeedface"),
        raising=False,
    )

    workspace_dir, project_dir, output_dir, logs_dir, meta_dir = external_tools._prepare_pmd_workspace(
        str(project_root)
    )

    assert workspace_dir == scan_workspace_root / "pmd-tool" / "feedfacefeedfacefeedfacefeedface"
    assert project_dir == workspace_dir / "project"
    assert output_dir.is_dir()
    assert logs_dir.is_dir()
    assert meta_dir.is_dir()
    assert (project_dir / "src" / "main" / "java" / "App.java").read_text(encoding="utf-8") == "class App {}\n"
    assert (project_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "keep me\n"
    assert not (project_dir / "src" / "scans").exists()


def test_resolve_pmd_ruleset_does_not_fallback_to_repo_root_or_cwd(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    meta_dir = tmp_path / "workspace" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    repo_only_ruleset = tmp_path / "repo-only.xml"
    repo_only_ruleset.write_text("<ruleset name='cwd-only'/>\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="repo-only.xml"):
        external_tools._resolve_pmd_ruleset("repo-only.xml", str(project_root), meta_dir)


async def _run_pmd_tool(
    monkeypatch,
    tmp_path: Path,
    *,
    target_path: str = ".",
    ruleset: str = "security",
    scan_workspace_root: Path | None = None,
    report_payload: object = _REPORT_UNSET,
    report_text: str | None = None,
    create_report: bool | None = None,
    exit_code: int = 4,
    runner_success: bool | None = None,
    runner_error: str | None = None,
    stdout_text: str | None = None,
    stderr_text: str | None = None,
    observe_workspace=None,
):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)

    workspace_root = scan_workspace_root or (tmp_path / "scan-root")
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(workspace_root),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        external_tools,
        "uuid4",
        lambda: SimpleNamespace(hex="feedfacefeedfacefeedfacefeedface"),
        raising=False,
    )

    seen: dict[str, object] = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        workspace_dir = Path(spec.workspace_dir)
        output_dir = workspace_dir / "output"
        logs_dir = workspace_dir / "logs"
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        effective_success = runner_success if runner_success is not None else exit_code in {0, 4}
        should_create_report = create_report
        if should_create_report is None:
            should_create_report = (
                report_payload is not _REPORT_UNSET or report_text is not None or exit_code in {0, 4}
            )

        if should_create_report:
            effective_report = report_payload
            if effective_report is _REPORT_UNSET:
                effective_report = {"files": []} if exit_code == 0 else _build_report()
            effective_report_text = report_text or json.dumps(effective_report)
            (output_dir / "report.json").write_text(effective_report_text, encoding="utf-8")

        stdout_path = None
        if stdout_text is not None:
            stdout_path = str(logs_dir / "stdout.log")
            Path(stdout_path).write_text(stdout_text, encoding="utf-8")

        stderr_path = None
        if stderr_text is not None:
            stderr_path = str(logs_dir / "stderr.log")
            Path(stderr_path).write_text(stderr_text, encoding="utf-8")

        if observe_workspace is not None:
            observe_workspace(workspace_dir, spec)

        return _build_runner_result(
            success=effective_success,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            error=runner_error,
        )

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(target_path=target_path, ruleset=ruleset)

    return result, seen.get("spec"), project_root


@pytest.mark.asyncio
async def test_pmd_tool_uses_scanner_runner_image(monkeypatch, tmp_path):
    result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path)

    assert result.success is True
    assert spec is not None
    assert spec.scanner_type == "pmd-tool"
    assert spec.image == "vulhunter/pmd-runner:test"
    assert spec.command[:2] == ["pmd", "check"]
    assert spec.command.count("--report-file") == 1
    assert _runner_option(spec.command, "--report-file") == "/scan/output/report.json"
    assert spec.expected_exit_codes == [0, 4]
    assert spec.env == {}
    assert spec.artifact_paths == ["output/report.json"]
    assert spec.timeout_seconds == 180


@pytest.mark.asyncio
async def test_pmd_tool_does_not_initialize_sandbox(monkeypatch, tmp_path):
    result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path)

    assert result.success is True
    assert spec is not None


@pytest.mark.asyncio
async def test_pmd_tool_creates_workspace_under_scan_workspace_root(monkeypatch, tmp_path):
    scan_workspace_root = tmp_path / "project" / "scans"
    observed: dict[str, bool] = {}
    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        scan_workspace_root=scan_workspace_root,
        observe_workspace=lambda workspace_dir, _spec: observed.update(
            {
                "project_dir": (workspace_dir / "project").is_dir(),
                "output_dir": (workspace_dir / "output").is_dir(),
                "logs_dir": (workspace_dir / "logs").is_dir(),
                "meta_dir": (workspace_dir / "meta").is_dir(),
                "app_file": (workspace_dir / "project" / "src" / "main" / "java" / "App.java").is_file(),
                "recursive_workspace": (
                    workspace_dir
                    / "project"
                    / "scans"
                    / "pmd-tool"
                    / "feedfacefeedfacefeedfacefeedface"
                ).exists(),
            }
        ),
    )

    workspace_dir = Path(spec.workspace_dir)
    assert result.success is True
    assert workspace_dir == scan_workspace_root / "pmd-tool" / "feedfacefeedfacefeedfacefeedface"
    assert observed == {
        "project_dir": True,
        "output_dir": True,
        "logs_dir": True,
        "meta_dir": True,
        "app_file": True,
        "recursive_workspace": False,
    }
    assert not workspace_dir.exists()


@pytest.mark.asyncio
async def test_pmd_tool_uses_scan_project_for_dot_target(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, target_path=".")

    assert _runner_option(spec.command, "--dir") == "/scan/project"


@pytest.mark.asyncio
async def test_pmd_tool_uses_scan_project_for_empty_target(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, target_path="")

    assert _runner_option(spec.command, "--dir") == "/scan/project"


@pytest.mark.asyncio
async def test_pmd_tool_uses_scan_project_for_dot_slash_target(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, target_path="./")

    assert _runner_option(spec.command, "--dir") == "/scan/project"


@pytest.mark.asyncio
async def test_pmd_tool_maps_security_alias_to_exact_rulesets(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, ruleset="security")

    assert _runner_option(spec.command, "--rulesets") == SECURITY_RULESET


@pytest.mark.asyncio
async def test_pmd_tool_maps_quickstart_alias_to_exact_rulesets(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, ruleset="quickstart")

    assert _runner_option(spec.command, "--rulesets") == QUICKSTART_RULESET


@pytest.mark.asyncio
async def test_pmd_tool_maps_all_alias_to_exact_rulesets(monkeypatch, tmp_path):
    _result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, ruleset="all")

    assert _runner_option(spec.command, "--rulesets") == ALL_RULESET


@pytest.mark.asyncio
async def test_pmd_tool_uses_project_local_ruleset_path_without_staging(monkeypatch, tmp_path):
    observed: dict[str, bool] = {}
    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        ruleset="config/pmd/custom.xml",
        observe_workspace=lambda workspace_dir, _spec: observed.update(
            {"staged_local_ruleset": (workspace_dir / "meta" / "rules" / "custom.xml").exists()}
        ),
    )

    workspace_dir = Path(spec.workspace_dir)
    assert result.success is True
    assert _runner_option(spec.command, "--rulesets") == "/scan/project/config/pmd/custom.xml"
    assert observed == {"staged_local_ruleset": False}
    assert not workspace_dir.exists()


@pytest.mark.asyncio
async def test_pmd_tool_stages_external_ruleset_into_meta_rules(monkeypatch, tmp_path):
    external_ruleset = tmp_path / "external-rules.xml"
    external_ruleset.write_text("<ruleset name='external'/>\n", encoding="utf-8")

    observed: dict[str, object] = {}
    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        ruleset=str(external_ruleset),
        observe_workspace=lambda workspace_dir, _spec: observed.update(
            {
                "staged_ruleset_exists": (workspace_dir / "meta" / "rules" / "external-rules.xml").exists(),
                "staged_ruleset_text": (workspace_dir / "meta" / "rules" / "external-rules.xml").read_text(
                    encoding="utf-8"
                ),
            }
        ),
    )

    workspace_dir = Path(spec.workspace_dir)
    assert result.success is True
    assert _runner_option(spec.command, "--rulesets") == "/scan/meta/rules/external-rules.xml"
    assert observed == {
        "staged_ruleset_exists": True,
        "staged_ruleset_text": "<ruleset name='external'/>\n",
    }
    assert not workspace_dir.exists()


@pytest.mark.asyncio
async def test_pmd_tool_rejects_absolute_target_path(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called for invalid target path")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(target_path="/etc")

    assert result.success is False
    assert "绝对路径" in str(result.error or result.data)
    assert called["runner"] is False


@pytest.mark.asyncio
async def test_pmd_tool_rejects_parent_traversal_target_path(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called for invalid target path")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(target_path=r"src\..\secret")

    assert result.success is False
    assert ".." in str(result.error or result.data)
    assert called["runner"] is False


@pytest.mark.asyncio
async def test_pmd_tool_rejects_missing_project_subpath(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called for invalid target path")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(target_path=r"src\missing")

    assert result.success is False
    assert "不存在" in str(result.error or result.data)
    assert "src/missing" in str(result.error or result.data)
    assert called["runner"] is False


@pytest.mark.asyncio
async def test_pmd_tool_rejects_file_target_path(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called for file target path")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(target_path="src/main/java/App.java")

    assert result.success is False
    assert "必须是目录" in str(result.error or result.data)
    assert called["runner"] is False


def test_resolve_pmd_ruleset_rejects_relative_symlink_outside_project(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    meta_dir = tmp_path / "workspace" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    external_ruleset = tmp_path / "outside.xml"
    external_ruleset.write_text("<ruleset name='outside'/>\n", encoding="utf-8")
    escaping_link = project_root / "config" / "pmd" / "escape.xml"
    escaping_link.parent.mkdir(parents=True, exist_ok=True)
    escaping_link.symlink_to(external_ruleset)

    with pytest.raises(ValueError, match="项目目录内"):
        external_tools._resolve_pmd_ruleset("config/pmd/escape.xml", str(project_root), meta_dir)


@pytest.mark.asyncio
async def test_pmd_tool_accepts_exit_code_4_and_parses_report(monkeypatch, tmp_path):
    result, spec, _project_root = await _run_pmd_tool(monkeypatch, tmp_path, exit_code=4)

    assert result.success is True
    assert result.metadata["findings_count"] == 1
    assert result.metadata["high_count"] == 1
    assert result.metadata["medium_count"] == 0
    assert result.metadata["low_count"] == 0
    assert result.metadata["findings"][0]["file"] == "src/main/java/App.java"
    assert result.metadata["raw_result"]["files"][0]["filename"] == "/scan/project/src/main/java/App.java"
    assert "发现 1 个问题" in result.data
    assert "/scan/project" not in result.data
    assert spec.workspace_dir not in result.data


@pytest.mark.asyncio
async def test_pmd_tool_fails_on_unexpected_exit_code(monkeypatch, tmp_path):
    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        exit_code=2,
        runner_success=False,
        runner_error="PMD runner exited unexpectedly",
        stderr_text="java.lang.IllegalStateException: boom",
        report_payload={"files": []},
    )

    error_text = str(result.error or result.data)
    assert result.success is False
    assert "exit_code=2" in error_text
    assert "PMD runner exited unexpectedly" in error_text
    assert "boom" in error_text
    assert spec.workspace_dir not in error_text
    assert "stderr.log" not in error_text
    assert "stdout.log" not in error_text


@pytest.mark.asyncio
async def test_pmd_tool_fails_when_report_missing_for_success_exit(monkeypatch, tmp_path):
    warnings: list[str] = []
    monkeypatch.setattr(
        external_tools.logger,
        "warning",
        lambda message, *args, **_kwargs: warnings.append(message % args if args else message),
    )

    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        exit_code=0,
        create_report=False,
    )

    error_text = str(result.error or result.data)
    assert result.success is False
    assert "报告" in error_text
    assert "缺失" in error_text or "不存在" in error_text
    assert any("report.json" in warning for warning in warnings)
    assert not Path(spec.workspace_dir).exists()


@pytest.mark.asyncio
async def test_pmd_tool_fails_when_report_json_is_invalid(monkeypatch, tmp_path):
    warnings: list[str] = []
    monkeypatch.setattr(
        external_tools.logger,
        "warning",
        lambda message, *args, **_kwargs: warnings.append(message % args if args else message),
    )

    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        exit_code=4,
        report_text="{not-valid-json",
    )

    error_text = str(result.error or result.data)
    assert result.success is False
    assert "JSON" in error_text or "解析" in error_text
    assert any("report.json" in warning for warning in warnings)
    assert not Path(spec.workspace_dir).exists()


@pytest.mark.asyncio
async def test_pmd_tool_fails_when_ruleset_file_cannot_be_resolved(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called when ruleset file is missing")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )
    errors: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        external_tools.logger,
        "error",
        lambda message, *args, **kwargs: errors.append((message, args, kwargs)),
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(ruleset="config/pmd/missing.xml")

    assert result.success is False
    assert "ruleset" in str(result.error or result.data)
    assert "不存在" in str(result.error or result.data)
    assert called["runner"] is False
    assert errors == []


@pytest.mark.asyncio
async def test_pmd_tool_normalizes_scan_project_paths(monkeypatch, tmp_path):
    result, _spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        report_payload=_build_report("/scan/project/src\\main\\java\\App.java"),
    )

    assert result.success is True
    assert result.metadata["findings"][0]["file"] == "src/main/java/App.java"
    assert "文件: src/main/java/App.java" in result.data
    assert "/scan/project" not in result.data


@pytest.mark.asyncio
async def test_pmd_tool_cleans_workspace_after_success_and_failure(monkeypatch, tmp_path):
    observed: dict[str, bool] = {}
    success_result, success_spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path / "success",
        observe_workspace=lambda workspace_dir, _spec: observed.update(
            {
                "success_workspace_exists_during_run": workspace_dir.is_dir(),
                "success_report_exists_during_run": (workspace_dir / "output" / "report.json").exists(),
            }
        ),
    )

    failure_result, failure_spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path / "failure",
        exit_code=2,
        runner_success=False,
        runner_error="container failed",
        stderr_text="permission denied",
        report_payload={"files": []},
        observe_workspace=lambda workspace_dir, _spec: observed.update(
            {"failure_workspace_exists_during_run": workspace_dir.is_dir()}
        ),
    )

    assert success_result.success is True
    assert failure_result.success is False
    assert observed == {
        "success_workspace_exists_during_run": True,
        "success_report_exists_during_run": True,
        "failure_workspace_exists_during_run": True,
    }
    assert not Path(success_spec.workspace_dir).exists()
    assert not Path(failure_spec.workspace_dir).exists()


@pytest.mark.asyncio
async def test_pmd_tool_fails_explicitly_for_unknown_non_xml_ruleset(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
            SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test",
        ),
        raising=False,
    )

    called = {"runner": False}

    async def _fake_run_scanner_container(_spec, **_kwargs):
        called["runner"] = True
        raise AssertionError("runner should not be called for unsupported ruleset aliases")

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(ruleset="custom-security-pack")

    error_text = str(result.error or result.data)
    assert result.success is False
    assert "不支持" in error_text
    assert "custom-security-pack" in error_text
    assert SECURITY_RULESET not in error_text
    assert called["runner"] is False
