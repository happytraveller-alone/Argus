from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


DEFAULT_BASE_DIR = Path("./uploads/agent_memory/projects")
DEFAULT_MAX_BYTES = 2_000_000

MEMORY_FILES: Dict[str, str] = {
    "shared": "shared.md",
    "orchestrator": "orchestrator.md",
    "recon": "recon.md",
    "analysis": "analysis.md",
    "verification": "verification.md",
    "skills": "skills.md",
}


SKILLS_TEMPLATE = """# Agent Markdown Memory 规范（skills.md）

本目录用于项目级“长期记忆”（无需 RAG/Embedding），供智能审计任务在多次运行间复用上下文。

## 写入要求（强约束）
- 只追加，不覆盖（除非轮转）
- 每次追加必须包含：
  - 时间戳（UTC ISO8601）
  - task_id
  - source（例如: opengrep_bootstrap / fallback_entrypoints / orchestrator / verification）
- 关键结构化信息必须放在 fenced JSON block 中，便于机器解析

## 推荐结构

## <timestamp> task_id=<id> source=<source>
### <title>
<human-readable summary>

```json
{
  "stats": {},
  "entry_points": [],
  "seed_findings": [],
  "top_findings": []
}
```

## 轮转策略
- 单文件超过 2MB 会自动轮转为 `*.YYYYMMDD_HHMMSS.archive.md`
- 新文件会写入指向归档文件的指针与最后摘要（excerpt）
"""


class MarkdownMemoryStore:
    """Project-level Markdown memory store (shared + per-agent).

    This store is intentionally simple and deterministic:
    - No embeddings
    - Fixed templates
    - Size-based rotation
    """

    def __init__(
        self,
        *,
        project_id: str,
        base_dir: Path | str = DEFAULT_BASE_DIR,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ):
        self.project_id = str(project_id)
        self.base_dir = Path(base_dir)
        self.project_dir = self.base_dir / self.project_id
        self.max_bytes = int(max(1, max_bytes))

    def _path(self, key: str) -> Path:
        name = MEMORY_FILES.get(key)
        if not name:
            raise KeyError(f"unknown memory key: {key}")
        return self.project_dir / name

    def _lock_path(self) -> Path:
        return self.project_dir / ".memory.lock"

    @contextmanager
    def _lock(self):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # A dedicated lock file avoids rename/write races on the actual markdown files.
        with open(lock_path, "a+", encoding="utf-8") as fp:
            try:
                import fcntl

                fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            yield

    def ensure(self) -> None:
        with self._lock():
            self.project_dir.mkdir(parents=True, exist_ok=True)
            for key, filename in MEMORY_FILES.items():
                file_path = self.project_dir / filename
                if file_path.exists():
                    continue
                try:
                    if key == "skills":
                        file_path.write_text(SKILLS_TEMPLATE, encoding="utf-8")
                    else:
                        file_path.write_text("", encoding="utf-8")
                except Exception as exc:
                    logger.warning("[MarkdownMemory] ensure failed for %s: %s", file_path, exc)

    def _rotate_if_needed(self, file_path: Path, incoming_bytes: int) -> None:
        try:
            current_size = file_path.stat().st_size if file_path.exists() else 0
        except Exception:
            current_size = 0

        if current_size + int(incoming_bytes) <= self.max_bytes:
            return

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_path = file_path.with_name(f"{file_path.stem}.{ts}.archive{file_path.suffix}")

        excerpt = ""
        if file_path.exists():
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                excerpt = text[-4000:]
            except Exception:
                excerpt = ""

        try:
            file_path.rename(archive_path)
        except Exception as exc:
            logger.warning("[MarkdownMemory] rotate rename failed (%s): %s", file_path, exc)
            return

        pointer = (
            f"# Rotated\n"
            f"- archived: {archive_path.name}\n"
            f"- rotated_at: {datetime.now(timezone.utc).isoformat()}\n\n"
        )
        if excerpt:
            pointer += "## Last Excerpt\n```text\n" + excerpt + "\n```\n\n"
        else:
            pointer += "## Last Excerpt\n(空)\n\n"

        try:
            file_path.write_text(pointer, encoding="utf-8")
        except Exception as exc:
            logger.warning("[MarkdownMemory] rotate pointer write failed (%s): %s", file_path, exc)

    def _read_tail(self, file_path: Path, max_chars: int) -> str:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
        if max_chars <= 0:
            return ""
        return text[-max_chars:]

    def _read_head_lines(self, file_path: Path, max_lines: int, max_chars: int) -> str:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
        lines = text.splitlines()
        head = "\n".join(lines[: max(1, int(max_lines))])
        if max_chars > 0 and len(head) > max_chars:
            head = head[:max_chars]
        return head

    def load_bundle(self, *, max_chars: int = 8000, skills_max_lines: int = 60) -> Dict[str, str]:
        """Load memory excerpts to inject into agent prompts."""
        self.ensure()
        bundle: Dict[str, str] = {}
        for key in ("shared", "orchestrator", "recon", "analysis", "verification"):
            bundle[key] = self._read_tail(self._path(key), int(max_chars))
        bundle["skills"] = self._read_head_lines(
            self._path("skills"),
            max_lines=int(skills_max_lines),
            max_chars=int(max_chars),
        )
        return bundle

    def append_entry(
        self,
        key: str,
        *,
        task_id: str,
        source: str,
        title: str,
        summary: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.ensure()
        file_path = self._path(key)

        ts = datetime.now(timezone.utc).isoformat()
        header = f"\n\n## {ts} task_id={task_id} source={source}\n### {str(title or '').strip() or 'entry'}\n"

        parts = [header]
        if summary:
            parts.append(str(summary).strip() + "\n")
        if payload is not None:
            try:
                payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:
                payload_text = json.dumps({"raw": str(payload)}, ensure_ascii=False, indent=2)
            parts.append("\n```json\n" + payload_text + "\n```\n")

        content = "".join(parts)
        incoming_bytes = len(content.encode("utf-8", errors="replace"))

        with self._lock():
            self._rotate_if_needed(file_path, incoming_bytes)
            try:
                with open(file_path, "a", encoding="utf-8") as fp:
                    fp.write(content)
            except Exception as exc:
                logger.warning("[MarkdownMemory] append failed (%s): %s", file_path, exc)

