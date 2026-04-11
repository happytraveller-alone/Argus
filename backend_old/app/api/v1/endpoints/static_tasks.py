import asyncio

from fastapi import APIRouter

from app.api.v1.endpoints import static_tasks_bandit as _bandit
from app.api.v1.endpoints import static_tasks_cache as _cache
from app.api.v1.endpoints import static_tasks_gitleaks as _gitleaks
from app.api.v1.endpoints import static_tasks_opengrep as _opengrep
from app.api.v1.endpoints import static_tasks_opengrep_rules as _opengrep_rules
from app.api.v1.endpoints import static_tasks_pmd as _pmd
from app.api.v1.endpoints import static_tasks_phpstan as _phpstan
from app.api.v1.endpoints.static_tasks_shared import (
    _clear_scan_task_cancel,
    _resolve_backend_venv_executable,
    _get_project_root,
    _is_scan_task_cancelled,
    _request_scan_task_cancel,
    _run_subprocess_with_tracking,
    _sync_task_scan_duration,
    async_session_factory,
    deps,
    get_db,
    logger,
    settings,
)


router = APIRouter()
router.include_router(_opengrep.router)
router.include_router(_opengrep_rules.router)
router.include_router(_bandit.router)
router.include_router(_pmd.router)
router.include_router(_phpstan.router)
router.include_router(_gitleaks.router)
router.include_router(_cache.router)


def _bind_bandit_runtime() -> None:
    _bandit.asyncio = asyncio
    _bandit.async_session_factory = async_session_factory
    _bandit._clear_scan_task_cancel = _clear_scan_task_cancel
    _bandit._get_project_root = _get_project_root
    _bandit._is_scan_task_cancelled = _is_scan_task_cancelled
    _bandit._resolve_backend_venv_executable = _resolve_backend_venv_executable
    _bandit._request_scan_task_cancel = _request_scan_task_cancel
    _bandit._run_subprocess_with_tracking = _run_subprocess_with_tracking
    _bandit._sync_task_scan_duration = _sync_task_scan_duration


def _bind_phpstan_runtime() -> None:
    _phpstan.asyncio = asyncio
    _phpstan.async_session_factory = async_session_factory
    _phpstan._clear_scan_task_cancel = _clear_scan_task_cancel
    _phpstan._get_project_root = _get_project_root
    _phpstan._is_scan_task_cancelled = _is_scan_task_cancelled
    _phpstan._request_scan_task_cancel = _request_scan_task_cancel
    _phpstan._run_subprocess_with_tracking = _run_subprocess_with_tracking
    _phpstan._sync_task_scan_duration = _sync_task_scan_duration


def _bind_pmd_runtime() -> None:
    _pmd.asyncio = asyncio
    _pmd.async_session_factory = async_session_factory
    _pmd._clear_scan_task_cancel = _clear_scan_task_cancel
    _pmd._get_project_root = _get_project_root
    _pmd._is_scan_task_cancelled = _is_scan_task_cancelled
    _pmd._request_scan_task_cancel = _request_scan_task_cancel
    _pmd._sync_task_scan_duration = _sync_task_scan_duration


def _bind_gitleaks_runtime() -> None:
    _gitleaks.asyncio = asyncio
    _gitleaks.async_session_factory = async_session_factory
    _gitleaks._clear_scan_task_cancel = _clear_scan_task_cancel
    _gitleaks._get_project_root = _get_project_root
    _gitleaks._is_scan_task_cancelled = _is_scan_task_cancelled
    _gitleaks._request_scan_task_cancel = _request_scan_task_cancel
    _gitleaks._run_subprocess_with_tracking = _run_subprocess_with_tracking
    _gitleaks._sync_task_scan_duration = _sync_task_scan_duration


async def _execute_bandit_scan(*args, **kwargs):
    _bind_bandit_runtime()
    return await _bandit._execute_bandit_scan(*args, **kwargs)


async def _execute_phpstan_scan(*args, **kwargs):
    _bind_phpstan_runtime()
    return await _phpstan._execute_phpstan_scan(*args, **kwargs)


async def _execute_pmd_scan(*args, **kwargs):
    _bind_pmd_runtime()
    return await _pmd._execute_pmd_scan(*args, **kwargs)


async def _execute_gitleaks_scan(*args, **kwargs):
    _bind_gitleaks_runtime()
    return await _gitleaks._execute_gitleaks_scan(*args, **kwargs)


