#!/usr/bin/env python3
"""Generate Python endpoint inventory and bucket it for Rust migration control."""

from __future__ import annotations

import argparse
import ast
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class RouteDef:
    method: str
    path: str
    source_module: str
    source_file: str


@dataclass(frozen=True)
class ChildRouter:
    module_name: str
    prefix: str


def normalize_path(path: str) -> str:
    value = re.sub(r"/{2,}", "/", path.strip())
    if not value.startswith("/"):
        value = "/" + value
    if value != "/" and value.endswith("/"):
        value = value[:-1]
    return value


def join_path(base: str, child: str) -> str:
    return normalize_path(f"{base.rstrip('/')}/{child.lstrip('/')}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve_module_file(repo_root: Path, module_name: str) -> Path:
    return repo_root / "backend_old" / "app" / "api" / "v1" / "endpoints" / f"{module_name}.py"


def parse_router_file(path: Path) -> tuple[List[RouteDef], List[ChildRouter]]:
    text = read_text(path)
    tree = ast.parse(text, filename=str(path))

    module_aliases: Dict[str, str] = {}
    router_aliases: Dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module == "app.api.v1.endpoints":
            for name in node.names:
                alias = name.asname or name.name
                module_aliases[alias] = name.name
        elif module.startswith("app.api.v1.endpoints."):
            mod = module.split(".")[-1]
            for name in node.names:
                alias = name.asname or name.name
                if name.name == "router":
                    router_aliases[alias] = mod
                else:
                    module_aliases[alias] = mod
        elif module.startswith("."):
            mod = module.split(".")[-1]
            for name in node.names:
                alias = name.asname or name.name
                if name.name == "router":
                    router_aliases[alias] = mod
                else:
                    module_aliases[alias] = mod

    route_pattern = re.compile(
        r"""@router\.(get|post|put|patch|delete|head|options)\(\s*(['"])(.*?)\2""",
        re.IGNORECASE | re.DOTALL,
    )
    routes: List[RouteDef] = []
    for method, _, raw_path in route_pattern.findall(text):
        routes.append(
            RouteDef(
                method=method.upper(),
                path=raw_path,
                source_module=path.stem,
                source_file=str(path),
            )
        )

    children: List[ChildRouter] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.attr != "include_router":
            continue
        if not node.args:
            continue

        module_name = None
        arg0 = node.args[0]
        if isinstance(arg0, ast.Attribute) and isinstance(arg0.value, ast.Name) and arg0.attr == "router":
            module_name = module_aliases.get(arg0.value.id)
        elif isinstance(arg0, ast.Name):
            module_name = router_aliases.get(arg0.id) or module_aliases.get(arg0.id)
        if not module_name:
            continue

        prefix = ""
        for kw in node.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value
                break
        children.append(ChildRouter(module_name=module_name, prefix=prefix))

    return routes, children


def collect_all_routes(repo_root: Path) -> List[RouteDef]:
    api_file = repo_root / "backend_old" / "app" / "api" / "v1" / "api.py"
    root_routes, root_children = parse_router_file(api_file)
    all_routes = list(root_routes)

    stack: List[Tuple[str, str]] = [(child.module_name, child.prefix) for child in root_children]
    visited: set[Tuple[str, str]] = set()

    while stack:
        module_name, mounted_prefix = stack.pop()
        key = (module_name, mounted_prefix)
        if key in visited:
            continue
        visited.add(key)

        module_file = resolve_module_file(repo_root, module_name)
        if not module_file.exists():
            continue
        mod_routes, children = parse_router_file(module_file)
        for route in mod_routes:
            all_routes.append(
                RouteDef(
                    method=route.method,
                    path=join_path(mounted_prefix, route.path),
                    source_module=route.source_module,
                    source_file=route.source_file,
                )
            )
        for child in children:
            stack.append((child.module_name, join_path(mounted_prefix, child.prefix)))

    deduped = sorted(
        {(r.method, join_path(API_PREFIX, r.path), r.source_module, r.source_file) for r in all_routes},
        key=lambda x: (x[1], x[0], x[2]),
    )
    return [
        RouteDef(method=method, path=path, source_module=module, source_file=src)
        for method, path, module, src in deduped
    ]


def classify_status(path: str) -> tuple[str, str]:
    if path.startswith("/api/v1/users"):
        return "retire", "users scope removed in Rust plan"
    if path.startswith("/api/v1/config"):
        return "retire", "old /config contract retired (replaced by /system-config)"
    if path.startswith("/api/v1/projects/") and "/members" in path:
        return "retire", "project members endpoints retired"
    if path.startswith("/api/v1/prompts"):
        return "defer", "prompts deferred in current waves"

    # Current wave ownership, not eventual end-state ownership.
    migrate_prefixes = (
        "/api/v1/projects",
        "/api/v1/system-config",
        "/api/v1/search",
        "/api/v1/skills",
    )
    for prefix in migrate_prefixes:
        if path.startswith(prefix):
            return "migrate", f"owned in current wave ({prefix})"

    return "proxy", "not yet migrated in this wave but still required"


def write_inventory(routes: Iterable[RouteDef], csv_path: Path, summary_path: Path) -> None:
    rows = []
    bucket_counts = {"migrate": 0, "retire": 0, "defer": 0, "proxy": 0}

    for route in routes:
        status, reason = classify_status(route.path)
        bucket_counts[status] += 1
        rows.append(
            {
                "method": route.method,
                "path": route.path,
                "status": status,
                "reason": reason,
                "source_module": route.source_module,
                "source_file": route.source_file,
            }
        )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["method", "path", "status", "reason", "source_module", "source_file"],
        )
        writer.writeheader()
        writer.writerows(rows)

    total = sum(bucket_counts.values())
    lines = [
        "# Python Endpoint Inventory Summary",
        "",
        f"- Total routes: `{total}`",
        f"- Migrate: `{bucket_counts['migrate']}`",
        f"- Retire: `{bucket_counts['retire']}`",
        f"- Defer: `{bucket_counts['defer']}`",
        f"- Proxy: `{bucket_counts['proxy']}`",
        "",
        f"- Source inventory: `{csv_path.as_posix()}`",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--out-csv",
        default="plan/wait_correct/route-inventory/python-endpoints-inventory.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--out-summary",
        default="plan/wait_correct/route-inventory/python-endpoints-summary.md",
        help="Output summary markdown path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    routes = collect_all_routes(repo_root)
    write_inventory(
        routes=routes,
        csv_path=(repo_root / args.out_csv).resolve(),
        summary_path=(repo_root / args.out_summary).resolve(),
    )
    print(f"Generated {len(routes)} routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
