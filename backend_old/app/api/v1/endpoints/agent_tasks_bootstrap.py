"""Bootstrap scan, scope filtering, and seed building helpers for agent tasks."""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

import yaml
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.agent_task import AgentTask
from app.models.bandit import BanditRuleState
from app.models.opengrep import OpengrepRule
from app.services.bandit_rules_snapshot import load_bandit_builtin_snapshot
from app.services.agent.bootstrap import (
    BanditBootstrapScanner,
    OpenGrepBootstrapScanner,
    PhpstanBootstrapScanner,
)
from app.services.scan_path_utils import normalize_scan_file_path
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container
from app.services.agent.utils.vulnerability_naming import (
    normalize_cwe_id as normalize_cwe_id_util,
)
from app.services.static_scan_runtime import (
    cleanup_scan_workspace,
    copy_project_tree_to_scan_dir,
    ensure_scan_logs_dir,
    ensure_scan_meta_dir,
    ensure_scan_output_dir,
    ensure_scan_project_dir,
    ensure_scan_workspace,
)

logger = logging.getLogger(__name__)


async def _prepare_scan_project_dir_async(
    project_root: str,
    project_dir: str | Path,
) -> None:
    await asyncio.to_thread(shutil.rmtree, project_dir, True)
    await asyncio.to_thread(copy_project_tree_to_scan_dir, project_root, project_dir)


_VERIFICATION_LEVEL_ALIASES = {
    "analysis_with_poc_plan": "analysis_with_poc_plan",
    "analysis_only": "analysis_with_poc_plan",
    "sandbox": "analysis_with_poc_plan",
    "generate_poc": "analysis_with_poc_plan",
    "poc_plan": "analysis_with_poc_plan",
}

HYBRID_TASK_NAME_MARKER = "[HYBRID]"
INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]"


def _normalize_bandit_rule_id(raw_rule_id: Any) -> str:
    return str(raw_rule_id or "").strip().upper()


def _extract_bandit_snapshot_test_ids_for_bootstrap() -> List[str]:
    try:
        payload = load_bandit_builtin_snapshot()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Bandit 预处理失败：Bandit 内置规则快照不存在: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Bandit 预处理失败：Bandit 内置规则快照格式错误: {exc}") from exc
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        return []

    test_ids: List[str] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        test_id = _normalize_bandit_rule_id(raw.get("test_id"))
        if not test_id:
            continue
        if test_id in test_ids:
            continue
        test_ids.append(test_id)
    return test_ids


def _resolve_bandit_effective_rule_ids_for_bootstrap(
    *,
    snapshot_test_ids: List[str],
    states_by_test_id: Dict[str, BanditRuleState],
) -> List[str]:
    return [
        test_id
        for test_id in snapshot_test_ids
        if (
            (states_by_test_id.get(test_id) is None)
            or (
                bool(getattr(states_by_test_id.get(test_id), "is_active", True))
                and not bool(getattr(states_by_test_id.get(test_id), "is_deleted", False))
            )
        )
    ]


async def _resolve_bandit_bootstrap_rule_ids(db: AsyncSession) -> List[str]:
    snapshot_test_ids = _extract_bandit_snapshot_test_ids_for_bootstrap()
    try:
        result = await db.execute(select(BanditRuleState))
    except ProgrammingError as exc:
        if "bandit_rule_states" in str(exc):
            raise RuntimeError("Bandit 预处理失败：数据库缺少 bandit_rule_states 表，请先运行 alembic upgrade head") from exc
        raise RuntimeError(f"Bandit 预处理失败：读取规则状态失败: {exc}") from exc

    rows = result.scalars().all()
    states_by_test_id = {
        _normalize_bandit_rule_id(getattr(row, "test_id", None)): row
        for row in rows
    }
    rule_ids = _resolve_bandit_effective_rule_ids_for_bootstrap(
        snapshot_test_ids=snapshot_test_ids,
        states_by_test_id=states_by_test_id,
    )
    if not rule_ids:
        raise RuntimeError("无可执行 Bandit 规则，请先在规则页启用至少 1 条规则")
    return rule_ids


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_verification_level(value: Optional[str]) -> str:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return "analysis_with_poc_plan"
    return _VERIFICATION_LEVEL_ALIASES.get(raw_value, "analysis_with_poc_plan")


def _resolve_agent_task_source_mode(
    name: Optional[str],
    description: Optional[str],
) -> str:
    normalized_name = str(name or "").strip().lower()
    normalized_description = str(description or "").strip().lower()
    normalized_combined = f"{normalized_name} {normalized_description}"
    if (
        HYBRID_TASK_NAME_MARKER.lower() in normalized_combined
        or "混合扫描" in normalized_combined
    ):
        return "hybrid"
    if INTELLIGENT_TASK_NAME_MARKER.lower() in normalized_combined:
        return "intelligent"
    # 历史无 marker 任务，默认迁移为 hybrid。
    return "hybrid"


