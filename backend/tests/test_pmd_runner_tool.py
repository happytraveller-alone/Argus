import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.tools import external_tools
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


def _runner_option(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return command[index + 1]


async def _run_pmd_tool(
    monkeypatch,
    tmp_path: Path,
    *,
    target_path: str = ".",
    ruleset: str = "security",
    scan_workspace_root: Path | None = None,
    report_payload: dict | None = None,
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
        output_dir = Path(spec.workspace_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(
            json.dumps(report_payload or _build_report()),
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="pmd-tool-1",
            exit_code=4,
            stdout_path=None,
            stderr_path=None,
            error=None,
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
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _create_project(project_root)

    scan_workspace_root = project_root / "scans"
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

    seen: dict[str, object] = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir = Path(spec.workspace_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(json.dumps(_build_report()), encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="pmd-tool-1",
            exit_code=4,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute()

    workspace_dir = Path(seen["spec"].workspace_dir)
    assert result.success is True
    assert workspace_dir == scan_workspace_root / "pmd-tool" / "feedfacefeedfacefeedfacefeedface"
    assert (workspace_dir / "project").is_dir()
    assert (workspace_dir / "output").is_dir()
    assert (workspace_dir / "logs").is_dir()
    assert (workspace_dir / "meta").is_dir()
    assert (workspace_dir / "project" / "src" / "main" / "java" / "App.java").is_file()
    assert not (workspace_dir / "project" / "scans").exists()


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
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _source_dir, local_ruleset = _create_project(project_root)
    monkeypatch.setattr(
        external_tools,
        "settings",
        SimpleNamespace(
            SCAN_WORKSPACE_ROOT=str(tmp_path / "scan-root"),
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
        output_dir = Path(spec.workspace_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(json.dumps(_build_report()), encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="pmd-tool-1",
            exit_code=4,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(
        external_tools,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    tool = PMDTool(str(project_root), sandbox_manager=_SandboxProbe())
    result = await tool._execute(ruleset=str(local_ruleset.relative_to(project_root)))

    workspace_dir = Path(seen["spec"].workspace_dir)
    assert result.success is True
    assert _runner_option(seen["spec"].command, "--rulesets") == "/scan/project/config/pmd/custom.xml"
    assert not (workspace_dir / "meta" / "rules" / "custom.xml").exists()


@pytest.mark.asyncio
async def test_pmd_tool_stages_external_ruleset_into_meta_rules(monkeypatch, tmp_path):
    external_ruleset = tmp_path / "external-rules.xml"
    external_ruleset.write_text("<ruleset name='external'/>\n", encoding="utf-8")

    result, spec, _project_root = await _run_pmd_tool(
        monkeypatch,
        tmp_path,
        ruleset=str(external_ruleset),
    )

    workspace_dir = Path(spec.workspace_dir)
    staged_ruleset = workspace_dir / "meta" / "rules" / "external-rules.xml"
    assert result.success is True
    assert _runner_option(spec.command, "--rulesets") == "/scan/meta/rules/external-rules.xml"
    assert staged_ruleset.read_text(encoding="utf-8") == "<ruleset name='external'/>\n"


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