OpengrepRuleSingleUploadRequest = _opengrep_rules.OpengrepRuleSingleUploadRequest
OpengrepRuleSingleUploadResponse = _opengrep_rules.OpengrepRuleSingleUploadResponse
OpengrepRuleBatchUpdateRequest = _opengrep_rules.OpengrepRuleBatchUpdateRequest
OpengrepRulePatchUploadResponse = _opengrep_rules.OpengrepRulePatchUploadResponse
PatchRuleCreationResponse = _opengrep_rules.PatchRuleCreationResponse

OpengrepScanTaskCreate = _opengrep.OpengrepScanTaskCreate
OpengrepScanTaskResponse = _opengrep.OpengrepScanTaskResponse
OpengrepFindingResponse = _opengrep.OpengrepFindingResponse
OpengrepFindingContextLine = _opengrep.OpengrepFindingContextLine
OpengrepFindingContextResponse = _opengrep.OpengrepFindingContextResponse
OpengrepScanProgressLogEntry = _opengrep.OpengrepScanProgressLogEntry
OpengrepScanProgressResponse = _opengrep.OpengrepScanProgressResponse

BanditScanTaskCreate = _bandit.BanditScanTaskCreate
BanditScanTaskResponse = _bandit.BanditScanTaskResponse
BanditFindingResponse = _bandit.BanditFindingResponse

PhpstanScanTaskCreate = _phpstan.PhpstanScanTaskCreate
PhpstanScanTaskResponse = _phpstan.PhpstanScanTaskResponse
PhpstanFindingResponse = _phpstan.PhpstanFindingResponse

PmdScanTaskCreate = _pmd.PmdScanTaskCreate
PmdScanTaskResponse = _pmd.PmdScanTaskResponse
PmdFindingResponse = _pmd.PmdFindingResponse

GitleaksScanTaskCreate = _gitleaks.GitleaksScanTaskCreate
GitleaksScanTaskResponse = _gitleaks.GitleaksScanTaskResponse
GitleaksFindingResponse = _gitleaks.GitleaksFindingResponse

_parse_opengrep_output = _opengrep._parse_opengrep_output
_parse_bandit_output_payload = _bandit._parse_bandit_output_payload
_parse_phpstan_output_payload = _phpstan._parse_phpstan_output_payload
_filter_phpstan_security_messages = _phpstan._filter_phpstan_security_messages
_build_effective_gitleaks_config_toml = _gitleaks._build_effective_gitleaks_config_toml

list_static_tasks = _opengrep.list_static_tasks
create_static_task = _opengrep.create_static_task
delete_static_task = _opengrep.delete_static_task
get_static_task = _opengrep.get_static_task
interrupt_static_task = _opengrep.interrupt_static_task
get_static_task_progress = _opengrep.get_static_task_progress
get_static_task_findings = _opengrep.get_static_task_findings
get_static_task_finding = _opengrep.get_static_task_finding
get_static_task_finding_context = _opengrep.get_static_task_finding_context
update_static_task_finding = _opengrep.update_static_task_finding

list_opengrep_rules = _opengrep_rules.list_opengrep_rules
get_opengrep_rule = _opengrep_rules.get_opengrep_rule
get_generating_rules = _opengrep_rules.get_generating_rules
create_opengrep_rule = _opengrep_rules.create_opengrep_rule
create_opengrep_generic_rule = _opengrep_rules.create_opengrep_generic_rule
edit_opengrep_rule = _opengrep_rules.edit_opengrep_rule
update_opengrep_rule = _opengrep_rules.update_opengrep_rule
delete_opengrep_rule = _opengrep_rules.delete_opengrep_rule
select_opengrep_rules = _opengrep_rules.select_opengrep_rules
upload_opengrep_rule_json = _opengrep_rules.upload_opengrep_rule_json
upload_patch_archive = _opengrep_rules.upload_patch_archive
upload_patch_directory = _opengrep_rules.upload_patch_directory
upload_opengrep_rules = _opengrep_rules.upload_opengrep_rules
upload_opengrep_rules_directory = _opengrep_rules.upload_opengrep_rules_directory

