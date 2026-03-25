from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


def _load_tree_sitter_parser():
    splitter_path = Path(__file__).resolve().parent / "app" / "services" / "rag" / "splitter.py"
    spec = importlib.util.spec_from_file_location("flow_parser_runner_splitter", splitter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load splitter module: {splitter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.TreeSitterParser


TreeSitterParser = _load_tree_sitter_parser()


DOT_EDGE_RE = re.compile(r'"([^"]+)"\s*->\s*"([^"]+)"')
FUNCTION_LIKE_TYPES = {"function", "method"}


def _load_request(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_response(path: str, payload: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_definitions_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    parser = TreeSitterParser()
    items = payload.get("items") if isinstance(payload, dict) else []
    results: List[Dict[str, Any]] = []

    for item in items if isinstance(items, list) else []:
        file_path = str(item.get("file_path") or "").strip()
        language = str(item.get("language") or "").strip() or "text"
        content = str(item.get("content") or "")
        diagnostics: List[str] = []
        definitions: List[Dict[str, Any]] = []
        error = None
        ok = True

        try:
            tree = parser.parse(content, language)
            if tree is not None:
                definitions = parser.extract_definitions(tree, content, language)
                diagnostics.append("runner_tree_sitter")
            else:
                diagnostics.append("runner_tree_sitter_unavailable")
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            diagnostics.append(f"runner_tree_sitter_error:{type(exc).__name__}")

        results.append(
            {
                "file_path": file_path,
                "ok": ok,
                "definitions": definitions,
                "diagnostics": diagnostics,
                "error": error,
            }
        )

    return {"items": results}


def _locate_enclosing_function(payload: Dict[str, Any]) -> Dict[str, Any]:
    parser = TreeSitterParser()
    file_path = str(payload.get("file_path") or "").strip()
    language = str(payload.get("language") or "").strip() or "text"
    content = str(payload.get("content") or "")
    line_start = int(payload.get("line_start") or 1)
    diagnostics: List[str] = []

    try:
        tree = parser.parse(content, language)
        if tree is None:
            diagnostics.append("runner_tree_sitter_unavailable")
            return {
                "ok": False,
                "file_path": file_path,
                "function": None,
                "start_line": None,
                "end_line": None,
                "language": language,
                "resolution_method": "missing_enclosing_function",
                "resolution_engine": "missing_enclosing_function",
                "diagnostics": diagnostics,
            }

        definitions = parser.extract_definitions(tree, content, language)
        candidates = [
            item
            for item in definitions
            if str(item.get("type") or "") in FUNCTION_LIKE_TYPES
            and int(item.get("start_point", [0, 0])[0]) + 1 <= line_start <= int(item.get("end_point", [0, 0])[0]) + 1
        ]
        if not candidates:
            diagnostics.append("runner_tree_sitter_no_enclosing_symbol")
            return {
                "ok": False,
                "file_path": file_path,
                "function": None,
                "start_line": None,
                "end_line": None,
                "language": language,
                "resolution_method": "missing_enclosing_function",
                "resolution_engine": "missing_enclosing_function",
                "diagnostics": diagnostics,
            }

        best = min(
            candidates,
            key=lambda item: (
                max(0, int(item.get("end_point", [0, 0])[0]) - int(item.get("start_point", [0, 0])[0])),
                int(item.get("start_point", [0, 0])[0]),
            ),
        )
        diagnostics.append("runner_tree_sitter")
        return {
            "ok": True,
            "file_path": file_path,
            "function": best.get("name"),
            "start_line": int(best.get("start_point", [0, 0])[0]) + 1,
            "end_line": int(best.get("end_point", [0, 0])[0]) + 1,
            "language": language,
            "resolution_method": "python_tree_sitter",
            "resolution_engine": "python_tree_sitter",
            "diagnostics": diagnostics,
        }
    except Exception as exc:
        diagnostics.append(f"runner_tree_sitter_error:{type(exc).__name__}")
        return {
            "ok": False,
            "file_path": file_path,
            "function": None,
            "start_line": None,
            "end_line": None,
            "language": language,
            "resolution_method": "missing_enclosing_function",
            "resolution_engine": "missing_enclosing_function",
            "diagnostics": diagnostics,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _normalize_symbol_name(raw_node: str) -> str:
    node = raw_node.strip().strip('"')
    if not node:
        return ""
    node = node.replace("\\", "/")
    if ":" in node:
        node = node.split(":")[-1]
    if "(" in node:
        node = node.split("(", 1)[0]
    tokens = re.split(r"[./:#\\\s]+", node)
    token = tokens[-1] if tokens else node
    return token.strip()


def _parse_dot_edges(dot_text: str) -> Dict[str, List[str]]:
    edges: Dict[str, List[str]] = {}
    for src_raw, dst_raw in DOT_EDGE_RE.findall(dot_text):
        src = _normalize_symbol_name(src_raw)
        dst = _normalize_symbol_name(dst_raw)
        if not src or not dst or src == dst:
            continue
        edges.setdefault(src, [])
        if dst not in edges[src]:
            edges[src].append(dst)
    return edges


def _build_code2flow_diagnostics(
    *,
    binary_path: str | None,
    probe_command: List[str] | None = None,
    stderr_text: str = "",
    error: str = "",
    used_engine: str = "fallback",
) -> Dict[str, str]:
    diagnostics: Dict[str, str] = {
        "binary_path": str(binary_path or ""),
        "probe_command": " ".join(shlex.quote(part) for part in (probe_command or ["code2flow", "--help"])),
        "stderr_excerpt": str(stderr_text or "").strip()[:400],
        "used_engine": used_engine,
    }
    if error:
        diagnostics["error"] = str(error)
    return diagnostics


def _code2flow_callgraph(payload: Dict[str, Any]) -> Dict[str, Any]:
    files = payload.get("files") if isinstance(payload, dict) else []
    if not isinstance(files, list) or not files:
        return {
            "ok": False,
            "edges": {},
            "blocked_reasons": ["code2flow_no_candidate_files"],
            "used_engine": "fallback",
            "diagnostics": {"error": "missing_files"},
        }

    code2flow_bin = shutil.which("code2flow")
    if not code2flow_bin:
        return {
            "ok": False,
            "edges": {},
            "blocked_reasons": ["code2flow_not_installed"],
            "used_engine": "fallback",
            "diagnostics": _build_code2flow_diagnostics(
                binary_path="",
                probe_command=["code2flow", "--help"],
                error="code2flow_binary_not_found",
                used_engine="fallback",
            ),
        }

    with tempfile.TemporaryDirectory(prefix="flow-parser-code2flow-") as temp_dir:
        workspace = Path(temp_dir)
        input_paths: List[str] = []
        for item in files:
            rel_path = str(item.get("file_path") or "").strip()
            content = str(item.get("content") or "")
            if not rel_path:
                continue
            target_path = workspace / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            input_paths.append(str(target_path))

        if not input_paths:
            return {
                "ok": False,
                "edges": {},
                "blocked_reasons": ["code2flow_no_candidate_files"],
                "used_engine": "fallback",
                "diagnostics": {"error": "missing_input_paths"},
            }

        output_dot = workspace / "graph.dot"
        commands = [
            [code2flow_bin, *input_paths, "-o", str(output_dot)],
            [code2flow_bin, "-o", str(output_dot), *input_paths],
            [code2flow_bin, *input_paths, "--output", str(output_dot)],
        ]

        last_error = ""
        last_probe_command: List[str] = [code2flow_bin, "--help"]
        last_stderr = ""
        for cmd in commands:
            last_probe_command = list(cmd)
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=40,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                last_stderr = last_error
                continue

            if proc.returncode == 0 and output_dot.exists():
                dot_text = output_dot.read_text(encoding="utf-8", errors="replace")
                edges = _parse_dot_edges(dot_text)
                if not edges:
                    return {
                        "ok": False,
                        "edges": {},
                        "blocked_reasons": ["code2flow_no_edges"],
                        "used_engine": "fallback",
                        "diagnostics": _build_code2flow_diagnostics(
                            binary_path=code2flow_bin,
                            probe_command=cmd,
                            stderr_text=proc.stderr or proc.stdout or "",
                            used_engine="fallback",
                        ),
                    }
                return {
                    "ok": True,
                    "edges": edges,
                    "blocked_reasons": [],
                    "used_engine": "code2flow",
                    "diagnostics": _build_code2flow_diagnostics(
                        binary_path=code2flow_bin,
                        probe_command=cmd,
                        stderr_text=proc.stderr or proc.stdout or "",
                        used_engine="code2flow",
                    ),
                }

            last_error = (proc.stderr or proc.stdout or "").strip()[:400]
            last_stderr = proc.stderr or proc.stdout or ""

        return {
            "ok": False,
            "edges": {},
            "blocked_reasons": ["code2flow_exec_failed"],
            "used_engine": "fallback",
            "diagnostics": _build_code2flow_diagnostics(
                binary_path=code2flow_bin,
                probe_command=last_probe_command,
                stderr_text=last_stderr,
                error=last_error or "code2flow_failed",
                used_engine="fallback",
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Flow/parser runner CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("definitions-batch", "locate-enclosing-function", "code2flow-callgraph"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--request", required=True)
        subparser.add_argument("--response", required=True)

    args = parser.parse_args()
    request = _load_request(args.request)

    if args.command == "definitions-batch":
        response = _extract_definitions_batch(request)
    elif args.command == "locate-enclosing-function":
        response = _locate_enclosing_function(request)
    else:
        response = _code2flow_callgraph(request)

    _write_response(args.response, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
