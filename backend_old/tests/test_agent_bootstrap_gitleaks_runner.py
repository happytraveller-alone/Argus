import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.services.agent.bootstrap_gitleaks_runner import (
    _prepare_scan_project_dir_async,
    _run_bootstrap_gitleaks_scan,
)


def test_prepare_scan_project_dir_async_recreates_project_dir_from_source():
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        project_dir = root / "workspace" / "project"
        source.mkdir(parents=True)
        project_dir.mkdir(parents=True)
        (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (project_dir / "stale.txt").write_text("stale\n", encoding="utf-8")

        def _copy(src: str | Path, dst: str | Path) -> None:
            dst = Path(dst)
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "app.py").write_text(Path(src, "app.py").read_text(encoding="utf-8"), encoding="utf-8")

        asyncio.run(
            _prepare_scan_project_dir_async(
                str(source),
                project_dir,
                copy_project_tree_to_scan_dir_fn=_copy,
            )
        )

        assert not (project_dir / "stale.txt").exists()
        assert (project_dir / "app.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_run_bootstrap_gitleaks_scan_reads_report_and_cleans_workspace():
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        workspace = root / "workspace"
        project_dir = root / "project"
        output_dir = root / "output"
        logs_dir = root / "logs"
        meta_dir = root / "meta"
        for path in [workspace, project_dir, output_dir, logs_dir, meta_dir]:
            path.mkdir(parents=True, exist_ok=True)

        cleaned: list[tuple[str, str]] = []

        async def _fake_runner(spec):
            (output_dir / "report.json").write_text(
                '[{"RuleID":"generic-api-key","Description":"secret","File":"/scan/project/src/api.py","StartLine":3,"EndLine":4}]',
                encoding="utf-8",
            )
            return SimpleNamespace(exit_code=0, stderr_path=None, stdout_path=None, error=None)

        result = asyncio.run(
            _run_bootstrap_gitleaks_scan(
                project_root=str(root),
                ensure_scan_workspace_fn=lambda *_args: workspace,
                ensure_scan_project_dir_fn=lambda *_args: project_dir,
                ensure_scan_output_dir_fn=lambda *_args: output_dir,
                ensure_scan_logs_dir_fn=lambda *_args: logs_dir,
                ensure_scan_meta_dir_fn=lambda *_args: meta_dir,
                prepare_scan_project_dir_async_fn=lambda *_args, **_kwargs: asyncio.sleep(0),
                run_scanner_container_fn=_fake_runner,
                cleanup_scan_workspace_fn=lambda scan_type, task_id: cleaned.append((scan_type, task_id)),
                scanner_run_spec_cls=SimpleNamespace,
                scanner_gitleaks_image="example/gitleaks:latest",
            )
        )

        assert result == [
            {
                "RuleID": "generic-api-key",
                "Description": "secret",
                "File": "/scan/project/src/api.py",
                "StartLine": 3,
                "EndLine": 4,
            }
        ]
        assert cleaned and cleaned[0][0] == "gitleaks-bootstrap"


def test_run_bootstrap_gitleaks_scan_raises_with_runner_error_excerpt():
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        workspace = root / "workspace"
        project_dir = root / "project"
        output_dir = root / "output"
        logs_dir = root / "logs"
        meta_dir = root / "meta"
        for path in [workspace, project_dir, output_dir, logs_dir, meta_dir]:
            path.mkdir(parents=True, exist_ok=True)

        stderr_path = logs_dir / "stderr.txt"
        stderr_path.write_text("runner exploded", encoding="utf-8")

        async def _fake_runner(_spec):
            return SimpleNamespace(
                exit_code=1,
                stderr_path=str(stderr_path),
                stdout_path=None,
                error=None,
            )

        try:
            asyncio.run(
                _run_bootstrap_gitleaks_scan(
                    project_root=str(root),
                    ensure_scan_workspace_fn=lambda *_args: workspace,
                    ensure_scan_project_dir_fn=lambda *_args: project_dir,
                    ensure_scan_output_dir_fn=lambda *_args: output_dir,
                    ensure_scan_logs_dir_fn=lambda *_args: logs_dir,
                    ensure_scan_meta_dir_fn=lambda *_args: meta_dir,
                    prepare_scan_project_dir_async_fn=lambda *_args, **_kwargs: asyncio.sleep(0),
                    run_scanner_container_fn=_fake_runner,
                    cleanup_scan_workspace_fn=lambda *_args: None,
                    scanner_run_spec_cls=SimpleNamespace,
                    scanner_gitleaks_image="example/gitleaks:latest",
                )
            )
        except RuntimeError as exc:
            assert "gitleaks failed: runner exploded" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for non-zero runner exit")