create_bandit_scan = _bandit.create_bandit_scan
list_bandit_tasks = _bandit.list_bandit_tasks
get_bandit_task = _bandit.get_bandit_task
interrupt_bandit_task = _bandit.interrupt_bandit_task
delete_bandit_task = _bandit.delete_bandit_task
get_bandit_findings = _bandit.get_bandit_findings
get_bandit_finding = _bandit.get_bandit_finding
update_bandit_finding_status = _bandit.update_bandit_finding_status
list_bandit_rules = _bandit.list_bandit_rules
get_bandit_rule = _bandit.get_bandit_rule
update_bandit_rule_enabled = _bandit.update_bandit_rule_enabled
batch_update_bandit_rules_enabled = _bandit.batch_update_bandit_rules_enabled
delete_bandit_rule = _bandit.delete_bandit_rule
restore_bandit_rule = _bandit.restore_bandit_rule
batch_delete_bandit_rules = _bandit.batch_delete_bandit_rules
batch_restore_bandit_rules = _bandit.batch_restore_bandit_rules

create_phpstan_scan = _phpstan.create_phpstan_scan
list_phpstan_tasks = _phpstan.list_phpstan_tasks
get_phpstan_task = _phpstan.get_phpstan_task
interrupt_phpstan_task = _phpstan.interrupt_phpstan_task
delete_phpstan_task = _phpstan.delete_phpstan_task
get_phpstan_findings = _phpstan.get_phpstan_findings
get_phpstan_finding = _phpstan.get_phpstan_finding
update_phpstan_finding_status = _phpstan.update_phpstan_finding_status
list_phpstan_rules = _phpstan.list_phpstan_rules
get_phpstan_rule = _phpstan.get_phpstan_rule
update_phpstan_rule = _phpstan.update_phpstan_rule
update_phpstan_rule_enabled = _phpstan.update_phpstan_rule_enabled
batch_update_phpstan_rules_enabled = _phpstan.batch_update_phpstan_rules_enabled
delete_phpstan_rule = _phpstan.delete_phpstan_rule
restore_phpstan_rule = _phpstan.restore_phpstan_rule
batch_delete_phpstan_rules = _phpstan.batch_delete_phpstan_rules
batch_restore_phpstan_rules = _phpstan.batch_restore_phpstan_rules

create_pmd_scan = _pmd.create_pmd_scan
list_pmd_tasks = _pmd.list_pmd_tasks
get_pmd_task = _pmd.get_pmd_task
interrupt_pmd_task = _pmd.interrupt_pmd_task
delete_pmd_task = _pmd.delete_pmd_task
get_pmd_findings = _pmd.get_pmd_findings
get_pmd_finding = _pmd.get_pmd_finding
update_pmd_finding_status = _pmd.update_pmd_finding_status

list_gitleaks_rules = _gitleaks.list_gitleaks_rules
get_gitleaks_rule = _gitleaks.get_gitleaks_rule
create_gitleaks_rule = _gitleaks.create_gitleaks_rule
update_gitleaks_rule = _gitleaks.update_gitleaks_rule
delete_gitleaks_rule = _gitleaks.delete_gitleaks_rule
batch_update_gitleaks_rules = _gitleaks.batch_update_gitleaks_rules
import_builtin_gitleaks_rules = _gitleaks.import_builtin_gitleaks_rules
create_gitleaks_scan = _gitleaks.create_gitleaks_scan
list_gitleaks_tasks = _gitleaks.list_gitleaks_tasks
get_gitleaks_task = _gitleaks.get_gitleaks_task
interrupt_gitleaks_task = _gitleaks.interrupt_gitleaks_task
delete_gitleaks_task = _gitleaks.delete_gitleaks_task
get_gitleaks_findings = _gitleaks.get_gitleaks_findings
get_gitleaks_finding = _gitleaks.get_gitleaks_finding
update_gitleaks_finding_status = _gitleaks.update_gitleaks_finding_status

list_pmd_presets = _pmd.list_pmd_presets
list_builtin_pmd_rulesets = _pmd.list_builtin_pmd_rulesets
get_builtin_pmd_ruleset = _pmd.get_builtin_pmd_ruleset
import_pmd_rule_config = _pmd.import_pmd_rule_config
list_pmd_rule_configs = _pmd.list_pmd_rule_configs
get_pmd_rule_config = _pmd.get_pmd_rule_config
update_pmd_rule_config = _pmd.update_pmd_rule_config
delete_pmd_rule_config = _pmd.delete_pmd_rule_config

get_repo_cache_stats = _cache.get_repo_cache_stats
cleanup_unused_cache = _cache.cleanup_unused_cache
clear_all_cache = _cache.clear_all_cache
