import os
import json
import subprocess
import tempfile
import re
import ast
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import logging
from app.services.zip_storage import get_project_zip_path
from app.services.upload.upload_manager import UploadManager
from app.services.llm.service import LLMService
from app.models.project_info import ProjectInfo
from .compression_factory import CompressionStrategyFactory

logger = logging.getLogger(__name__)


from pycloc import CLOC
from pycloc.exceptions import CLOCCommandError, CLOCDependencyError


async def get_cloc_stats(project_info: ProjectInfo) -> str:
    """获取项目代码统计（返回JSON字符串：总行数、总文件数、各语言文件数/行数/占比）"""
    zip_path = get_project_zip_path(project_info.project_id)
    if not os.path.exists(zip_path):
        logger.warning(f"项目ZIP文件不存在: {zip_path}")
        return "{}"

    with tempfile.TemporaryDirectory(prefix="deepaudit_", suffix="_cloc") as temp_dir:
        # 解压文件
        strategy = CompressionStrategyFactory.get_strategy(zip_path)
        extracted_files = await strategy.extract(zip_path, temp_dir)
        if not extracted_files:
            logger.error("解压失败：无文件被解压")
            return "{}"
        # 使用 pycloc 统计
        try:
            cloc = CLOC(
                json=True,
                quiet=True,
                exclude_dir="__pycache__,node_modules,venv",
            )
            output = cloc(temp_dir)
            if not output or not str(output).strip():
                logger.error("pycloc 返回空输出")
                return "{}"
            # 解析JSON结果
            cloc_result = json.loads(output)
            # 定义需要排除的非语言字段
            exclude_fields = {"header", "SUM"}
            # 存储各语言统计
            language_stats = {}

            # 遍历所有字段，筛选出语言相关的统计
            for key, value in cloc_result.items():
                if key not in exclude_fields and isinstance(value, dict):
                    code_lines = value.get("code", 0) or 0
                    files_count = (
                        value.get("nFiles")
                        or value.get("files")
                        or value.get("file_count")
                        or 0
                    )
                    language_stats[key] = {
                        "loc_number": int(code_lines),
                        "files_count": int(files_count),
                    }

            # 把提取后的语言行数信息加入结果（方便外部使用）
            total_lines = 0
            if isinstance(cloc_result.get("SUM"), dict):
                total_lines = cloc_result["SUM"].get("code", 0) or 0
            if total_lines <= 0:
                total_lines = sum(v.get("loc_number", 0) for v in language_stats.values())

            total_files = sum(v.get("files_count", 0) for v in language_stats.values())
            if total_files <= 0:
                # pycloc 某些场景可能不返回 nFiles，回退到解压文件列表按后缀统计得到总文件数
                total_files = len(
                    [
                        f
                        for f in extracted_files
                        if isinstance(f, str)
                        and not f.endswith("/")
                        and Path(f).suffix
                    ]
                )

            # 计算占比
            languages = {}
            for lang, stats in language_stats.items():
                lines = stats.get("loc_number", 0)
                files_count = stats.get("files_count", 0)
                proportion = (lines / total_lines) if total_lines > 0 else 0
                languages[lang] = {
                    "loc_number": lines,
                    "files_count": files_count,
                    "proportion": round(proportion, 4),
                }
            result_payload = {
                "total": total_lines,
                "total_files": total_files,
                "languages": languages,
            }
            return json.dumps(result_payload, ensure_ascii=False)
        except json.JSONDecodeError:
            logger.error("pycloc JSON解析失败")
            return "{}"
        except CLOCDependencyError as e:
            logger.error(f"pycloc 依赖错误（Perl不可用）: {e}")
            return "{}"
        except CLOCCommandError as e:
            logger.error(f"pycloc 命令执行失败: {e}")
            return "{}"
        except Exception as e:
            logger.error(f"pycloc 执行异常: {e}", exc_info=True)
            return "{}"


