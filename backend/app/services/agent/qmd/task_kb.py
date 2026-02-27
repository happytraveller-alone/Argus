from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


logger = logging.getLogger(__name__)


def _safe_name(value: Any, *, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_")
    return normalized or fallback


def _split_qmd_command(raw_command: Any) -> list[str]:
    fallback = "npx -y @tobilu/qmd"
    text = str(raw_command or "").strip() or fallback
    try:
        parts = shlex.split(text)
    except Exception:
        parts = []
    if not parts:
        parts = shlex.split(fallback)
    return [str(part).strip() for part in parts if str(part).strip()]


class QmdTaskKnowledgeBase:
    """Task-scoped QMD CLI wrapper used by Agent local tools."""

    def __init__(
        self,
        *,
        project_root: str,
        task_id: str,
        command: str,
        task_root_rel: str = ".deepaudit/qmd",
        collection_prefix: str = "task",
        doc_glob: str = "**/*.{md,txt,json,yml,yaml}",
        auto_embed: bool = False,
        query_cache: bool = True,
        timeout_seconds: int = 120,
    ) -> None:
        self.project_root = Path(str(project_root or "").strip() or ".").resolve()
        self.task_id = str(task_id or "").strip() or "default"
        self.task_root_rel = str(task_root_rel or ".deepaudit/qmd").strip() or ".deepaudit/qmd"
        self.task_root = (self.project_root / self.task_root_rel).resolve()
        self.collection_prefix = _safe_name(collection_prefix, fallback="task")
        self.collection_name = f"{self.collection_prefix}_{_safe_name(self.task_id, fallback='default')}"
        self.index_name = self.collection_name
        self.doc_glob = str(doc_glob or "**/*.{md,txt,json,yml,yaml}").strip() or "**/*.{md,txt,json,yml,yaml}"
        self.auto_embed = bool(auto_embed)
        self.query_cache_enabled = bool(query_cache)
        self.timeout_seconds = max(5, int(timeout_seconds or 120))
        self.command_base = _split_qmd_command(command)
        self.manifest_path = self.task_root / ".manifest.json"
        self._manifest: Dict[str, str] = {}
        self._query_cache: Dict[str, Dict[str, Any]] = {}
        self._collection_ready = False
        self._dirty = False

    @property
    def agents_dir(self) -> Path:
        return self.task_root / "agents"

    @property
    def artifacts_dir(self) -> Path:
        return self.task_root / "artifacts"

    def ensure_ready(self) -> Dict[str, Any]:
        self.task_root.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._load_manifest()
        if self._collection_ready:
            return {"success": True, "collection": self.collection_name}
        add_result = self._run_cli(
            [
                "collection",
                "add",
                str(self.task_root),
                "--name",
                self.collection_name,
                "--mask",
                self.doc_glob,
            ],
            expect_json=False,
            ensure_collection=False,
        )
        if add_result.get("success"):
            self._collection_ready = True
            return {"success": True, "collection": self.collection_name}

        stderr = str(add_result.get("stderr") or "").lower()
        stdout = str(add_result.get("stdout") or "").lower()
        if "already exists" in stderr or "already exists" in stdout:
            self._collection_ready = True
            return {"success": True, "collection": self.collection_name, "existing": True}

        error_text = str(add_result.get("error") or "").strip() or "collection_add_failed"
        logger.warning("[QMD TaskKB] ensure_ready failed: %s", error_text)
        return {"success": False, "error": error_text, "collection": self.collection_name}

    def upsert_text(self, relative_path: str, content: str) -> bool:
        normalized = self._normalize_relative_path(relative_path)
        target = (self.task_root / normalized).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        text = str(content or "")
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        if self._manifest.get(normalized) == digest and target.exists():
            return False
        target.write_text(text, encoding="utf-8")
        self._manifest[normalized] = digest
        self._dirty = True
        self._persist_manifest()
        if self.query_cache_enabled:
            self._query_cache.clear()
        return True

    def upsert_json(self, relative_path: str, payload: Any) -> bool:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return self.upsert_text(relative_path, text + "\n")

    def update_index(self, *, force: bool = False, embed: Optional[bool] = None) -> Dict[str, Any]:
        ensure_result = self.ensure_ready()
        if not ensure_result.get("success"):
            return {
                "success": False,
                "error": str(ensure_result.get("error") or "qmd_not_ready"),
                "updated": False,
            }
        should_update = bool(force or self._dirty)
        if not should_update:
            return {"success": True, "updated": False}
        update_result = self._run_cli(["update"], expect_json=False)
        if not update_result.get("success"):
            return {
                "success": False,
                "updated": False,
                "error": str(update_result.get("error") or "qmd_update_failed"),
                "stdout": update_result.get("stdout"),
                "stderr": update_result.get("stderr"),
            }
        should_embed = self.auto_embed if embed is None else bool(embed)
        if should_embed:
            embed_result = self._run_cli(["embed"], expect_json=False)
            if not embed_result.get("success"):
                return {
                    "success": False,
                    "updated": True,
                    "embed_success": False,
                    "error": str(embed_result.get("error") or "qmd_embed_failed"),
                    "stdout": embed_result.get("stdout"),
                    "stderr": embed_result.get("stderr"),
                }
        self._dirty = False
        return {"success": True, "updated": True}

    def query(
        self,
        *,
        query_text: str,
        limit: int = 5,
        collection: Optional[str] = None,
        full: bool = False,
    ) -> Dict[str, Any]:
        normalized_query = str(query_text or "").strip()
        if not normalized_query:
            return {"success": False, "error": "query_required"}
        collection_name = str(collection or self.collection_name).strip() or self.collection_name
        cache_key = json.dumps(
            {
                "query": normalized_query,
                "limit": int(max(1, limit)),
                "collection": collection_name,
                "full": bool(full),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if self.query_cache_enabled and cache_key in self._query_cache:
            cached = dict(self._query_cache[cache_key])
            cached.setdefault("metadata", {})
            cached["metadata"]["cache_hit"] = True
            return cached

        result = self._run_search_command(
            command_name="query",
            query_text=normalized_query,
            limit=limit,
            collection=collection_name,
            full=full,
            allow_fallback=True,
        )
        if result.get("success") and self.query_cache_enabled:
            self._query_cache[cache_key] = dict(result)
        return result

    def get(self, *, doc_id: str, lines: Optional[int] = None, from_line: Optional[int] = None) -> Dict[str, Any]:
        normalized_doc_id = str(doc_id or "").strip()
        if not normalized_doc_id:
            return {"success": False, "error": "doc_id_required"}
        args = ["get", normalized_doc_id]
        if lines is not None:
            args.extend(["-l", str(max(1, int(lines)))])
        if from_line is not None:
            args.extend(["--from", str(max(1, int(from_line)))])
        return self._run_cli(args, expect_json=False)

    def multi_get(
        self,
        *,
        pattern: str,
        lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_pattern = str(pattern or "").strip()
        if not normalized_pattern:
            return {"success": False, "error": "pattern_required"}
        args = ["multi-get", normalized_pattern, "--json"]
        if lines is not None:
            args.extend(["-l", str(max(1, int(lines)))])
        if max_bytes is not None:
            args.extend(["--max-bytes", str(max(1, int(max_bytes)))])
        return self._run_cli(args, expect_json=True)

    def status(self) -> Dict[str, Any]:
        return self._run_cli(["status"], expect_json=False)

    def _run_search_command(
        self,
        *,
        command_name: str,
        query_text: str,
        limit: int,
        collection: str,
        full: bool,
        allow_fallback: bool,
    ) -> Dict[str, Any]:
        args = [
            command_name,
            query_text,
            "-n",
            str(max(1, int(limit))),
            "--json",
            "--collection",
            collection,
        ]
        if full:
            args.append("--full")
        result = self._run_cli(args, expect_json=True)
        if result.get("success"):
            return result
        if not allow_fallback:
            return result
        fallback = self._run_search_command(
            command_name="search",
            query_text=query_text,
            limit=limit,
            collection=collection,
            full=full,
            allow_fallback=False,
        )
        if fallback.get("success"):
            fallback.setdefault("metadata", {})
            fallback["metadata"]["fallback"] = "search"
            fallback["metadata"]["fallback_reason"] = str(result.get("error") or "query_failed")
        return fallback

    def _run_cli(
        self,
        args: Iterable[str],
        *,
        expect_json: bool,
        ensure_collection: bool = True,
    ) -> Dict[str, Any]:
        if ensure_collection:
            ensure = self.ensure_ready()
            if not ensure.get("success"):
                return {
                    "success": False,
                    "error": str(ensure.get("error") or "qmd_not_ready"),
                    "stdout": "",
                    "stderr": "",
                }

        full_command = [
            *self.command_base,
            "--index",
            self.index_name,
            *[str(item) for item in args],
        ]
        try:
            completed = subprocess.run(
                full_command,
                cwd=str(self.task_root),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                env=os.environ.copy(),
            )
        except FileNotFoundError as exc:
            return {
                "success": False,
                "error": f"command_not_found:{exc}",
                "stdout": "",
                "stderr": "",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "error": f"timeout:{self.timeout_seconds}s",
                "stdout": str(exc.stdout or ""),
                "stderr": str(exc.stderr or ""),
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "success": False,
                "error": f"execution_error:{exc}",
                "stdout": "",
                "stderr": "",
            }

        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        if int(completed.returncode or 0) != 0:
            error_text = (stderr.strip() or stdout.strip() or f"exit_{completed.returncode}").strip()
            return {
                "success": False,
                "error": error_text,
                "exit_code": int(completed.returncode),
                "stdout": stdout,
                "stderr": stderr,
            }

        payload: Dict[str, Any] = {
            "success": True,
            "exit_code": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
        }
        if expect_json:
            parsed = self._parse_json_output(stdout)
            payload["data"] = parsed
        else:
            payload["data"] = stdout.strip()
        return payload

    @staticmethod
    def build_multiline_query(searches: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in searches:
            if not isinstance(item, dict):
                continue
            query_type = str(item.get("type") or "").strip().lower() or "vec"
            query_text = str(item.get("query") or "").strip()
            if not query_text:
                continue
            lines.append(f"{query_type}: {query_text}")
        return "\n".join(lines)

    def _load_manifest(self) -> None:
        if not self.manifest_path.exists():
            self._manifest = {}
            return
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self._manifest = {
                    str(key): str(value)
                    for key, value in payload.items()
                    if str(key).strip() and str(value).strip()
                }
                return
        except Exception as exc:
            logger.warning("[QMD TaskKB] load manifest failed (%s): %s", self.manifest_path, exc)
        self._manifest = {}

    def _persist_manifest(self) -> None:
        try:
            self.manifest_path.write_text(
                json.dumps(self._manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[QMD TaskKB] persist manifest failed (%s): %s", self.manifest_path, exc)

    @staticmethod
    def _parse_json_output(stdout: str) -> Any:
        text = str(stdout or "").strip()
        if not text:
            return []
        try:
            return json.loads(text)
        except Exception:
            return {"raw": text}

    def _normalize_relative_path(self, relative_path: str) -> str:
        raw = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        normalized = raw or "artifacts/unknown.txt"
        target = (self.task_root / normalized).resolve()
        if target == self.task_root:
            raise ValueError("invalid_relative_path")
        if self.task_root not in target.parents:
            raise ValueError("path_outside_task_root")
        return str(target.relative_to(self.task_root)).replace("\\", "/")