def _resolve_static_bootstrap_config(
    task: AgentTask,
    source_mode: str,
) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "mode": "disabled",
        "opengrep_enabled": False,
        "bandit_enabled": False,
        "gitleaks_enabled": False,
        "phpstan_enabled": False,
    }
    if source_mode == "hybrid":
        defaults = {
            "mode": "embedded",
            "opengrep_enabled": True,
            "bandit_enabled": False,
            "gitleaks_enabled": False,
            "phpstan_enabled": False,
        }

    audit_scope = task.audit_scope if isinstance(task.audit_scope, dict) else {}
    static_bootstrap = (
        audit_scope.get("static_bootstrap")
        if isinstance(audit_scope.get("static_bootstrap"), dict)
        else {}
    )

    raw_mode = str(static_bootstrap.get("mode") or defaults["mode"]).strip().lower()
    mode = "embedded" if raw_mode == "embedded" else "disabled"
    if source_mode != "hybrid":
        mode = "disabled"

    opengrep_enabled = bool(
        static_bootstrap.get("opengrep_enabled", defaults["opengrep_enabled"])
    )
    bandit_enabled = bool(
        static_bootstrap.get("bandit_enabled", defaults["bandit_enabled"])
    )
    gitleaks_enabled = bool(
        static_bootstrap.get("gitleaks_enabled", defaults["gitleaks_enabled"])
    )
    phpstan_enabled = bool(
        static_bootstrap.get("phpstan_enabled", defaults["phpstan_enabled"])
    )

    if mode == "disabled":
        opengrep_enabled = False
        bandit_enabled = False
        gitleaks_enabled = False
        phpstan_enabled = False

    return {
        "mode": mode,
        "opengrep_enabled": opengrep_enabled,
        "bandit_enabled": bandit_enabled,
        "gitleaks_enabled": gitleaks_enabled,
        "phpstan_enabled": phpstan_enabled,
    }

