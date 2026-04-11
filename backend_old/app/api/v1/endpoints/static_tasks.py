import asyncio

from fastapi import APIRouter

from app.api.v1.endpoints import static_tasks_cache as _cache
from app.api.v1.endpoints import static_tasks_opengrep as _opengrep
from app.api.v1.endpoints import static_tasks_opengrep_rules as _opengrep_rules
from app.api.v1.endpoints import static_tasks_pmd as _pmd
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
router.include_router(_cache.router)

def _bind_pmd_runtime() -> None:
    _pmd.asyncio = asyncio
    _pmd.async_session_factory = async_session_factory
    _pmd._clear_scan_task_cancel = _clear_scan_task_cancel
    _pmd._get_project_root = _get_project_root
    _pmd._is_scan_task_cancelled = _is_scan_task_cancelled
    _pmd._request_scan_task_cancel = _request_scan_task_cancel
    _pmd._sync_task_scan_duration = _sync_task_scan_duration


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

PmdScanTaskCreate = _pmd.PmdScanTaskCreate
PmdScanTaskResponse = _pmd.PmdScanTaskResponse
PmdFindingResponse = _pmd.PmdFindingResponse

_parse_opengrep_output = _opengrep._parse_opengrep_output

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
