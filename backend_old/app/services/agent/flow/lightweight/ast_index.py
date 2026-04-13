from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.services.parser import TreeSitterParser

from .definition_provider import get_default_definition_provider


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
}

RESERVED_CALL_NAMES = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "catch",
    "new",
    "delete",
}


@dataclass
class FunctionSymbol:
    id: str
    name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    callees: Set[str] = field(default_factory=set)
    control_conditions: List[str] = field(default_factory=list)
    is_entry: bool = False


class ASTCallIndex:
    def __init__(
        self,
        project_root: str,
        target_files: Optional[List[str]] = None,
        max_files: int = 2000,
        definition_provider: Any = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.target_files = {self._normalize_path(p) for p in (target_files or []) if p}
        self.max_files = max_files
        self.parser = TreeSitterParser()
        self.definition_provider = definition_provider or get_default_definition_provider()

        self.symbols_by_id: Dict[str, FunctionSymbol] = {}
        self.symbols_by_name: Dict[str, List[FunctionSymbol]] = {}
        self._built = False

    def _normalize_path(self, raw_path: str) -> str:
        p = str(raw_path).replace("\\", "/").strip()
        if p.startswith("./"):
            p = p[2:]
        return p

    def _iter_source_files(self) -> Iterable[Path]:
        if self.target_files:
            for rel in sorted(self.target_files):
                file_path = (self.project_root / rel).resolve()
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield file_path
            return

        count = 0
        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = self._normalize_path(str(file_path.relative_to(self.project_root)))
            if "/.git/" in f"/{rel}/" or "/node_modules/" in f"/{rel}/":
                continue
            yield file_path
            count += 1
            if count >= self.max_files:
                break

    def _detect_language(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        if ext in TreeSitterParser.LANGUAGE_MAP:
            return TreeSitterParser.LANGUAGE_MAP[ext]
        if ext in {".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"}:
            return "cpp"
        if ext in {".c", ".h"}:
            return "c"
        return "text"

    def _extract_conditions(self, content: str) -> List[str]:
        conditions: List[str] = []
        for line in content.splitlines():
            raw = line.strip()
            if not raw:
                continue
            lower = raw.lower()
            if lower.startswith(("if ", "if(", "elif ", "else if", "switch", "case ", "while", "for ", "for(")):
                conditions.append(raw[:180])
            if len(conditions) >= 8:
                break
        return conditions

    def _extract_callees(self, content: str) -> Set[str]:
        callees: Set[str] = set()
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", content):
            name = match.group(1)
            if name in RESERVED_CALL_NAMES:
                continue
            if len(name) < 2:
                continue
            callees.add(name)
            if len(callees) >= 64:
                break
        return callees

    def _is_entry_function(self, symbol: FunctionSymbol) -> bool:
        name = symbol.name.lower()
        if name == "main":
            return True
        if any(token in name for token in ["handler", "controller", "route", "endpoint", "login", "auth"]):
            return True

        body = symbol.content.lower()
        route_patterns = [
            "@app.route",
            "@router.",
            "app.get(",
            "app.post(",
            "router.get(",
            "router.post(",
            "@requestmapping",
            "@getmapping",
            "@postmapping",
        ]
        return any(pattern in body for pattern in route_patterns)

    def _regex_extract_definitions(self, code: str, language: str) -> List[Tuple[str, int, int, str]]:
        """Fallback definition extractor: returns (name, start_line, end_line, content)."""
        lines = code.splitlines()
        defs: List[Tuple[str, int, int, str]] = []

        patterns: List[re.Pattern[str]] = []
        if language == "python":
            patterns = [re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")]
        elif language in {"javascript", "typescript", "tsx"}:
            patterns = [
                re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
                re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?\("),
            ]
        elif language == "java":
            patterns = [
                re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\],\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            ]
        elif language == "kotlin":
            patterns = [
                re.compile(r"^\s*(?:public|private|protected|internal|open|override|suspend|inline|tailrec|operator|infix|\s)*fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            ]
        elif language in {"c", "cpp"}:
            patterns = [
                re.compile(r"^\s*[A-Za-z_][\w\s\*:&<>]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{")
            ]

        for idx, line in enumerate(lines):
            matched_name: Optional[str] = None
            for pattern in patterns:
                m = pattern.match(line)
                if m:
                    matched_name = m.group(1)
                    break
            if not matched_name:
                continue
            if str(matched_name).strip().lower() in {"__attribute__", "__declspec"}:
                continue

            start = idx + 1
            end = start
            body_lines: List[str] = []

            if language == "python":
                # Indentation-based block end for python fallback.
                indent = len(line) - len(line.lstrip(" "))
                for j in range(idx, len(lines)):
                    current = lines[j]
                    body_lines.append(current)
                    end = j + 1
                    if j == idx:
                        continue
                    if not current.strip():
                        continue
                    if current.lstrip().startswith("#"):
                        continue
                    current_indent = len(current) - len(current.lstrip(" "))
                    # stop when we hit a sibling/parent block
                    if current_indent <= indent and (current.lstrip().startswith("def ") or current.lstrip().startswith("class ")):
                        body_lines.pop()
                        end = j
                        break
            else:
                depth = 0
                for j in range(idx, len(lines)):
                    current = lines[j]
                    depth += current.count("{")
                    depth -= current.count("}")
                    body_lines.append(current)
                    end = j + 1
                    if j > idx and depth <= 0:
                        break

            defs.append((matched_name, start, end, "\n".join(body_lines)))

        return defs

    def build(self) -> None:
        if self._built:
            return

        file_entries: List[Tuple[Path, str, str, str]] = []
        for file_path in self._iter_source_files():
            try:
                rel = self._normalize_path(str(file_path.relative_to(self.project_root)))
                code = file_path.read_text(encoding="utf-8", errors="replace")
                language = self._detect_language(file_path)
                file_entries.append((file_path, rel, code, language))
            except Exception:
                continue

        definition_results: Dict[str, Dict[str, Any]] = {}
        if self.definition_provider is not None and file_entries:
            definition_results = self.definition_provider.extract_definitions_batch(
                [
                    {"file_path": rel, "language": language, "content": code}
                    for _file_path, rel, code, language in file_entries
                ]
            )

        for file_path, rel, code, language in file_entries:
            try:
                definitions: List[Tuple[str, int, int, str]] = []
                runner_payload = definition_results.get(rel) or {}
                runner_definitions = runner_payload.get("definitions")
                if isinstance(runner_definitions, list):
                    for item in runner_definitions:
                        name = item.get("name")
                        if not name:
                            continue
                        start = int(item.get("start_point", (0, 0))[0]) + 1
                        end = int(item.get("end_point", (start, 0))[0]) + 1
                        if end < start:
                            end = start
                        body = "\n".join(code.splitlines()[start - 1 : end])
                        definitions.append((str(name), start, end, body))
                else:
                    tree = self.parser.parse(code, language)
                    if tree is not None:
                        for item in self.parser.extract_definitions(tree, code, language):
                            name = item.get("name")
                            if not name:
                                continue
                            start = int(item.get("start_point", (0, 0))[0]) + 1
                            end = int(item.get("end_point", (start, 0))[0]) + 1
                            if end < start:
                                end = start
                            body = "\n".join(code.splitlines()[start - 1 : end])
                            definitions.append((str(name), start, end, body))

                if not definitions:
                    definitions = self._regex_extract_definitions(code, language)

                for name, start, end, body in definitions:
                    symbol_id = f"{rel}:{name}:{start}"
                    symbol = FunctionSymbol(
                        id=symbol_id,
                        name=name,
                        file_path=rel,
                        language=language,
                        start_line=start,
                        end_line=end,
                        content=body,
                    )
                    symbol.control_conditions = self._extract_conditions(body)
                    symbol.callees = self._extract_callees(body)
                    symbol.is_entry = self._is_entry_function(symbol)
                    self.symbols_by_id[symbol_id] = symbol
                    self.symbols_by_name.setdefault(name, []).append(symbol)
            except Exception:
                continue

        self._built = True

    def infer_entry_points(self) -> List[FunctionSymbol]:
        self.build()
        entries = [sym for sym in self.symbols_by_id.values() if sym.is_entry]
        if entries:
            return entries[:80]

        # fallback: choose public-like functions
        fallback = sorted(self.symbols_by_id.values(), key=lambda s: (s.file_path, s.start_line))
        return fallback[:15]

    def find_symbol_by_location(self, file_path: str, line: int) -> Optional[FunctionSymbol]:
        self.build()
        normalized = self._normalize_path(file_path)
        for sym in self.symbols_by_id.values():
            if sym.file_path != normalized:
                continue
            if sym.start_line <= line <= sym.end_line:
                return sym
        return None

    def _neighbors(self, symbol: FunctionSymbol, extra_edges: Optional[Dict[str, Set[str]]] = None) -> List[FunctionSymbol]:
        candidates: Set[str] = set(symbol.callees)
        if extra_edges:
            candidates.update(extra_edges.get(symbol.name, set()))

        neighbors: List[FunctionSymbol] = []
        for callee in candidates:
            for target in self.symbols_by_name.get(callee, []):
                neighbors.append(target)
        return neighbors

    def find_path(
        self,
        target_file: str,
        target_line: int,
        max_depth: int = 8,
        entry_points: Optional[List[str]] = None,
        extra_edges: Optional[Dict[str, Set[str]]] = None,
    ) -> Dict[str, object]:
        self.build()
        blocked_reasons: List[str] = []

        target_symbol = self.find_symbol_by_location(target_file, target_line)
        if not target_symbol:
            blocked_reasons.append("target_symbol_not_found")
            return {
                "path_found": False,
                "target_symbol": None,
                "call_chain": [],
                "control_conditions": [],
                "entry_inferred": True,
                "blocked_reasons": blocked_reasons,
            }

        if entry_points:
            requested = {name.strip() for name in entry_points if isinstance(name, str) and name.strip()}
            entries = [sym for sym in self.symbols_by_id.values() if sym.name in requested]
            entry_inferred = False
            if not entries:
                entries = self.infer_entry_points()
                entry_inferred = True
        else:
            entries = self.infer_entry_points()
            entry_inferred = True

        if not entries:
            blocked_reasons.append("entry_points_not_found")
            return {
                "path_found": False,
                "target_symbol": target_symbol,
                "call_chain": [f"{target_symbol.file_path}:{target_symbol.name}"],
                "control_conditions": target_symbol.control_conditions[:6],
                "entry_inferred": True,
                "blocked_reasons": blocked_reasons,
            }

        queue: List[Tuple[FunctionSymbol, List[FunctionSymbol], int]] = []
        visited: Set[str] = set()
        for entry in entries:
            queue.append((entry, [entry], 0))
            visited.add(entry.id)

        while queue:
            current, path, depth = queue.pop(0)
            if current.id == target_symbol.id:
                conditions: List[str] = []
                for item in path:
                    conditions.extend(item.control_conditions[:2])
                call_chain = [f"{item.file_path}:{item.name}" for item in path]
                return {
                    "path_found": True,
                    "target_symbol": target_symbol,
                    "call_chain": call_chain,
                    "control_conditions": list(dict.fromkeys(conditions))[:12],
                    "entry_inferred": entry_inferred,
                    "blocked_reasons": blocked_reasons,
                }

            if depth >= max_depth:
                continue

            for neighbor in self._neighbors(current, extra_edges=extra_edges):
                if neighbor.id in visited:
                    continue
                visited.add(neighbor.id)
                queue.append((neighbor, [*path, neighbor], depth + 1))

        blocked_reasons.append("path_not_reachable_from_entries")
        return {
            "path_found": False,
            "target_symbol": target_symbol,
            "call_chain": [f"{target_symbol.file_path}:{target_symbol.name}"],
            "control_conditions": target_symbol.control_conditions[:6],
            "entry_inferred": entry_inferred,
            "blocked_reasons": blocked_reasons,
        }