def build_static_project_description(language_info_json: str, project_name: Optional[str] = None) -> str:
    """基于静态统计结果生成项目描述（不依赖 LLM）。"""
    try:
        payload = json.loads(language_info_json) if language_info_json else {}
    except Exception:
        payload = {}

    languages = payload.get("languages") if isinstance(payload, dict) else {}
    if not isinstance(languages, dict) or len(languages) == 0:
        return "未检测到可统计的源码文件。"

    total_lines = int(payload.get("total") or 0)
    total_files = int(payload.get("total_files") or 0)

    sorted_langs = sorted(
        languages.items(),
        key=lambda item: (item[1] or {}).get("loc_number", 0),
        reverse=True,
    )
    top_langs = []
    for lang, stats in sorted_langs[:3]:
        loc = int((stats or {}).get("loc_number") or 0)
        files_count = int((stats or {}).get("files_count") or 0)
        top_langs.append(f"{lang}（{files_count} 文件 / {loc} 行）")

    prefix = f"项目“{project_name}”" if project_name else "该项目"
    top_desc = "、".join(top_langs) if top_langs else "无"
    return (
        f"{prefix}基于静态代码统计，共包含 {total_files} 个源码文件，"
        f"累计 {total_lines} 行代码。主要语言为：{top_desc}。"
    )


