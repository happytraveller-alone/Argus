import asyncio

from fastapi import APIRouter

from app.api.v1.endpoints import static_tasks_cache as _cache
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
router.include_router(_pmd.router)
router.include_router(_phpstan.router)
router.include_router(_cache.router)


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


async def _execute_phpstan_scan(*args, **kwargs):
    _bind_phpstan_runtime()
    return await _phpstan._execute_phpstan_scan(*args, **kwargs)


async def _execute_pmd_scan(*args, **kwargs):
    _bind_pmd_runtime()
    return await _pmd._execute_pmd_scan(*args, **kwargs)


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

PhpstanScanTaskCreate = _phpstan.PhpstanScanTaskCreate
PhpstanScanTaskResponse = _phpstan.PhpstanScanTaskResponse
PhpstanFindingResponse = _phpstan.PhpstanFindingResponse

PmdScanTaskCreate = _pmd.PmdScanTaskCreate
PmdScanTaskResponse = _pmd.PmdScanTaskResponse
PmdFindingResponse = _pmd.PmdFindingResponse

_parse_opengrep_output = _opengrep._parse_opengrep_output
_parse_phpstan_output_payload = _phpstan._parse_phpstan_output_payload
_filter_phpstan_security_messages = _phpstan._filter_phpstan_security_messages

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
