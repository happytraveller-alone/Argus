from types import SimpleNamespace

import pytest

from app.services.agent.bootstrap.yasa import YasaBootstrapScanner


@pytest.mark.asyncio
async def test_yasa_bootstrap_scanner_uses_scanner_runner(monkeypatch, tmp_path):
    output_dir = tmp_path / "scans" / "yasa-bootstrap" / "output"
    logs_dir = tmp_path / "scans" / "yasa-bootstrap" / "logs"
    project_dir = tmp_path / "scans" / "yasa-bootstrap" / "project"
    output_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (tmp_path / "repo").mkdir()

    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.ensure_scan_workspace",
        lambda *_args, **_kwargs: project_dir.parent,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.ensure_scan_project_dir",
        lambda *_args, **_kwargs: project_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.ensure_scan_output_dir",
        lambda *_args, **_kwargs: output_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.ensure_scan_logs_dir",
        lambda *_args, **_kwargs: logs_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.settings",
        SimpleNamespace(
            YASA_TIMEOUT_SECONDS=600,
            YASA_ENABLED=True,
            SCANNER_YASA_IMAGE="vulhunter/yasa-runner:test",
        ),
    )

    seen = {}

    async def _fake_run_scanner_container(spec):
        seen["spec"] = spec
        (output_dir / "report.sarif").write_text(
            """
            {
              "runs": [
                {
                  "results": [
                    {
                      "ruleId": "bootstrap.rule",
                      "message": {"text": "bootstrap finding"},
                      "level": "warning",
                      "locations": [
                        {
                          "physicalLocation": {
                            "artifactLocation": {"uri": "src/main.py"},
                            "region": {"startLine": 3, "endLine": 3}
                          }
                        }
                      ]
                    }
                  ]
                }
              ]
            }
            """,
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="bootstrap-container",
            exit_code=0,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(
        "app.services.agent.bootstrap.yasa.run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = YasaBootstrapScanner(language="python")
    result = await scanner.scan(str(tmp_path / "repo"))

    assert seen["spec"].image == "vulhunter/yasa-runner:test"
    assert result.total_findings == 1
    assert result.findings[0].title == "bootstrap.rule"
    assert result.findings[0].description == "bootstrap finding"
