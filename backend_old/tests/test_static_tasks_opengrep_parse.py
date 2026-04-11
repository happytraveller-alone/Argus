"""
Manual/integration smoke test for opengrep output parsing.

This originally executed at import-time and required a pre-existing ZIP in uploads,
which makes the default pytest suite fail during collection.
"""

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from app.api.v1.endpoints.static_tasks import _parse_opengrep_output
from app.core.config import settings
from app.models.opengrep import OpengrepFinding


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_opengrep_parse_smoke():
    project_id = os.environ.get("VulHunter_OPENGREP_PARSE_PROJECT_ID")
    if not project_id:
        pytest.skip("Set VulHunter_OPENGREP_PARSE_PROJECT_ID to run this integration test.")

    zip_dir = Path(getattr(settings, "ZIP_STORAGE_PATH", "./uploads/zip_files"))
    zip_path = zip_dir / f"{project_id}.zip"
    if not zip_path.exists():
        matches = list(zip_dir.glob(f"{project_id}_*.zip"))
        zip_path = matches[0] if matches else None

    if not zip_path or not zip_path.exists():
        pytest.skip(f"Project ZIP not found for {project_id}; skipping integration test.")

    temp_dir = tempfile.mkdtemp(prefix=f"VulHunter_{project_id}_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # If the archive expands to a single folder, treat it as the repo root.
        items = [p for p in os.listdir(temp_dir) if not p.startswith(".") and not p.startswith("__")]
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            project_root = os.path.join(temp_dir, items[0])
        else:
            project_root = temp_dir

        cmd = ["opengrep", "--config", "p/security-audit", "--json", project_root]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode not in (0, 1) and not result.stdout:
            raise RuntimeError(
                f"opengrep failed: returncode={result.returncode}, stderr={result.stderr[:200]}"
            )

        parsed_results = _parse_opengrep_output(result.stdout)
        findings = [
            OpengrepFinding(
                scan_task_id="test-task",
                rule=finding,
                description=finding.get("extra", {}).get("message"),
                file_path=finding.get("path", ""),
                start_line=finding.get("start", {}).get("line"),
                code_snippet=finding.get("extra", {}).get("lines"),
                severity=finding.get("extra", {}).get("severity", "INFO"),
                status="open",
            )
            for finding in parsed_results
        ]

        assert isinstance(findings, list)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
