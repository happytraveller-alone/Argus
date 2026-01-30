import asyncio
import os
import shutil
import subprocess
import tempfile
import zipfile
import json
from pathlib import Path

from app.api.v1.endpoints.static_tasks import _parse_opengrep_output
from app.core.config import settings
from app.models.opengrep import OpengrepFinding
from app.models.project_info import ProjectInfo


async def test_opengrep_parse():
    uuid = "c4a41891-046d-48a7-a46b-7f68fc8a6fc0"
    project_info = ProjectInfo()
    project_info.project_id = uuid

    # 获取zip文件解压到临时目录
    zip_dir = Path(getattr(settings, "ZIP_STORAGE_PATH", "./uploads/zip_files"))
    zip_path = zip_dir / f"{uuid}.zip"
    if not zip_path.exists():
        matches = list(zip_dir.glob(f"{uuid}_*.zip"))
        zip_path = matches[0] if matches else None

    if not zip_path or not zip_path.exists():
        raise FileNotFoundError(f"未找到zip文件: {uuid}")

    temp_dir = tempfile.mkdtemp(prefix=f"deepaudit_{uuid}_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # 如果解压后只有一个子目录，则使用该子目录作为项目根目录
        items = [
            p for p in os.listdir(temp_dir) if not p.startswith(".") and not p.startswith("__")
        ]
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            project_root = os.path.join(temp_dir, items[0])
        else:
            project_root = temp_dir

        # 使用 opengrep --config p/security-audit --json 解析
        cmd = [
            "opengrep",
            "--config",
            "p/security-audit",
            "--json",
            project_root,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode not in (0, 1) and not result.stdout:
            raise RuntimeError(
                f"opengrep 执行失败: returncode={result.returncode}, stderr={result.stderr[:200]}"
            )
        # 获取opengrep的输出结果，并解析输出到OpengrepFinding模型列表
        parsed_results = _parse_opengrep_output(result.stdout)
        findings = []
        for finding in parsed_results:
            opengrep_finding = OpengrepFinding(
                scan_task_id="test-task",
                rule=finding,
                description=finding.get("extra", {}).get("message"),
                file_path=finding.get("path", ""),
                start_line=finding.get("start", {}).get("line"),
                code_snippet=finding.get("extra", {}).get("lines"),
                severity=finding.get("extra", {}).get("severity", "INFO"),
                status="open",
            )
            findings.append(opengrep_finding)

        print(f"Parsed findings: {len(findings)}")
        for item in findings[:5]:
            print(
                f"{item.severity} | {item.file_path}:{item.start_line} | {item.description}"
            )
        assert isinstance(findings, list)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


result = asyncio.run(test_opengrep_parse())
