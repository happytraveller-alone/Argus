"""Bootstrap scan, scope filtering, and seed building helpers for agent tasks."""

import asyncio
import logging
import os
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

import yaml
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.opengrep import OpengrepRule
from app.services.agent.bootstrap import (
    BanditBootstrapScanner,
    OpenGrepBootstrapScanner,
    PhpstanBootstrapScanner,
)
from app.services.agent.bandit_bootstrap_rules import (
    _resolve_bandit_bootstrap_rule_ids,
)
from app.services.agent.bootstrap_entrypoints import (
    _build_seed_from_entrypoints,
    _discover_entry_points_deterministic,
)
from app.services.agent.bootstrap_findings import (
    _build_bootstrap_confidence_map_from_rules,
    _dedupe_bootstrap_findings,
    _normalize_bootstrap_finding_from_gitleaks_payload,
    _normalize_bootstrap_finding_from_opengrep_payload,
    _parse_bootstrap_opengrep_output,
)
from app.services.agent.bootstrap_gitleaks_runner import (
    _run_bootstrap_gitleaks_scan,
)
from app.services.agent.bootstrap_policy import (
    _normalize_verification_level,
    _resolve_agent_task_source_mode,
    _resolve_static_bootstrap_config,
)
from app.services.agent.bootstrap_seeds import (
    MAX_SEED_FINDINGS,
    _merge_seed_and_agent_findings,
    _normalize_seed_from_opengrep,
    _to_int,
)
from app.services.agent.scope_filters import (
    _build_core_audit_exclude_patterns,
    _filter_bootstrap_findings,
    _is_core_ignored_path,
    _normalize_scan_path,
)
from app.services.agent.utils.vulnerability_naming import (
    normalize_cwe_id as normalize_cwe_id_util,
)

logger = logging.getLogger(__name__)

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


__all__ = [name for name in globals() if not name.startswith("__")]