async def generate_project_description(project_info: ProjectInfo) -> Dict[str, Any]:
    """生成项目描述"""
    # MVP 实现：解压项目 -> 遍历文件 -> 提取每个文件的函数和注释 -> 调用LLM逐文件分析 -> 汇总
    zip_path = get_project_zip_path(project_info.project_id)
    if not os.path.exists(zip_path):
        logger.error(f"项目ZIP文件不存在: {zip_path}")
        return json.dumps({"error": "项目ZIP文件不存在"}, ensure_ascii=False)

    analyzer = ProjectDescriptionAnalyzer()
    try:
        with tempfile.TemporaryDirectory(prefix="deepaudit_desc_", suffix="_proj") as temp_dir:
            strategy = CompressionStrategyFactory.get_strategy(zip_path)
            extracted = await strategy.extract(zip_path, temp_dir)
            if not extracted:
                logger.error("解压失败：无文件被解压")
                return json.dumps({"error": "解压失败"}, ensure_ascii=False)

            # 分析目录并生成描述
            return await analyzer.analyze_project(temp_dir)
    except Exception as e:
        logger.error(f"生成项目描述失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


class ProjectDescriptionAnalyzer:
    """项目统计和分析器"""

    def __init__(self, user_config: Optional[dict] = None):
        self.llm_service = LLMService(user_config=user_config)

    # 需要排除的目录
    EXCLUDED_DIRS = {
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "dist",
        "build",
        ".egg-info",
        ".pytest_cache",
        ".mypy_cache",
        ".coverage",
        "htmlcov",
        "target",
        "out",
        ".gradle",
        ".idea",
        ".vscode",
        ".env",
        ".DS_Store",
        "coverage",
        ".next",
        ".nuxt",
        ".cache",
        ".turbo",
        "pnpm-store",
        "test",
        "tests",
    }

    # 需要排除的文件扩展名
    EXCLUDED_EXTS = {
        ".pyc",
        ".o",
        ".a",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".class",
        ".jar",
        ".war",
        ".zip",
        ".tar",
        ".gz",
        ".7z",
        ".rar",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".lock",
        ".swp",
        ".swo",
        "~",
    }

    @staticmethod
    def _should_skip_dir(dir_name: str) -> bool:
        """检查目录是否应该被跳过"""
        return dir_name.lower() in ProjectDescriptionAnalyzer.EXCLUDED_DIRS or dir_name.startswith(
            "."
        )

    @staticmethod
    def _should_skip_file(file_path: str) -> bool:
        """检查文件是否应该被跳过"""
        name = os.path.basename(file_path).lower()
        ext = Path(file_path).suffix.lower()

        # 检查扩展名
        if ext in ProjectDescriptionAnalyzer.EXCLUDED_EXTS:
            return True

        # 跳过特殊文件
        if name.startswith(".") or name in {"thumbs.db", "desktop.ini"}:
            return True

        return False

    async def analyze_project(self, project_dir: str, max_files: int = 30) -> Dict[str, Any]:
        """遍历项目目录，提取函数及注释，调用LLM进行逐文件分析并汇总结果（MVP）。"""
        summaries: Dict[str, Any] = {}

        # 先收集待处理文件（根据 max_files 限制），避免在并发阶段进行文件系统遍历
        file_entries: List[Tuple[str, str]] = []
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]
            for fname in files:
                if len(file_entries) >= max_files:
                    break
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, project_dir)
                if self._should_skip_file(fpath):
                    continue
                file_entries.append((fpath, rel_path))
            if len(file_entries) >= max_files:
                break

        # 并发处理文件，限制并发数以避免同时打爆 LLM 或本地 IO
        concurrency = min(6, max(1, (os.cpu_count() / 4 or 4)))
        semaphore = asyncio.Semaphore(concurrency)

        async def worker(fpath: str, rel_path: str):
            async with semaphore:
                return await self._process_file(fpath, rel_path)

        tasks = [asyncio.create_task(worker(f, r)) for f, r in file_entries]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []

        files_processed = 0
        for idx, res in enumerate(results):
            fpath, rel_path = file_entries[idx]
            if isinstance(res, Exception):
                logger.warning(f"处理文件失败 {fpath}: {res}")
                summaries[rel_path] = {"error": str(res)}
            else:
                summaries[rel_path] = res
                files_processed += 1

        # 汇总：用LLM对文件分析结果生成项目级描述
        try:
            summary_prompt = self._build_project_summary_prompt(summaries)
            project_summary_resp = await self.llm_service.chat_completion(
                [{"role": "user", "content": summary_prompt}], temperature=0.1, max_tokens=1000
            )
            logger.warning(f"项目汇总LLM响应: {project_summary_resp}")
            project_description = (
                project_summary_resp.get("content")
                if isinstance(project_summary_resp, dict)
                else ""
            )
        except Exception as e:
            logger.warning(f"生成项目汇总描述时LLM失败: {e}")
            project_description = ""
        return {
            "project_description": project_description,
            "file_summaries": summaries,
        }

    def _get_source_segment(self, text: str, node: ast.AST, context_lines: int = 2) -> str:
        try:
            lines = text.split("\n")
            lineno = getattr(node, "lineno", None)
            end_lineno = getattr(node, "end_lineno", lineno)
            if lineno is None:
                return ""
            start = max(0, lineno - 1 - context_lines)
            end = min(len(lines), (end_lineno or lineno) + context_lines)
            return "\n".join(lines[start:end])
        except Exception:
            return ""

    def _extract_functions_by_regex(self, text: str, language: str) -> List[Dict[str, Any]]:
        """
        使用正则提取函数和类定义，并保留上下各两行作为 snippet
        """
        patterns = {
            # Python：函数 + 类
            "py": [
                ("function", r"^\s*def\s+(\w+)\s*\("),
                ("async_function", r"^\s*async\s+def\s+(\w+)\s*\("),
                ("class", r"^\s*class\s+(\w+)\s*(?:\(|:)"),
            ],
            "python": [
                ("function", r"^\s*def\s+(\w+)\s*\("),
                ("async_function", r"^\s*async\s+def\s+(\w+)\s*\("),
                ("class", r"^\s*class\s+(\w+)\s*(?:\(|:)"),
            ],
            # JavaScript / TypeScript
            "js": [
                ("function", r"function\s+(\w+)\s*\("),
                ("arrow_function", r"const\s+(\w+)\s*=\s*\([^)]*\)\s*=>"),
                ("class", r"class\s+(\w+)"),
            ],
            "ts": [
                ("function", r"function\s+(\w+)\s*\("),
                ("arrow_function", r"const\s+(\w+)\s*=\s*\([^)]*\)\s*=>"),
                ("class", r"class\s+(\w+)"),
            ],
            # Java
            "java": [
                ("class", r"\bclass\s+(\w+)"),
                ("method", r"\b(?:public|protected|private|static|\s)+[\w<>,\[\]\s]+\s+(\w+)\s*\("),
            ],
            # Go
            "go": [
                ("function", r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\("),
                ("struct", r"type\s+(\w+)\s+struct"),
            ],
            # PHP
            "php": [
                ("function", r"function\s+(\w+)\s*\("),
                ("class", r"class\s+(\w+)"),
            ],
        }

        res: List[Dict[str, Any]] = []
        lines = text.splitlines()
        pats = patterns.get(language, [])

        for kind, pat in pats:
            try:
                regex = re.compile(pat, re.MULTILINE)
                for m in regex.finditer(text):
                    name = m.group(1)
                    lineno = text[: m.start()].count("\n") + 1
                    snippet = self._get_line_context(lines, lineno, context_lines=2)

                    res.append(
                        {
                            "type": kind,
                            "name": name,
                            "lineno": lineno,
                            "docstring": "",
                            "snippet": snippet,
                        }
                    )
            except Exception:
                continue

        return res

    def _get_line_context(self, lines: List[str], lineno: int, context_lines: int = 2) -> str:
        """
        根据行号提取上下文（上下各 context_lines 行）
        lineno 从 1 开始
        """
        try:
            idx = lineno - 1
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            return "\n".join(lines[start:end])
        except Exception:
            return ""

    def _get_regex_context(self, text: str, pos: int, context_lines: int = 2) -> str:
        lines = text.split("\n")
        line_no = text[:pos].count("\n")
        start = max(0, line_no - context_lines)
        end = min(len(lines), line_no + context_lines + 3)
        return "\n".join(lines[start:end])

    def _read_file_text(self, fpath: str) -> Optional[str]:
        try:
            with open(fpath, "rb") as fh:
                raw = fh.read()
            try:
                return raw.decode("utf-8")
            except Exception:
                try:
                    return raw.decode("latin1")
                except Exception:
                    return None
        except Exception:
            return None

    async def _process_file(self, fpath: str, rel_path: str) -> Dict[str, Any]:
        """并发处理单个文件：读取、提取函数、调用LLM并返回摘要字典"""
        try:
            text = await asyncio.to_thread(self._read_file_text, fpath)
            if not text:
                return {"error": "非文本或读取失败"}

            language = Path(fpath).suffix.lower().lstrip(".") or "text"

            # 提取函数/方法及注释（所有语言走正则提取）
            functions = self._extract_functions_by_regex(text, language)

            # 构建 prompt 并调用 LLM
            prompt = self._build_file_prompt(rel_path, language, functions, text)
            try:
                resp = await self.llm_service.chat_completion(
                    [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=800
                )
                analysis = resp.get("content") if isinstance(resp, dict) else ""
                if not analysis:
                    analysis = ""
            except Exception as e:
                logger.warning(f"LLM 分析文件失败 {rel_path}: {e}")
                analysis = f"LLM 分析失败: {str(e)}"
            logger.warning(f"已处理文件: {rel_path} -> {analysis}")
            return {
                "language": language,
                "functions": functions,
                "analysis": analysis,
            }
        except Exception as e:
            logger.warning(f"处理文件失败 {fpath}: {e}")
            return {"error": str(e)}

    def _build_file_prompt(
        self, rel_path: str, language: str, functions: List[Dict[str, Any]], full_text: str
    ) -> str:
        # MVP prompt：简洁说明需要输出语言为中文，描述文件的主要作用、关键函数和简要改进建议
        funcs_summary = []
        for f in functions[:10]:
            funcs_summary.append(
                f"- {f.get('name')} (line: {f.get('lineno')}) doc: { (f.get('docstring') or '').strip() }"
            )

        prompt = f"请用简体中文简短分析文件: {rel_path}\\n语言: {language}\\n关键函数/方法:\\n{chr(10).join(funcs_summary)}\\n\\n请回答: 这个文件的主要作用。不要输出其他多余内容。"
        return prompt

    def _build_project_summary_prompt(self, summaries: Dict[str, Any]) -> str:
        # 将每个文件的简要结果拼接并请求LLM生成项目级描述
        parts = [
            f"文件: {p}\\n语言: {s.get('language')}\\n分析摘要: { (s.get('analysis') or '')[:1000]}"
            for p, s in summaries.items()
        ]
        body = "\\n\\n".join(parts[:30])
        prompt = f"请基于以下各文件的分析结果，使用简体中文生成一段简要的项目描述，不超过500字。输入：\\n{body}\\n\\n请只返回最终的项目描述文本。"
        return prompt