def _normalize_bootstrap_confidence(confidence: Any) -> Optional[str]:
    normalized = str(confidence or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _extract_bootstrap_rule_lookup_keys(check_id: Any) -> List[str]:
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    keys: List[str] = []

    def _append(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in keys:
            keys.append(normalized)

    _append(raw_check_id)
    if "." in raw_check_id:
        _append(raw_check_id.rsplit(".", 1)[-1])
    return keys


def _extract_bootstrap_payload_confidence(rule_data: Any) -> Optional[str]:
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = _normalize_bootstrap_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = _normalize_bootstrap_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            metadata_confidence = _normalize_bootstrap_confidence(
                extra_metadata.get("confidence")
            )
            if metadata_confidence:
                return metadata_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = _normalize_bootstrap_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    return None


def _parse_bootstrap_opengrep_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []

    output = json.loads(stdout)
    if isinstance(output, dict):
        results = output.get("results", [])
    elif isinstance(output, list):
        results = output
    else:
        raise ValueError("Unexpected opengrep output type")

    if not isinstance(results, list):
        raise ValueError("Invalid opengrep results format")

    parsed: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def _build_bootstrap_confidence_map_from_rules(
    rules: List[OpengrepRule],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for rule in rules:
        normalized_confidence = _normalize_bootstrap_confidence(
            getattr(rule, "confidence", None)
        )
        if not normalized_confidence:
            continue
        lookup_values = [getattr(rule, "id", None), getattr(rule, "name", None)]
        for raw_value in lookup_values:
            for key in _extract_bootstrap_rule_lookup_keys(raw_value):
                mapping[key] = normalized_confidence
    return mapping


def _normalize_bootstrap_finding_from_opengrep_payload(
    finding: Dict[str, Any],
    confidence_map: Dict[str, str],
    index: int,
) -> Dict[str, Any]:
    rule_data = finding if isinstance(finding, dict) else {}
    check_id = rule_data.get("check_id") or rule_data.get("id")

    confidence = _extract_bootstrap_payload_confidence(rule_data)
    if confidence is None:
        for key in _extract_bootstrap_rule_lookup_keys(check_id):
            mapped = confidence_map.get(key)
            if mapped:
                confidence = mapped
                break

    extra = rule_data.get("extra") if isinstance(rule_data.get("extra"), dict) else {}
    title = extra.get("message") or str(check_id or "OpenGrep 发现")
    description = extra.get("message") or ""
    file_path = str(rule_data.get("path") or "").strip()
    start_obj = rule_data.get("start")
    end_obj = rule_data.get("end")
    start_line = int(start_obj.get("line") or 0) if isinstance(start_obj, dict) else 0
    end_line = (
        int(end_obj.get("line") or start_line)
        if isinstance(end_obj, dict)
        else start_line
    )
    severity_text = str(extra.get("severity") or "INFO").strip().upper()
    code_snippet = extra.get("lines")

    return {
        "id": str(check_id or f"opengrep-{index}"),
        "title": str(title),
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": severity_text,
        "confidence": confidence,
        "vulnerability_type": str(check_id or "opengrep_rule"),
        "source": "opengrep_bootstrap",
    }


def _normalize_bootstrap_finding_from_gitleaks_payload(
    finding: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    rule_id = str(finding.get("RuleID") or "gitleaks_secret").strip()
    description = str(finding.get("Description") or "Gitleaks 密钥泄露候选").strip()
    file_path = normalize_scan_file_path(
        str(finding.get("File") or "").strip(),
        "/scan/project",
    )
    start_line = int(finding.get("StartLine") or 0)
    end_line = int(finding.get("EndLine") or start_line)
    code_snippet = finding.get("Match") or finding.get("Secret")
    title = f"Gitleaks: {rule_id}" if rule_id else "Gitleaks 密钥泄露候选"

    return {
        "id": f"gitleaks-{index}",
        "title": title,
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": "ERROR",
        "confidence": "HIGH",
        "vulnerability_type": rule_id or "gitleaks_secret",
        "source": "gitleaks_bootstrap",
    }


def _filter_bootstrap_findings(
    normalized_findings: List[Dict[str, Any]],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in normalized_findings:
        file_path = str(item.get("file_path") or "").strip()
        if file_path and _is_core_ignored_path(file_path, exclude_patterns):
            continue
        severity_value = str(item.get("severity") or "").upper()
        confidence_value = _normalize_bootstrap_confidence(item.get("confidence"))
        if severity_value != "ERROR":
            continue
        if confidence_value not in {"HIGH", "MEDIUM"}:
            continue
        copied = dict(item)
        copied["confidence"] = confidence_value
        filtered.append(copied)
    return filtered


async def _run_bootstrap_opengrep_scan(
    project_root: str,
    active_rules: List[OpengrepRule],
) -> List[Dict[str, Any]]:
    merged_rules: List[Dict[str, Any]] = []
    for rule in active_rules:
        try:
            parsed_yaml = yaml.safe_load(rule.pattern_yaml)
        except Exception:
            continue
        if not isinstance(parsed_yaml, dict):
            continue
        rule_items = parsed_yaml.get("rules")
        if not isinstance(rule_items, list):
            continue
        for item in rule_items:
            if isinstance(item, dict):
                merged_rules.append(item)

    if not merged_rules:
        raise ValueError("No executable opengrep rules found")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
        yaml.dump({"rules": merged_rules}, tf, sort_keys=False, default_flow_style=False)
        merged_rule_path = tf.name

    try:
        cmd = ["opengrep", "--config", merged_rule_path, "--json", project_root]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        findings = _parse_bootstrap_opengrep_output(result.stdout or "")
        if result.returncode != 0 and not findings:
            stderr_text = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"opengrep failed: {stderr_text[:300]}")
        return findings
    finally:
        try:
            os.unlink(merged_rule_path)
        except Exception:
            pass


def _parse_bootstrap_gitleaks_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []
    output = json.loads(stdout)
    if isinstance(output, list):
        return [item for item in output if isinstance(item, dict)]
    if isinstance(output, dict):
        nested = output.get("findings")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    raise ValueError("Unexpected gitleaks output type")


async def _run_bootstrap_gitleaks_scan(
    project_root: str,
) -> List[Dict[str, Any]]:
    task_id = f"bootstrap-{uuid4().hex}"
    workspace_dir = ensure_scan_workspace("gitleaks-bootstrap", task_id)
    project_dir = ensure_scan_project_dir("gitleaks-bootstrap", task_id)
    output_dir = ensure_scan_output_dir("gitleaks-bootstrap", task_id)
    logs_dir = ensure_scan_logs_dir("gitleaks-bootstrap", task_id)
    meta_dir = ensure_scan_meta_dir("gitleaks-bootstrap", task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"

    try:
        await _prepare_scan_project_dir_async(project_root, project_dir)

        cmd = [
            "gitleaks",
            "detect",
            "--source",
            "/scan/project",
            "--report-format",
            "json",
            "--report-path",
            "/scan/output/report.json",
            "--exit-code",
            "0",
            "--no-git",
        ]
        result = await run_scanner_container(
            ScannerRunSpec(
                scanner_type="gitleaks-bootstrap",
                image=str(
                    getattr(settings, "SCANNER_GITLEAKS_IMAGE", "vulhunter/gitleaks-runner:latest")
                ),
                workspace_dir=str(workspace_dir),
                command=cmd,
                timeout_seconds=900,
                env={},
            )
        )
        if result.exit_code != 0:
            stderr_text = ""
            stdout_text = ""
            if result.stderr_path and Path(result.stderr_path).exists():
                stderr_text = Path(result.stderr_path).read_text(encoding="utf-8", errors="ignore")
            if result.stdout_path and Path(result.stdout_path).exists():
                stdout_text = Path(result.stdout_path).read_text(encoding="utf-8", errors="ignore")
            error_text = (stderr_text or stdout_text or result.error or "unknown error").strip()
            raise RuntimeError(f"gitleaks failed: {error_text[:300]}")

        if not report_path.exists():
            return []
        report_content = report_path.read_text(encoding="utf-8", errors="ignore")
        return _parse_bootstrap_gitleaks_output(report_content)
    finally:
        cleanup_scan_workspace("gitleaks-bootstrap", task_id)


def _dedupe_bootstrap_findings(
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, int, str, str]] = set()
    for item in findings:
        file_path = str(item.get("file_path") or "").strip()
        line_start = int(item.get("line_start") or 0)
        vuln_type = str(item.get("vulnerability_type") or "").strip()
        source = str(item.get("source") or "").strip()
        key = (file_path, line_start, vuln_type, source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _log_embedded_bootstrap_start(tool_name: str, project_root: str) -> None:
    logger.info(
        "[EmbeddedBootstrap][%s] start project_root=%s",
        tool_name,
        project_root,
    )


def _log_embedded_bootstrap_success(
    tool_name: str,
    project_root: str,
    total_findings: int,
    candidate_count: int,
) -> None:
    logger.info(
        "[EmbeddedBootstrap][%s] success project_root=%s total_findings=%d candidate_count=%d",
        tool_name,
        project_root,
        int(total_findings or 0),
        int(candidate_count or 0),
    )


def _log_embedded_bootstrap_error(
    tool_name: str,
    project_root: str,
    message: str,
    *,
    exc_info: bool = True,
) -> None:
    logger.error(
        "[EmbeddedBootstrap][%s] error project_root=%s reason=%s",
        tool_name,
        project_root,
        message,
        exc_info=exc_info,
    )


def _log_embedded_bootstrap_skipped(
    tool_name: str,
    project_root: str,
    reason: str,
) -> None:
    logger.info(
        "[EmbeddedBootstrap][%s] skipped project_root=%s reason=%s",
        tool_name,
        project_root,
        reason,
    )


async def _prepare_embedded_bootstrap_findings(
    db: AsyncSession,
    project_root: str,
    event_emitter: Any,
    programming_languages: Any = None,
    exclude_patterns: Optional[List[str]] = None,
    opengrep_enabled: bool = True,
    bandit_enabled: bool = False,
    gitleaks_enabled: bool = False,
    phpstan_enabled: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    opengrep_candidates: List[Dict[str, Any]] = []
    bandit_candidates: List[Dict[str, Any]] = []
    gitleaks_candidates: List[Dict[str, Any]] = []
    phpstan_candidates: List[Dict[str, Any]] = []
    opengrep_total_findings = 0
    bandit_total_findings = 0
    gitleaks_total_findings = 0
    phpstan_total_findings = 0

    if not opengrep_enabled and not bandit_enabled and not gitleaks_enabled and not phpstan_enabled:
        if event_emitter:
            await event_emitter.emit_info(
                " 静态预扫未启用：返回空候选，继续后续流程",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "disabled_empty_seed",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        return [], None, "disabled_empty_seed"

    if opengrep_enabled:
        _log_embedded_bootstrap_start("OpenGrep", project_root)
        active_rules_result = await db.execute(
            select(OpengrepRule).where(OpengrepRule.is_active == True)
        )
        active_rules = active_rules_result.scalars().all()
        if not active_rules:
            _log_embedded_bootstrap_error(
                "OpenGrep",
                project_root,
                "当前没有启用规则",
                exc_info=False,
            )
            if event_emitter:
                await event_emitter.emit_error(
                    "OpenGrep 预处理失败：当前没有启用规则，无法继续智能审计"
                )
            raise RuntimeError("OpenGrep 预处理失败：当前没有启用规则")

        if event_emitter:
            await event_emitter.emit_info(
                "🧪 OpenGrep 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_opengrep",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            scanner = OpenGrepBootstrapScanner(active_rules=active_rules)
            scan_result = await scanner.scan(project_root)
        except FileNotFoundError as exc:
            _log_embedded_bootstrap_error("OpenGrep", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error("OpenGrep 预处理失败：未安装 opengrep")
            raise RuntimeError("OpenGrep 预处理失败：未安装 opengrep") from exc
        except Exception as exc:
            _log_embedded_bootstrap_error("OpenGrep", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error(f"OpenGrep 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"OpenGrep 预处理失败：{str(exc)[:200]}") from exc

        opengrep_total_findings = int(getattr(scan_result, "total_findings", 0) or 0)
        normalized_opengrep_findings = []
        for finding in getattr(scan_result, "findings", []) or []:
            if hasattr(finding, "to_dict"):
                finding_payload = finding.to_dict()
            elif isinstance(finding, dict):
                finding_payload = dict(finding)
            else:
                continue
            normalized_opengrep_findings.append(finding_payload)
        opengrep_candidates = _filter_bootstrap_findings(
            normalized_opengrep_findings,
            exclude_patterns=exclude_patterns,
        )
        _log_embedded_bootstrap_success(
            "OpenGrep",
            project_root,
            opengrep_total_findings,
            len(opengrep_candidates),
        )

    if bandit_enabled:
        _log_embedded_bootstrap_start("Bandit", project_root)
        if event_emitter:
            await event_emitter.emit_info(
                "🧪 Bandit 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_bandit",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            bandit_rule_ids = await _resolve_bandit_bootstrap_rule_ids(db)
        except Exception as exc:
            message = str(exc)[:200]
            _log_embedded_bootstrap_error("Bandit", project_root, message)
            if event_emitter:
                await event_emitter.emit_error(message)
            raise RuntimeError(message) from exc
        try:
            scanner = BanditBootstrapScanner(rule_ids=bandit_rule_ids)
            scan_result = await scanner.scan(project_root)
        except FileNotFoundError as exc:
            _log_embedded_bootstrap_error("Bandit", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error("Bandit 预处理失败：未安装 bandit")
            raise RuntimeError("Bandit 预处理失败：未安装 bandit") from exc
        except Exception as exc:
            _log_embedded_bootstrap_error("Bandit", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error(f"Bandit 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"Bandit 预处理失败：{str(exc)[:200]}") from exc

        bandit_total_findings = int(getattr(scan_result, "total_findings", 0) or 0)
        normalized_bandit_findings = []
        for finding in getattr(scan_result, "findings", []) or []:
            if hasattr(finding, "to_dict"):
                finding_payload = finding.to_dict()
            elif isinstance(finding, dict):
                finding_payload = dict(finding)
            else:
                continue
            normalized_bandit_findings.append(finding_payload)
        bandit_candidates = _filter_bootstrap_findings(
            normalized_bandit_findings,
            exclude_patterns=exclude_patterns,
        )
        _log_embedded_bootstrap_success(
            "Bandit",
            project_root,
            bandit_total_findings,
            len(bandit_candidates),
        )

    if gitleaks_enabled:
        _log_embedded_bootstrap_start("Gitleaks", project_root)
        if event_emitter:
            await event_emitter.emit_info(
                "🧪 Gitleaks 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_gitleaks",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            parsed_gitleaks_findings = await _run_bootstrap_gitleaks_scan(project_root)
        except FileNotFoundError as exc:
            _log_embedded_bootstrap_error("Gitleaks", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error("Gitleaks 预处理失败：未安装 gitleaks")
            raise RuntimeError("Gitleaks 预处理失败：未安装 gitleaks") from exc
        except Exception as exc:
            _log_embedded_bootstrap_error("Gitleaks", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error(f"Gitleaks 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"Gitleaks 预处理失败：{str(exc)[:200]}") from exc

        gitleaks_total_findings = len(parsed_gitleaks_findings)
        normalized_gitleaks_findings = [
            _normalize_bootstrap_finding_from_gitleaks_payload(finding, index)
            for index, finding in enumerate(parsed_gitleaks_findings)
            if isinstance(finding, dict)
        ]
        gitleaks_candidates = _filter_bootstrap_findings(
            normalized_gitleaks_findings,
            exclude_patterns=exclude_patterns,
        )
        _log_embedded_bootstrap_success(
            "Gitleaks",
            project_root,
            gitleaks_total_findings,
            len(gitleaks_candidates),
        )

    if phpstan_enabled:
        _log_embedded_bootstrap_start("PHPStan", project_root)
        if event_emitter:
            await event_emitter.emit_info(
                "🧪 PHPStan 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_phpstan",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            scanner = PhpstanBootstrapScanner(level=8)
            scan_result = await scanner.scan(project_root)
        except FileNotFoundError as exc:
            _log_embedded_bootstrap_error("PHPStan", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error("PHPStan 预处理失败：未安装 phpstan")
            raise RuntimeError("PHPStan 预处理失败：未安装 phpstan") from exc
        except Exception as exc:
            _log_embedded_bootstrap_error("PHPStan", project_root, str(exc))
            if event_emitter:
                await event_emitter.emit_error(f"PHPStan 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"PHPStan 预处理失败：{str(exc)[:200]}") from exc

        phpstan_total_findings = int(getattr(scan_result, "total_findings", 0) or 0)
        normalized_phpstan_findings = []
        for finding in getattr(scan_result, "findings", []) or []:
            if hasattr(finding, "to_dict"):
                finding_payload = finding.to_dict()
            elif isinstance(finding, dict):
                finding_payload = dict(finding)
            else:
                continue
            normalized_phpstan_findings.append(finding_payload)
        phpstan_candidates = _filter_bootstrap_findings(
            normalized_phpstan_findings,
            exclude_patterns=exclude_patterns,
        )
        _log_embedded_bootstrap_success(
            "PHPStan",
            project_root,
            phpstan_total_findings,
            len(phpstan_candidates),
        )

    merged_candidates = _dedupe_bootstrap_findings(
        [*opengrep_candidates, *bandit_candidates, *gitleaks_candidates, *phpstan_candidates]
    )
    total_findings = (
        opengrep_total_findings
        + bandit_total_findings
        + gitleaks_total_findings
        + phpstan_total_findings
    )

    enabled_sources: List[str] = []
    if opengrep_enabled:
        enabled_sources.append("opengrep")
    if bandit_enabled:
        enabled_sources.append("bandit")
    if gitleaks_enabled:
        enabled_sources.append("gitleaks")
    if phpstan_enabled:
        enabled_sources.append("phpstan")
    bootstrap_source = f"embedded_{'_'.join(enabled_sources)}"

    if event_emitter:
        await event_emitter.emit_info(
            "内嵌静态预扫完成",
            metadata={
                "bootstrap": True,
                "bootstrap_task_id": None,
                "bootstrap_source": bootstrap_source,
                "bootstrap_total_findings": total_findings,
                "bootstrap_candidate_count": len(merged_candidates),
                "bootstrap_opengrep_total_findings": opengrep_total_findings,
                "bootstrap_opengrep_candidate_count": len(opengrep_candidates),
                "bootstrap_bandit_total_findings": bandit_total_findings,
                "bootstrap_bandit_candidate_count": len(bandit_candidates),
                "bootstrap_gitleaks_total_findings": gitleaks_total_findings,
                "bootstrap_gitleaks_candidate_count": len(gitleaks_candidates),
                "bootstrap_phpstan_total_findings": phpstan_total_findings,
                "bootstrap_phpstan_candidate_count": len(phpstan_candidates),
            },
        )
    return merged_candidates, None, bootstrap_source


MAX_SEED_FINDINGS = 25

_CORE_AUDIT_EXCLUDE_PATTERNS: List[str] = [
    "test/**",
    "tests/**",
    "**/test/**",
    "**/tests/**",
    ".*/**",
    "**/.*/**",
    "*config*.*",
    "**/*config*.*",
    "*settings*.*",
    "**/*settings*.*",
    ".env*",
    "**/.env*",
    "*.yml",
    "**/*.yml",
    "*.yaml",
    "**/*.yaml",
    "*.json",
    "**/*.json",
    "*.ini",
    "**/*.ini",
    "*.conf",
    "**/*.conf",
    "*.toml",
    "**/*.toml",
    "*.properties",
    "**/*.properties",
    "*.plist",
    "**/*.plist",
    "*.xml",
    "**/*.xml",
]


def _build_core_audit_exclude_patterns(
    user_patterns: Optional[List[str]],
) -> List[str]:
    merged: List[str] = []
    seen: Set[str] = set()
    raw_patterns = list(user_patterns or []) + _CORE_AUDIT_EXCLUDE_PATTERNS
    for raw in raw_patterns:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip().replace("\\", "/")
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(normalized)
    return merged


def _normalize_scan_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _path_components(path: str) -> List[str]:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return []
    return [part for part in normalized.split("/") if part not in {"", ".", ".."}]


def _match_exclude_patterns(path: str, patterns: Optional[List[str]]) -> bool:
    import fnmatch

    normalized = _normalize_scan_path(path)
    basename = os.path.basename(normalized)
    for pattern in patterns or []:
        if not isinstance(pattern, str):
            continue
        candidate = pattern.strip().replace("\\", "/")
        if not candidate:
            continue
        if fnmatch.fnmatch(normalized, candidate) or fnmatch.fnmatch(basename, candidate):
            return True
    return False


def _is_core_ignored_path(
    path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> bool:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return False

    parts = _path_components(normalized)
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in {"test", "tests"}:
            return True
        if part.startswith("."):
            return True

    if parts:
        last = parts[-1]
        if last.lower() in {"test", "tests"}:
            return True
        if last.startswith("."):
            return True

    effective_patterns = _build_core_audit_exclude_patterns(exclude_patterns)
    if _match_exclude_patterns(normalized, effective_patterns):
        return True

    return False


def _normalize_seed_from_opengrep(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 OpenGrep bootstrap 候选统一转换为 fixed-first 的 seed findings 格式。"""

    def map_severity(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if raw == "ERROR":
            return "high"
        if raw == "WARNING":
            return "medium"
        if raw == "INFO":
            return "low"
        return "medium"

    def map_confidence(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        raw = str(value or "").strip().upper()
        if raw == "HIGH":
            return 0.8
        if raw == "MEDIUM":
            return 0.7
        if raw == "LOW":
            return 0.4
        try:
            return max(0.0, min(float(raw), 1.0))
        except Exception:
            return 0.5

    seeds: List[Dict[str, Any]] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or item.get("path") or "").strip()
        line_start = _to_int(item.get("line_start")) or _to_int(item.get("line")) or 1
        line_end = _to_int(item.get("line_end")) or line_start
        vuln_type = str(item.get("vulnerability_type") or item.get("check_id") or "opengrep_rule").strip()

        title = item.get("title") or item.get("description") or "OpenGrep 发现"
        description = item.get("description") or ""
        code_snippet = item.get("code_snippet") or item.get("code") or ""

        raw_severity = item.get("severity") or item.get("extra", {}).get("severity")
        raw_confidence = item.get("confidence")

        seeds.append(
            {
                "id": item.get("id"),
                "title": str(title).strip() if title is not None else "OpenGrep 发现",
                "description": str(description).strip(),
                "file_path": file_path,
                "line_start": int(line_start),
                "line_end": int(line_end),
                "code_snippet": str(code_snippet)[:2000],
                "severity": map_severity(raw_severity),
                "confidence": map_confidence(raw_confidence),
                "vulnerability_type": vuln_type or "opengrep_rule",
                "source": str(item.get("source") or "opengrep_bootstrap"),
                "needs_verification": True,
                # 保留原始 OpenGrep 标记，便于溯源
                "bootstrap_severity": str(raw_severity or "").strip(),
                "bootstrap_confidence": str(raw_confidence or "").strip(),
            }
        )

    # 去重与截断（按 file+line+type）
    seen: Set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(key=lambda s: (-float(s.get("confidence") or 0.0), str(s.get("file_path") or "")))
    return deduped[:MAX_SEED_FINDINGS]


def _discover_entry_points_deterministic(
    project_root: str,
    target_files: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """在 OpenGrep 候选为空时，确定性发现入口点（grep-like + AST 兜底）。"""

    normalized_project_root = os.path.abspath(project_root)
    root = Path(normalized_project_root)
    effective_exclude_patterns = _build_core_audit_exclude_patterns(exclude_patterns)

    include_set = (
        {_normalize_scan_path(path) for path in target_files if isinstance(path, str)}
        if target_files
        else None
    )

    code_exts = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".go",
        ".php",
        ".rb",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }

    patterns: List[Tuple[str, re.Pattern[str]]] = [
        ("python_fastapi_route", re.compile(r"^\s*@(?:app|router)\.(get|post|put|delete|patch)\b", re.I)),
        ("python_flask_route", re.compile(r"^\s*@app\.route\b", re.I)),
        ("python_main", re.compile(r"__name__\s*==\s*[\"']__main__[\"']")),
        ("django_urlpatterns", re.compile(r"\burlpatterns\s*=")),
        ("express_route", re.compile(r"\b(app|router)\.(get|post|put|delete|patch)\s*\(", re.I)),
        ("node_listen", re.compile(r"\bapp\.listen\s*\(", re.I)),
        ("spring_mapping", re.compile(r"@\s*(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b")),
        ("spring_controller", re.compile(r"@\s*(RestController|Controller)\b")),
        ("go_http_handle", re.compile(r"\bhttp\.HandleFunc\s*\(", re.I)),
        ("laravel_route", re.compile(r"\bRoute::(get|post|put|delete|patch)\s*\(", re.I)),
    ]

    entry_points: List[Dict[str, Any]] = []
    entry_files: List[str] = []

    def consider_file(rel_path: str) -> bool:
        if include_set is not None and rel_path not in include_set:
            return False
        if _is_core_ignored_path(rel_path, effective_exclude_patterns):
            return False
        return True

    # 1) grep-like 入口点扫描（有限扫描，避免大仓库拖慢）
    max_scan_files = 600
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = os.path.relpath(dirpath, project_root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_core_ignored_path(
                f"{rel_dir}/{d}" if rel_dir else d,
                effective_exclude_patterns,
            )
        ]
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext not in code_exts:
                continue
            abs_path = Path(dirpath) / name
            try:
                rel = abs_path.relative_to(root).as_posix()
            except Exception:
                continue
            if _is_core_ignored_path(rel, effective_exclude_patterns):
                continue
            if not consider_file(_normalize_scan_path(rel)):
                continue
            scanned += 1
            if scanned > max_scan_files:
                break
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                for typ, pat in patterns:
                    m = pat.search(line)
                    if not m:
                        continue
                    method = None
                    if m.lastindex:
                        # best-effort: common patterns capture method in group(1) or group(2)
                        for gi in range(1, m.lastindex + 1):
                            g = m.group(gi)
                            if isinstance(g, str) and g.strip() and g.strip().lower() in {
                                "get",
                                "post",
                                "put",
                                "delete",
                                "patch",
                                "head",
                                "options",
                            }:
                                method = g.strip().lower()
                                break
                    entry_points.append(
                        {
                            "type": typ,
                            "file": rel,
                            "line": idx,
                            "method": method or "",
                            "evidence": stripped[:240],
                        }
                    )
                    if rel not in entry_files:
                        entry_files.append(rel)
                    if len(entry_points) >= 80:
                        break
                if len(entry_points) >= 80:
                    break
            if len(entry_points) >= 80:
                break
        if len(entry_points) >= 80 or scanned > max_scan_files:
            break

    # 2) AST 推断入口函数名（用于 flow pipeline 入口约束）
    entry_function_names: List[str] = []
    try:
        from app.services.agent.flow.lightweight.ast_index import ASTCallIndex

        ast_target_files = entry_files or (target_files or None)
        ast_index = ASTCallIndex(
            project_root=normalized_project_root,
            target_files=ast_target_files if isinstance(ast_target_files, list) else None,
        )
        inferred = ast_index.infer_entry_points()
        for sym in inferred or []:
            name = str(getattr(sym, "name", "")).strip()
            if name and name not in entry_function_names:
                entry_function_names.append(name)
            if len(entry_function_names) >= 80:
                break
    except Exception as exc:
        logger.debug("[EntryPoints] AST inference failed: %s", exc)

    return {
        "entry_points": entry_points,
        "entry_function_names": entry_function_names,
    }


async def _build_seed_from_entrypoints(
    project_root: str,
    target_vulns: Optional[List[str]],
    entry_function_names: List[str],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """基于入口点提示，使用 SmartScanTool 生成固定数量的 seed findings。"""
    from app.services.agent.tools import SmartScanTool

    severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    confidence_by_severity = {"critical": 0.9, "high": 0.8, "medium": 0.6, "low": 0.4, "info": 0.3}

    tool = SmartScanTool(project_root, exclude_patterns=exclude_patterns or [])
    result = await tool.execute(
        target=".",
        quick_mode=True,
        max_files=200,
        focus_vulnerabilities=target_vulns or None,
    )
    raw_findings = []
    if isinstance(result, object) and getattr(result, "success", False):
        metadata = getattr(result, "metadata", {}) or {}
        raw_findings = metadata.get("findings") if isinstance(metadata, dict) else []
    if not isinstance(raw_findings, list):
        raw_findings = []

    seeds: List[Dict[str, Any]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or "").strip()
        line_no = _to_int(item.get("line_number")) or 1
        vuln_type = str(item.get("vulnerability_type") or "potential_issue").strip() or "potential_issue"
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in severity_weight:
            severity = "medium"
        confidence = float(confidence_by_severity.get(severity, 0.5))

        matched_line = str(item.get("matched_line") or "").strip()
        context = str(item.get("context") or "").strip()
        code_snippet = matched_line or context

        title = f"{vuln_type} 可疑点（入口点回退扫描）"
        description = f"SmartScan 模式匹配：{item.get('pattern_name') or ''}".strip()
        if context:
            description = f"{description}\n上下文：\n{context}".strip()

        seeds.append(
            {
                "title": title,
                "description": description[:1200],
                "file_path": file_path,
                "line_start": int(line_no),
                "line_end": int(line_no),
                "code_snippet": str(code_snippet)[:2000],
                "severity": severity,
                "confidence": confidence,
                "vulnerability_type": vuln_type,
                "source": "fallback_entrypoints_smart_scan",
                "needs_verification": True,
                #  flow pipeline 入口约束（函数名列表）
                "entry_points": list(entry_function_names[:20]),
            }
        )

    # 去重与截断（按严重度+置信度）
    seen: Set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(
        key=lambda s: (
            -severity_weight.get(str(s.get("severity") or "medium").strip().lower(), 2),
            -float(s.get("confidence") or 0.0),
        )
    )
    return deduped[:MAX_SEED_FINDINGS]


def _merge_seed_and_agent_findings(
    seed_findings: List[Dict[str, Any]],
    agent_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """合并 seed 与 agent findings。

    严格门禁模式下，不再将未匹配 seed 兜底入库，避免未验证候选泄漏到最终结果。
    """
    seed_findings = [f for f in (seed_findings or []) if isinstance(f, dict)]
    agent_findings = [f for f in (agent_findings or []) if isinstance(f, dict)]

    def key_for(f: Dict[str, Any]) -> Tuple[str, int, str]:
        file_path = str(f.get("file_path") or "").replace("\\", "/").strip()
        line_start = _to_int(f.get("line_start")) or _to_int(f.get("line")) or 0
        vuln_type = str(f.get("vulnerability_type") or "").strip().lower()
        title = str(f.get("title") or "").strip().lower()
        if file_path and line_start and vuln_type:
            return (file_path, int(line_start), vuln_type)
        return (file_path, int(line_start), title)

    seed_by_key: Dict[Tuple[str, int, str], Dict[str, Any]] = {key_for(f): f for f in seed_findings}
    used: Set[Tuple[str, int, str]] = set()

    merged: List[Dict[str, Any]] = []
    for f in agent_findings:
        k = key_for(f)
        seed = seed_by_key.get(k)
        if seed:
            used.add(k)
            merged.append({**seed, **f})  # LLM/Agent 输出覆盖 seed 的默认字段
        else:
            merged.append(f)

    # 最终去重（防止 agent_findings 内部重复）
    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, int, str]] = set()
    for f in merged:
        k = key_for(f)
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
