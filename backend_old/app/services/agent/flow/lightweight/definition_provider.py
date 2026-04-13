from __future__ import annotations

from typing import Any, Dict, List, Protocol

from app.services.flow_parser_runner import get_flow_parser_runner_client
from app.services.parser import TreeSitterParser


class DefinitionProvider(Protocol):
    def extract_definitions_batch(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        ...


class LocalDefinitionProvider:
    def __init__(self) -> None:
        self.parser = TreeSitterParser()

    def extract_definitions_batch(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for item in items:
            file_path = str(item.get("file_path") or "").strip()
            language = str(item.get("language") or "").strip() or "text"
            content = str(item.get("content") or "")
            definitions: List[Dict[str, Any]] = []
            diagnostics: List[str] = []
            try:
                tree = self.parser.parse(content, language)
                if tree is not None:
                    definitions = self.parser.extract_definitions(tree, content, language)
                    diagnostics.append("local_tree_sitter")
                else:
                    diagnostics.append("local_tree_sitter_unavailable")
            except Exception as exc:
                diagnostics.append(f"local_tree_sitter_error:{type(exc).__name__}")

            results[file_path] = {
                "file_path": file_path,
                "ok": True,
                "definitions": definitions,
                "diagnostics": diagnostics,
                "error": None,
            }
        return results


class RunnerDefinitionProvider:
    def __init__(self) -> None:
        self.client = get_flow_parser_runner_client()

    def extract_definitions_batch(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return self.client.extract_definitions_batch(items)


class HybridDefinitionProvider:
    def __init__(
        self,
        *,
        runner_provider: DefinitionProvider | None = None,
        local_provider: DefinitionProvider | None = None,
    ) -> None:
        self.runner_provider = runner_provider or RunnerDefinitionProvider()
        self.local_provider = local_provider or LocalDefinitionProvider()

    def extract_definitions_batch(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}

        try:
            results.update(self.runner_provider.extract_definitions_batch(items))
        except Exception:
            pass

        fallback_items: List[Dict[str, Any]] = []
        for item in items:
            file_path = str(item.get("file_path") or "").strip()
            payload = results.get(file_path) or {}
            if not payload.get("ok") or not isinstance(payload.get("definitions"), list):
                fallback_items.append(item)

        if fallback_items:
            local_results = self.local_provider.extract_definitions_batch(fallback_items)
            for file_path, payload in local_results.items():
                existing = results.get(file_path)
                if existing and isinstance(existing.get("diagnostics"), list):
                    payload["diagnostics"] = [
                        *existing["diagnostics"],
                        *payload.get("diagnostics", []),
                    ]
                results[file_path] = payload

        return results


def get_default_definition_provider() -> DefinitionProvider:
    return HybridDefinitionProvider()
