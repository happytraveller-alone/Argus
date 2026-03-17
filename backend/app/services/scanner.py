"""
ZIP 项目扫描服务与共享扫描工具函数。
"""

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.audit import AuditIssue, AuditTask
from app.models.project import Project
from app.services.llm.service import LLMConfigError, LLMService
from app.services.zip_storage import load_project_zip
from app.services.project_metrics import project_metrics_refresher


def get_analysis_config(user_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    获取分析配置参数（优先使用用户配置，然后使用系统配置）。
    """
    other_config = (user_config or {}).get("otherConfig", {})
    return {
        "max_analyze_files": other_config.get("maxAnalyzeFiles") or settings.MAX_ANALYZE_FILES,
        "llm_concurrency": other_config.get("llmConcurrency") or settings.LLM_CONCURRENCY,
        "llm_gap_ms": other_config.get("llmGapMs") or settings.LLM_GAP_MS,
    }


TEXT_EXTENSIONS = [
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".cc",
    ".hh",
    ".cs",
    ".php",
    ".rb",
    ".kt",
    ".swift",
    ".sql",
    ".sh",
    ".json",
    ".yml",
    ".yaml",
]

EXCLUDE_PATTERNS = [
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    "coverage/",
    ".nyc_output/",
    ".vscode/",
    ".idea/",
    ".vs/",
    "target/",
    "out/",
    "__MACOSX/",
    ".DS_Store",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".min.js",
    ".min.css",
    ".map",
]


def is_text_file(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in TEXT_EXTENSIONS)


def should_exclude(path: str, exclude_patterns: List[str] = None) -> bool:
    normalized_path = (path or "").replace("\\", "/")
    path_segments = [seg.lower() for seg in PurePosixPath(normalized_path).parts]
    if any("test" in segment for segment in path_segments[:-1]):
        return True

    all_patterns = EXCLUDE_PATTERNS + (exclude_patterns or [])
    return any(pattern in normalized_path for pattern in all_patterns)


def get_language_from_path(path: str) -> str:
    ext = path.split(".")[-1].lower() if "." in path else ""
    language_map = {
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "py": "python",
        "java": "java",
        "go": "go",
        "rs": "rust",
        "cpp": "cpp",
        "c": "cpp",
        "cc": "cpp",
        "h": "cpp",
        "hh": "cpp",
        "cs": "csharp",
        "php": "php",
        "rb": "ruby",
        "kt": "kotlin",
        "swift": "swift",
    }
    return language_map.get(ext, "text")


class TaskControlManager:
    """任务控制管理器 - 用于取消运行中的任务"""

    def __init__(self):
        self._cancelled_tasks: set = set()

    def cancel_task(self, task_id: str):
        self._cancelled_tasks.add(task_id)
        print(f"🛑 任务 {task_id} 已标记为取消")

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled_tasks

    def cleanup_task(self, task_id: str):
        self._cancelled_tasks.discard(task_id)


task_control = TaskControlManager()


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


async def scan_repo_task(task_id: str, db_session_factory, user_config: dict = None):
    """
    兼容旧调用名的 ZIP 项目扫描任务。
    """
    async with db_session_factory() as db:
        task = await db.get(AuditTask, task_id)
        if not task:
            return

        extract_dir = Path(f"/tmp/{task_id}")

        try:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            await db.commit()

            llm_service = LLMService(user_config=user_config or {})
            try:
                _ = llm_service.config
            except LLMConfigError as cfg_exc:
                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
                print(f"ZIP任务 {task_id} 失败: LLM配置错误 - {cfg_exc}")
                task_control.cleanup_task(task_id)
                return

            project = await db.get(Project, task.project_id)
            if not project:
                raise RuntimeError("项目不存在")
            if getattr(project, "source_type", None) != "zip":
                raise RuntimeError("仅支持 ZIP 项目")

            zip_path = await load_project_zip(project.id)
            if not zip_path or not os.path.exists(zip_path):
                raise RuntimeError("项目 ZIP 文件不存在")

            extract_dir.mkdir(parents=True, exist_ok=True)
            from zipfile import ZipFile

            with ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            scan_config = dict((user_config or {}).get("scan_config", {}) or {})
            custom_exclude_patterns = scan_config.get("exclude_patterns", []) or []

            files_to_scan: list[dict[str, str]] = []
            for root, dirs, files in os.walk(extract_dir):
                dirs[:] = [
                    directory
                    for directory in dirs
                    if directory not in ["node_modules", "__pycache__", ".git", "dist", "build", "vendor"]
                ]
                for file_name in files:
                    full_path = Path(root) / file_name
                    rel_path = _normalize_path(str(full_path.relative_to(extract_dir)))
                    if not is_text_file(rel_path) or should_exclude(rel_path, custom_exclude_patterns):
                        continue
                    try:
                        content = full_path.read_text(errors="ignore")
                    except Exception:
                        continue
                    if len(content) > settings.MAX_FILE_SIZE_BYTES:
                        continue
                    files_to_scan.append({"path": rel_path, "content": content})

            analysis_config = get_analysis_config(user_config)
            max_analyze_files = analysis_config["max_analyze_files"]
            llm_gap_ms = analysis_config["llm_gap_ms"]

            target_files = scan_config.get("file_paths", []) or []
            if target_files:
                normalized_targets = {_normalize_path(path) for path in target_files}
                files_to_scan = [f for f in files_to_scan if f["path"] in normalized_targets]
            elif max_analyze_files > 0:
                files_to_scan = files_to_scan[:max_analyze_files]

            task.total_files = len(files_to_scan)
            await db.commit()

            total_issues = 0
            total_lines = 0
            quality_scores: list[float] = []
            scanned_files = 0

            for file_info in files_to_scan:
                if task_control.is_cancelled(task_id):
                    task.status = "cancelled"
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    task_control.cleanup_task(task_id)
                    return

                try:
                    content = file_info["content"]
                    total_lines += content.count("\n") + 1
                    language = get_language_from_path(file_info["path"])
                    rule_set_id = scan_config.get("rule_set_id")
                    prompt_template_id = scan_config.get("prompt_template_id")

                    if rule_set_id or prompt_template_id:
                        result = await llm_service.analyze_code_with_rules(
                            content,
                            language,
                            rule_set_id=rule_set_id,
                            prompt_template_id=prompt_template_id,
                            db_session=db,
                        )
                    else:
                        result = await llm_service.analyze_code(content, language)

                    for issue_data in result.get("issues", []):
                        db.add(
                            AuditIssue(
                                task_id=task.id,
                                file_path=file_info["path"],
                                line_number=issue_data.get("line", 1),
                                column_number=issue_data.get("column"),
                                issue_type=issue_data.get("type", "maintainability"),
                                severity=issue_data.get("severity", "low"),
                                title=issue_data.get("title", "Issue"),
                                message=issue_data.get("title", "Issue"),
                                description=issue_data.get("description"),
                                suggestion=issue_data.get("suggestion"),
                                code_snippet=issue_data.get("code_snippet"),
                                ai_explanation=json.dumps(issue_data.get("xai"))
                                if issue_data.get("xai")
                                else None,
                                status="open",
                            )
                        )
                        total_issues += 1

                    if "quality_score" in result:
                        quality_scores.append(result["quality_score"])

                    scanned_files += 1
                    task.scanned_files = scanned_files
                    task.total_lines = total_lines
                    task.issues_count = total_issues
                    await db.commit()

                    await asyncio.sleep(llm_gap_ms / 1000)
                except Exception as file_error:
                    print(f"ZIP任务分析文件失败 ({file_info['path']}): {file_error}")
                    await asyncio.sleep(llm_gap_ms / 1000)

            avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 100.0
            task.status = "completed" if scanned_files > 0 or not files_to_scan else "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.scanned_files = scanned_files
            task.total_lines = total_lines
            task.issues_count = total_issues if scanned_files > 0 else 0
            task.quality_score = avg_quality_score if scanned_files > 0 else 0
            await db.commit()
            task_control.cleanup_task(task_id)
        except Exception as exc:
            print(f"ZIP扫描失败: {exc}")
            task.status = "failed"
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()
            task_control.cleanup_task(task_id)
        finally:
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            if task and task.project_id:
                project_metrics_refresher.enqueue(task.project_id)
