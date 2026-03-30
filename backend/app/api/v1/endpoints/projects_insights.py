from app.api.v1.endpoints.projects_shared import *
from app.api.v1.endpoints.static_tasks_bandit import _extract_bandit_snapshot_rules
from app.api.v1.endpoints.static_tasks_phpstan import _extract_phpstan_snapshot_rules
from app.models.yasa import YasaRuleConfig
from app.services.yasa_rules_snapshot import extract_yasa_snapshot_rules
from app.models.project_management_metrics import ProjectManagementMetrics
from urllib.parse import urlencode

router = APIRouter()

STATIC_SCAN_BATCH_MARKER_PREFIX = "[[STATIC_BATCH:"
STATIC_SCAN_BATCH_MARKER_SUFFIX = "]]"
STATIC_SCAN_PAIRING_WINDOW_MS = 60 * 1000
DASHBOARD_TASK_STATUS_KEYS = (
    "pending",
    "running",
    "completed",
    "failed",
    "interrupted",
    "cancelled",
)
DASHBOARD_SCAN_TYPE_KEYS = ("static", "intelligent", "hybrid")


def _build_empty_task_status_by_scan_type() -> Dict[str, Dict[str, int]]:
    return {
        status_key: {scan_type: 0 for scan_type in DASHBOARD_SCAN_TYPE_KEYS}
        for status_key in DASHBOARD_TASK_STATUS_KEYS
    }


def _extract_static_scan_batch_id(name: Any) -> Optional[str]:
    text = str(name or "")
    start = text.rfind(STATIC_SCAN_BATCH_MARKER_PREFIX)
    if start == -1:
        return None
    content_start = start + len(STATIC_SCAN_BATCH_MARKER_PREFIX)
    end = text.find(STATIC_SCAN_BATCH_MARKER_SUFFIX, content_start)
    if end == -1:
        return None
    batch_id = text[content_start:end].strip()
    return batch_id or None


def _normalize_dashboard_task_timestamp(value: Any) -> int:
    normalized = _coerce_datetime(value)
    if normalized is None:
        return 0
    return int(normalized.timestamp() * 1000)


def _resolve_dashboard_static_group_status(group: Dict[str, Any]) -> str:
    statuses = [
        _normalize_status_token((group.get("opengrep_task") or {}).get("status")),
        _normalize_status_token((group.get("gitleaks_task") or {}).get("status")),
        _normalize_status_token((group.get("bandit_task") or {}).get("status")),
        _normalize_status_token((group.get("phpstan_task") or {}).get("status")),
        _normalize_status_token((group.get("yasa_task") or {}).get("status")),
    ]
    statuses = [status for status in statuses if status]

    if not statuses:
        return "failed"
    if any(status == "running" for status in statuses):
        return "running"
    if all(status == "pending" for status in statuses):
        return "pending"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "pending" for status in statuses):
        return "running"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status in {"cancelled", "interrupted", "aborted"} for status in statuses):
        return "interrupted"
    return "failed"


def _build_dashboard_static_detail_path(group: Dict[str, Any]) -> str:
    opengrep_task = group.get("opengrep_task")
    gitleaks_task = group.get("gitleaks_task")
    bandit_task = group.get("bandit_task")
    phpstan_task = group.get("phpstan_task")
    yasa_task = group.get("yasa_task")
    primary_task = opengrep_task or gitleaks_task or bandit_task or phpstan_task or yasa_task
    if not primary_task:
        return "/tasks/static"

    query_params: List[tuple[str, str]] = []
    if opengrep_task:
        query_params.append(("opengrepTaskId", str(opengrep_task["task_id"])))
    if gitleaks_task:
        query_params.append(("gitleaksTaskId", str(gitleaks_task["task_id"])))
    if bandit_task:
        query_params.append(("banditTaskId", str(bandit_task["task_id"])))
    if phpstan_task:
        query_params.append(("phpstanTaskId", str(phpstan_task["task_id"])))
    if yasa_task:
        query_params.append(("yasaTaskId", str(yasa_task["task_id"])))

    if (
        not opengrep_task
        and gitleaks_task
        and not bandit_task
        and not phpstan_task
        and not yasa_task
    ):
        query_params.append(("tool", "gitleaks"))
    if (
        not opengrep_task
        and not gitleaks_task
        and bandit_task
        and not phpstan_task
        and not yasa_task
    ):
        query_params.append(("tool", "bandit"))
    if (
        not opengrep_task
        and not gitleaks_task
        and not bandit_task
        and phpstan_task
        and not yasa_task
    ):
        query_params.append(("tool", "phpstan"))
    if (
        not opengrep_task
        and not gitleaks_task
        and not bandit_task
        and not phpstan_task
        and yasa_task
    ):
        query_params.append(("tool", "yasa"))

    query_string = urlencode(query_params)
    base_path = f"/static-analysis/{primary_task['task_id']}"
    return f"{base_path}?{query_string}" if query_string else base_path


def _build_dashboard_static_recent_tasks(
    static_task_records: List[Dict[str, Any]],
    project_name_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    tasks_by_project: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in static_task_records:
        project_id = str(record.get("project_id") or "")
        created_at = _coerce_datetime(record.get("created_at"))
        if not project_id or created_at is None:
            continue
        normalized_record = dict(record)
        normalized_record["project_id"] = project_id
        normalized_record["created_at"] = created_at
        tasks_by_project[project_id].append(normalized_record)

    grouped_recent_tasks: List[Dict[str, Any]] = []
    engine_key_map = {
        "opengrep": "opengrep_task",
        "gitleaks": "gitleaks_task",
        "bandit": "bandit_task",
        "phpstan": "phpstan_task",
        "yasa": "yasa_task",
    }

    for project_id, records in tasks_by_project.items():
        sorted_records = sorted(
            records,
            key=lambda item: _normalize_dashboard_task_timestamp(item.get("created_at")),
        )
        batch_tagged_records = [
            item for item in sorted_records if _extract_static_scan_batch_id(item.get("name"))
        ]
        legacy_records = [
            item for item in sorted_records if not _extract_static_scan_batch_id(item.get("name"))
        ]
        project_groups: List[Dict[str, Any]] = []

        def assign_record_to_groups(
            item: Dict[str, Any],
            candidate_groups: List[Dict[str, Any]],
            *,
            ignore_window: bool,
        ) -> None:
            task_timestamp = _normalize_dashboard_task_timestamp(item.get("created_at"))
            engine_key = engine_key_map[str(item.get("engine") or "")]
            best_group_index = -1
            best_diff = float("inf")

            for index, group in enumerate(candidate_groups):
                group_timestamp = _normalize_dashboard_task_timestamp(group.get("created_at"))
                diff = abs(task_timestamp - group_timestamp)
                if not ignore_window and diff > STATIC_SCAN_PAIRING_WINDOW_MS:
                    continue
                if group.get(engine_key) is not None:
                    continue
                if diff < best_diff:
                    best_diff = diff
                    best_group_index = index

            if best_group_index == -1:
                next_group = {
                    "project_id": project_id,
                    "created_at": item.get("created_at"),
                    "opengrep_task": None,
                    "gitleaks_task": None,
                    "bandit_task": None,
                    "phpstan_task": None,
                    "yasa_task": None,
                }
                next_group[engine_key] = item
                candidate_groups.append(next_group)
                return

            candidate_groups[best_group_index][engine_key] = item

        groups_by_batch: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in batch_tagged_records:
            batch_id = _extract_static_scan_batch_id(item.get("name"))
            if not batch_id:
                continue
            assign_record_to_groups(
                item,
                groups_by_batch[batch_id],
                ignore_window=True,
            )
        for groups_of_batch in groups_by_batch.values():
            project_groups.extend(groups_of_batch)

        legacy_groups: List[Dict[str, Any]] = []
        for item in legacy_records:
            assign_record_to_groups(item, legacy_groups, ignore_window=False)
        project_groups.extend(legacy_groups)

        project_name = project_name_map.get(project_id, "未知项目")
        for group in project_groups:
            primary_task = (
                group.get("opengrep_task")
                or group.get("gitleaks_task")
                or group.get("bandit_task")
                or group.get("phpstan_task")
                or group.get("yasa_task")
            )
            if not primary_task:
                continue
            grouped_recent_tasks.append(
                {
                    "task_id": str(primary_task.get("task_id") or ""),
                    "task_type": "静态扫描",
                    "title": f"静态扫描 · {project_name}",
                    "engine": str(primary_task.get("engine") or "opengrep"),
                    "status": _resolve_dashboard_static_group_status(group),
                    "created_at": group.get("created_at"),
                    "detail_path": _build_dashboard_static_detail_path(group),
                }
            )

    return grouped_recent_tasks


def _count_snapshot_rules_with_deleted_states(
    snapshot_rules: List[Dict[str, Any]],
    state_rows: List[Any],
    *,
    rule_id_key: str,
    normalize_rule_id: Optional[Callable[[Any], str]] = None,
) -> int:
    deleted_rule_ids: set[str] = set()
    normalize = normalize_rule_id or (lambda value: str(value or "").strip())

    for row in state_rows:
        if isinstance(row, (list, tuple)):
            raw_rule_id = row[0] if len(row) > 0 else None
            is_deleted = bool(row[1]) if len(row) > 1 else False
        else:
            raw_rule_id = getattr(row, rule_id_key, None)
            is_deleted = bool(getattr(row, "is_deleted", False))
        normalized_rule_id = normalize(raw_rule_id)
        if normalized_rule_id and is_deleted:
            deleted_rule_ids.add(normalized_rule_id)

    total = 0
    for item in snapshot_rules:
        normalized_rule_id = normalize(item.get(rule_id_key))
        if normalized_rule_id and normalized_rule_id not in deleted_rule_ids:
            total += 1
    return total


async def _get_yasa_rule_total(db: Optional[AsyncSession] = None) -> int:
    try:
        builtin_total = len(extract_yasa_snapshot_rules())
    except Exception:
        builtin_total = 0

    if db is None:
        return builtin_total

    try:
        custom_rule_total_result = await db.execute(
            select(func.count())
            .select_from(YasaRuleConfig)
            .where(YasaRuleConfig.source == "custom")
        )
        custom_rule_total = int(custom_rule_total_result.scalar() or 0)
    except Exception:
        custom_rule_total = 0

    return max(builtin_total, 0) + max(custom_rule_total, 0)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get global statistics.
    """
    interrupted_statuses = ("interrupted", "aborted", "cancelled")

    async def _count(model, where_clause=None) -> int:
        stmt = select(func.count(model.id))
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = await db.execute(stmt)
        return int(result.scalar() or 0)

    total_projects = await _count(Project)
    active_projects = total_projects

    # 任务统计（统一从数据库聚合，不再前端拼接）
    agent_total = await _count(AgentTask)
    agent_completed = await _count(AgentTask, func.lower(AgentTask.status) == "completed")
    agent_running = await _count(AgentTask, func.lower(AgentTask.status) == "running")
    agent_failed = await _count(AgentTask, func.lower(AgentTask.status) == "failed")
    agent_interrupted = await _count(
        AgentTask, func.lower(AgentTask.status).in_(interrupted_statuses)
    )

    opengrep_total = await _count(OpengrepScanTask)
    opengrep_completed = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "completed"
    )
    opengrep_running = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "running"
    )
    opengrep_failed = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "failed"
    )
    opengrep_interrupted = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status).in_(interrupted_statuses)
    )

    gitleaks_total = await _count(GitleaksScanTask)
    gitleaks_completed = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "completed"
    )
    gitleaks_running = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "running"
    )
    gitleaks_failed = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "failed"
    )
    gitleaks_interrupted = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status).in_(interrupted_statuses)
    )

    bandit_total = await _count(BanditScanTask)
    bandit_completed = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "completed"
    )
    bandit_running = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "running"
    )
    bandit_failed = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "failed"
    )
    bandit_interrupted = await _count(
        BanditScanTask, func.lower(BanditScanTask.status).in_(interrupted_statuses)
    )

    phpstan_total = await _count(PhpstanScanTask)
    phpstan_completed = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "completed"
    )
    phpstan_running = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "running"
    )
    phpstan_failed = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "failed"
    )
    phpstan_interrupted = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status).in_(interrupted_statuses)
    )

    total_tasks = (
        agent_total + opengrep_total + gitleaks_total + bandit_total + phpstan_total
    )
    completed_tasks = (
        agent_completed
        + opengrep_completed
        + gitleaks_completed
        + bandit_completed
        + phpstan_completed
    )
    running_tasks = (
        agent_running
        + opengrep_running
        + gitleaks_running
        + bandit_running
        + phpstan_running
    )
    failed_tasks = (
        agent_failed + opengrep_failed + gitleaks_failed + bandit_failed + phpstan_failed
    )
    interrupted_tasks = (
        agent_interrupted
        + opengrep_interrupted
        + gitleaks_interrupted
        + bandit_interrupted
        + phpstan_interrupted
    )

    # 问题统计（统一聚合）
    total_issues = (
        await _count(AgentFinding)
        + await _count(OpengrepFinding)
        + await _count(GitleaksFinding)
        + await _count(BanditFinding)
        + await _count(PhpstanFinding)
    )
    resolved_issues = (
        await _count(
            AgentFinding,
            func.lower(AgentFinding.status).in_(("resolved", "verified", "fixed")),
        )
        + await _count(OpengrepFinding, func.lower(OpengrepFinding.status) == "verified")
        + await _count(GitleaksFinding, func.lower(GitleaksFinding.status) == "verified")
        + await _count(BanditFinding, func.lower(BanditFinding.status) == "verified")
        + await _count(PhpstanFinding, func.lower(PhpstanFinding.status) == "verified")
    )

    return {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "interrupted_tasks": interrupted_tasks,
        "running_tasks": running_tasks,
        "failed_tasks": failed_tasks,
        "total_issues": total_issues,
        "resolved_issues": resolved_issues,
    }


@router.get("/dashboard-snapshot", response_model=DashboardSnapshotResponse)
async def get_dashboard_snapshot(
    top_n: int = Query(10, ge=1, le=50, description="Top N projects"),
    range_days: int = Query(14, description="Window size in days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get aggregated dashboard data with project-card aligned vulnerability metric."""
    range_days = _normalize_dashboard_range_days(range_days)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=int(range_days))

    projects_result = await db.execute(select(Project.id, Project.name, Project.source_type))
    project_rows = projects_result.all()
    project_name_map: Dict[str, str] = {
        str(project_id): str(project_name or "未知项目")
        for project_id, project_name, _source_type in project_rows
        if project_id
    }
    project_source_type_map: Dict[str, str] = {
        str(project_id): str(source_type or "")
        for project_id, _project_name, source_type in project_rows
        if project_id
    }
    management_metrics_result = await db.execute(
        select(
            ProjectManagementMetrics.project_id,
            ProjectManagementMetrics.status,
            ProjectManagementMetrics.critical,
            ProjectManagementMetrics.high,
            ProjectManagementMetrics.medium,
            ProjectManagementMetrics.low,
        )
    )
    management_metrics_rows = management_metrics_result.all()
    project_management_metrics_map: Dict[str, Dict[str, Any]] = {
        str(project_id): {
            "status": str(status or ""),
            "critical": _to_non_negative_int(critical),
            "high": _to_non_negative_int(high),
            "medium": _to_non_negative_int(medium),
            "low": _to_non_negative_int(low),
        }
        for project_id, status, critical, high, medium, low in management_metrics_rows
        if project_id
    }

    project_info_result = await db.execute(
        select(ProjectInfo.project_id, ProjectInfo.language_info, ProjectInfo.status)
    )
    project_info_rows = list(project_info_result.all())
    project_info_project_ids = {
        str(project_id or "")
        for project_id, _language_info, _status in project_info_rows
        if project_id
    }
    missing_project_info_ids = [
        project_id
        for project_id, source_type in project_source_type_map.items()
        if project_id
        and source_type == "zip"
        and project_id not in project_info_project_ids
    ]
    for project_id in missing_project_info_ids:
        project_info = await ensure_project_info_language_stats(
            db,
            project_id,
            raise_on_error=False,
        )
        project_info_rows.append(
            (
                project_info.project_id,
                project_info.language_info,
                project_info.status,
            )
        )

    project_dominant_language_map: Dict[str, str] = {}
    project_language_loc_map: Dict[str, Dict[str, int]] = {}
    language_project_sets: Dict[str, set[str]] = defaultdict(set)
    language_loc_totals: Dict[str, int] = defaultdict(int)
    for project_id, language_info, info_status in project_info_rows:
        normalized_project_id = str(project_id or "")
        if not normalized_project_id:
            continue
        if _normalize_status_token(info_status) != "completed":
            continue
        parsed_language_info = _parse_dashboard_language_info(language_info)
        if not parsed_language_info:
            continue
        project_language_loc_map[normalized_project_id] = {
            language: _to_non_negative_int(stats.get("loc_number"))
            for language, stats in parsed_language_info.items()
        }
        dominant_language = max(
            parsed_language_info.items(),
            key=lambda item: (
                _to_non_negative_int(item[1].get("loc_number")),
                _to_non_negative_int(item[1].get("files_count")),
                item[0],
            ),
        )[0]
        project_dominant_language_map[normalized_project_id] = dominant_language
        for language, stats in parsed_language_info.items():
            loc_number = _to_non_negative_int(stats.get("loc_number"))
            language_loc_totals[language] += loc_number
            language_project_sets[language].add(normalized_project_id)

    opengrep_result = await db.execute(
        select(
            OpengrepScanTask.id,
            OpengrepScanTask.project_id,
            OpengrepScanTask.status,
            OpengrepScanTask.name,
            OpengrepScanTask.scan_duration_ms,
            OpengrepScanTask.created_at,
        )
    )
    opengrep_rows = opengrep_result.all()
    opengrep_task_ids = [str(task_id) for task_id, *_ in opengrep_rows if task_id]
    high_confidence_counts = await count_high_confidence_findings_by_task_ids(
        db,
        opengrep_task_ids,
    )

    gitleaks_result = await db.execute(
        select(
            GitleaksScanTask.id,
            GitleaksScanTask.project_id,
            GitleaksScanTask.status,
            GitleaksScanTask.name,
            GitleaksScanTask.total_findings,
            GitleaksScanTask.scan_duration_ms,
            GitleaksScanTask.created_at,
        )
    )
    gitleaks_rows = gitleaks_result.all()

    bandit_result = await db.execute(
        select(
            BanditScanTask.id,
            BanditScanTask.project_id,
            BanditScanTask.status,
            BanditScanTask.name,
            BanditScanTask.high_count,
            BanditScanTask.medium_count,
            BanditScanTask.low_count,
            BanditScanTask.scan_duration_ms,
            BanditScanTask.created_at,
        )
    )
    bandit_rows = bandit_result.all()

    phpstan_result = await db.execute(
        select(
            PhpstanScanTask.id,
            PhpstanScanTask.project_id,
            PhpstanScanTask.status,
            PhpstanScanTask.name,
            PhpstanScanTask.total_findings,
            PhpstanScanTask.scan_duration_ms,
            PhpstanScanTask.created_at,
        )
    )
    phpstan_rows = phpstan_result.all()

    yasa_result = await db.execute(
        select(
            YasaScanTask.id,
            YasaScanTask.project_id,
            YasaScanTask.status,
            YasaScanTask.name,
            YasaScanTask.total_findings,
            YasaScanTask.scan_duration_ms,
            YasaScanTask.created_at,
        )
    )
    yasa_rows = yasa_result.all()

    agent_result = await db.execute(
        select(
            AgentTask.id,
            AgentTask.project_id,
            AgentTask.status,
            AgentTask.name,
            AgentTask.description,
            AgentTask.verified_count,
            AgentTask.tokens_used,
            AgentTask.started_at,
            AgentTask.completed_at,
            AgentTask.created_at,
        )
    )
    agent_rows = agent_result.all()

    rule_result = await db.execute(
        select(
            OpengrepRule.name,
            OpengrepRule.language,
            OpengrepRule.severity,
            OpengrepRule.confidence,
            OpengrepRule.is_active,
            OpengrepRule.cwe,
        ).where(OpengrepRule.severity == "ERROR")
    )
    rule_rows = rule_result.all()

    gitleaks_rule_result = await db.execute(select(GitleaksRule.id))
    gitleaks_rule_rows = gitleaks_rule_result.all()

    bandit_rule_result = await db.execute(select(BanditRuleState.test_id, BanditRuleState.is_deleted))
    bandit_rule_rows = bandit_rule_result.all()

    phpstan_rule_result = await db.execute(
        select(PhpstanRuleState.rule_id, PhpstanRuleState.is_deleted)
    )
    phpstan_rule_rows = phpstan_rule_result.all()

    opengrep_finding_result = await db.execute(
        select(
            OpengrepFinding.scan_task_id,
            OpengrepFinding.rule,
            OpengrepFinding.severity,
            OpengrepFinding.status,
            OpengrepFinding.file_path,
            OpengrepScanTask.created_at,
        )
        .join(OpengrepScanTask, OpengrepScanTask.id == OpengrepFinding.scan_task_id)
        .where(OpengrepFinding.scan_task_id.in_(opengrep_task_ids))
    )
    opengrep_finding_rows = opengrep_finding_result.all()

    gitleaks_finding_result = await db.execute(
        select(
            GitleaksFinding.scan_task_id,
            GitleaksFinding.status,
            GitleaksFinding.file_path,
            GitleaksFinding.created_at,
        )
    )
    gitleaks_finding_rows = gitleaks_finding_result.all()

    bandit_finding_result = await db.execute(
        select(
            BanditFinding.scan_task_id,
            BanditFinding.test_id,
            BanditFinding.issue_severity,
            BanditFinding.issue_text,
            BanditFinding.test_name,
            BanditFinding.issue_confidence,
            BanditFinding.status,
            BanditFinding.file_path,
            BanditFinding.created_at,
        )
    )
    bandit_finding_rows = bandit_finding_result.all()

    phpstan_finding_result = await db.execute(
        select(
            PhpstanFinding.scan_task_id,
            PhpstanFinding.status,
            PhpstanFinding.file_path,
            PhpstanFinding.created_at,
        )
    )
    phpstan_finding_rows = phpstan_finding_result.all()

    yasa_finding_result = await db.execute(
        select(
            YasaFinding.scan_task_id,
            YasaFinding.status,
            YasaFinding.level,
            YasaFinding.file_path,
            YasaFinding.created_at,
        )
    )
    yasa_finding_rows = yasa_finding_result.all()

    agent_finding_result = await db.execute(
        select(
            AgentFinding.task_id,
            AgentFinding.is_verified,
            AgentFinding.references,
            AgentFinding.vulnerability_type,
            AgentFinding.title,
            AgentFinding.description,
            AgentFinding.code_snippet,
            AgentFinding.ai_confidence,
            AgentFinding.confidence,
            AgentFinding.status,
            AgentFinding.verdict,
            AgentFinding.severity,
            AgentFinding.file_path,
            AgentFinding.created_at,
        )
    )
    agent_finding_rows = agent_finding_result.all()

    scan_runs_map: Dict[str, Dict[str, int]] = {}
    vulns_map: Dict[str, Dict[str, int]] = {}
    rule_confidence_buckets: Dict[str, Dict[str, int]] = {
        "HIGH": {"total_rules": 0, "enabled_rules": 0},
        "MEDIUM": {"total_rules": 0, "enabled_rules": 0},
        "LOW": {"total_rules": 0, "enabled_rules": 0},
        "UNSPECIFIED": {"total_rules": 0, "enabled_rules": 0},
    }
    rule_confidence_by_language: Dict[str, Dict[str, int]] = {}
    cwe_distribution_map: Dict[str, Dict[str, Any]] = {}
    verified_vulnerability_type_map: Dict[str, Dict[str, Any]] = {}
    task_status_breakdown = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "interrupted": 0,
        "cancelled": 0,
    }
    task_status_by_scan_type = _build_empty_task_status_by_scan_type()
    engine_metrics: Dict[str, Dict[str, int]] = {
        engine: {
            "completed_scans": 0,
            "effective_findings": 0,
            "verified_findings": 0,
            "false_positive_count": 0,
            "duration_total": 0,
            "duration_count": 0,
            "terminal_total": 0,
            "success_total": 0,
        }
        for engine in DASHBOARD_ENGINE_ORDER
    }
    activity_map: Dict[str, Dict[str, int]] = {}
    hotspots_map: Dict[str, Dict[str, Any]] = {}
    language_risk_map: Dict[str, Dict[str, int]] = {}
    opengrep_task_project_map: Dict[str, str] = {}
    gitleaks_task_project_map: Dict[str, str] = {}
    bandit_task_project_map: Dict[str, str] = {}
    phpstan_task_project_map: Dict[str, str] = {}
    yasa_task_project_map: Dict[str, str] = {}
    agent_task_project_map: Dict[str, str] = {}
    agent_task_source_mode_map: Dict[str, str] = {}
    recent_task_items: List[Dict[str, Any]] = []
    static_recent_task_records: List[Dict[str, Any]] = []
    window_scanned_projects: set[str] = set()
    all_counts = {"raw": 0, "effective": 0, "verified": 0, "false_positive": 0}
    window_counts = {"raw": 0, "effective": 0, "verified": 0, "false_positive": 0}
    success_totals = {"completed": 0, "terminal": 0}
    duration_totals = {"sum": 0, "count": 0, "window_sum": 0, "window_count": 0}
    total_model_tokens = 0

    def ensure_scan_runs(project_id: str) -> Dict[str, int]:
        existing = scan_runs_map.get(project_id)
        if existing is not None:
            return existing
        created = {
            "static_runs": 0,
            "intelligent_runs": 0,
            "hybrid_runs": 0,
        }
        scan_runs_map[project_id] = created
        return created

    def ensure_vulns(project_id: str) -> Dict[str, int]:
        existing = vulns_map.get(project_id)
        if existing is not None:
            return existing
        created = {
            "static_vulns": 0,
            "intelligent_vulns": 0,
            "hybrid_vulns": 0,
        }
        vulns_map[project_id] = created
        return created

    def ensure_hotspot(project_id: str) -> Dict[str, Any]:
        existing = hotspots_map.get(project_id)
        if existing is not None:
            return existing
        created = {
            "project_id": project_id,
            "project_name": project_name_map.get(project_id, "未知项目"),
            "risk_score": 0.0,
            "scan_runs_window": 0,
            "effective_findings": 0,
            "verified_findings": 0,
            "false_positive_count": 0,
            "raw_findings": 0,
            "dominant_language": project_dominant_language_map.get(project_id, "unknown"),
            "last_scan_at": None,
            "engine_effective_counts": {},
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
        }
        hotspots_map[project_id] = created
        return created

    def ensure_language_risk(language: str) -> Dict[str, int]:
        normalized_language = str(language or "").strip() or "unknown"
        existing = language_risk_map.get(normalized_language)
        if existing is not None:
            return existing
        created = {
            "effective_findings": 0,
            "verified_findings": 0,
            "false_positive_count": 0,
        }
        language_risk_map[normalized_language] = created
        return created

    def resolve_activity_field(engine: str) -> str:
        return "agent_findings" if engine == "llm" else f"{engine}_findings"

    def bucket_severity(severity: Any, engine: str) -> str:
        normalized = _normalize_status_token(severity)
        if engine == "opengrep":
            normalized = str(severity or "").strip().upper()
            if normalized == "ERROR":
                return "high"
            if normalized == "WARNING":
                return "medium"
            return "low"
        if engine == "gitleaks":
            return "high"
        if engine == "phpstan":
            return "medium"
        if engine == "yasa":
            if normalized in {"error", "high"}:
                return "high"
            if normalized in {"warning", "medium"}:
                return "medium"
            return "low"
        if normalized == "critical":
            return "critical"
        if normalized == "high":
            return "high"
        if normalized == "medium":
            return "medium"
        return "low"

    def register_project_risk_severity(project_id: str, bucket: str) -> None:
        hotspot = ensure_hotspot(project_id)
        key = f"{bucket}_count"
        hotspot[key] = _to_non_negative_int(hotspot.get(key, 0)) + 1

    def register_recent_task(
        *,
        task_id: Any,
        project_id: str,
        task_type: str,
        engine: str,
        status: Any,
        created_at: Any,
        detail_path: str,
    ) -> None:
        normalized_timestamp = _coerce_datetime(created_at)
        if not normalized_timestamp:
            return
        project_name = project_name_map.get(project_id, "未知项目")
        recent_task_items.append(
            {
                "task_id": str(task_id or ""),
                "task_type": task_type,
                "title": f"{task_type} · {project_name}",
                "engine": engine,
                "status": _normalize_status_token(status) or "running",
                "created_at": normalized_timestamp,
                "detail_path": detail_path,
            }
        )

    def register_task(
        engine: str,
        project_id: str,
        status: Any,
        timestamp: Optional[datetime],
        duration_ms: int,
        *,
        scan_type: str,
        include_in_task_breakdown: bool = True,
    ) -> None:
        hotspot = ensure_hotspot(project_id)
        _update_project_hotspot_scan_meta(
            hotspot,
            project_id,
            project_name_map,
            project_dominant_language_map,
            timestamp,
        )

        status_bucket = _bucket_dashboard_task_status(status)
        if include_in_task_breakdown:
            task_status_breakdown[status_bucket] = _to_non_negative_int(
                task_status_breakdown.get(status_bucket, 0)
            ) + 1
            if scan_type in DASHBOARD_SCAN_TYPE_KEYS:
                task_status_by_scan_type[status_bucket][scan_type] = _to_non_negative_int(
                    task_status_by_scan_type.get(status_bucket, {}).get(scan_type, 0)
                ) + 1

        if status_bucket == "completed":
            success_totals["completed"] += 1
            duration_totals["sum"] += duration_ms
            duration_totals["count"] += 1
            normalized_timestamp = _coerce_datetime(timestamp)
            if normalized_timestamp is not None and normalized_timestamp >= window_start:
                window_scanned_projects.add(project_id)
                hotspot["scan_runs_window"] = _to_non_negative_int(
                    hotspot.get("scan_runs_window", 0)
                ) + 1
                engine_metrics[engine]["completed_scans"] += 1
                engine_metrics[engine]["duration_total"] += duration_ms
                engine_metrics[engine]["duration_count"] += 1
                duration_totals["window_sum"] += duration_ms
                duration_totals["window_count"] += 1
                _update_window_activity(activity_map, normalized_timestamp, window_start, "completed_scans")

    def ensure_activity_bucket(timestamp: Optional[datetime]) -> Optional[Dict[str, int]]:
        normalized = _coerce_datetime(timestamp)
        if normalized is None or normalized < window_start:
            return None
        return activity_map.setdefault(
            _dashboard_activity_bucket(normalized),
            {
                "completed_scans": 0,
                "agent_findings": 0,
                "opengrep_findings": 0,
                "gitleaks_findings": 0,
                "bandit_findings": 0,
                "phpstan_findings": 0,
                "yasa_findings": 0,
                "static_findings": 0,
                "intelligent_verified_findings": 0,
                "hybrid_verified_findings": 0,
                "total_new_findings": 0,
            },
        )

        if status_bucket in {"completed", "failed", "interrupted", "cancelled"}:
            success_totals["terminal"] += 1
            normalized_timestamp = _coerce_datetime(timestamp)
            if normalized_timestamp is not None and normalized_timestamp >= window_start:
                engine_metrics[engine]["terminal_total"] += 1
                if status_bucket == "completed":
                    engine_metrics[engine]["success_total"] += 1

    def register_finding(
        *,
        project_id: str,
        engine: str,
        effective: bool,
        verified: bool,
        false_positive: bool,
        risk_weight: float,
        timestamp: Optional[datetime],
        file_path: Any,
    ) -> None:
        hotspot = ensure_hotspot(project_id)
        _record_project_hotspot_finding(
            hotspot,
            engine=engine,
            effective=effective,
            verified=verified,
            false_positive=false_positive,
            risk_weight=risk_weight,
        )

        all_counts["raw"] += 1
        if effective:
            all_counts["effective"] += 1
        if verified:
            all_counts["verified"] += 1
        if false_positive:
            all_counts["false_positive"] += 1

        finding_language = _resolve_dashboard_language_from_path(
            file_path,
            hotspot.get("dominant_language") or "unknown",
        )
        language_bucket = ensure_language_risk(finding_language)
        if effective:
            language_bucket["effective_findings"] += 1
        if verified:
            language_bucket["verified_findings"] += 1
        if false_positive:
            language_bucket["false_positive_count"] += 1

        normalized_timestamp = _coerce_datetime(timestamp)
        if normalized_timestamp is None or normalized_timestamp < window_start:
            return

        window_counts["raw"] += 1
        if effective:
            window_counts["effective"] += 1
            engine_metrics[engine]["effective_findings"] += 1
            _update_window_activity(
                activity_map,
                normalized_timestamp,
                window_start,
                resolve_activity_field(engine),
            )
        if verified:
            window_counts["verified"] += 1
            engine_metrics[engine]["verified_findings"] += 1
        if false_positive:
            window_counts["false_positive"] += 1
            engine_metrics[engine]["false_positive_count"] += 1

    opengrep_duration_ms = 0
    for task_id, project_id, status, name, scan_duration_ms, created_at in opengrep_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        duration_ms = _to_non_negative_int(scan_duration_ms)
        task_timestamp = _coerce_datetime(created_at)
        if normalized_task_id:
            opengrep_task_project_map[normalized_task_id] = normalized_project_id
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(
            high_confidence_counts.get(normalized_task_id, 0)
        )
        if _normalize_status_token(status) == "completed":
            ensure_scan_runs(normalized_project_id)["static_runs"] += 1
        opengrep_duration_ms += duration_ms
        register_task(
            "opengrep",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="static",
            include_in_task_breakdown=False,
        )
        static_recent_task_records.append(
            {
                "task_id": normalized_task_id,
                "project_id": normalized_project_id,
                "engine": "opengrep",
                "status": status,
                "created_at": created_at,
                "name": name,
            }
        )

    gitleaks_duration_ms = 0
    for (
        task_id,
        project_id,
        status,
        name,
        total_findings,
        scan_duration_ms,
        created_at,
    ) in gitleaks_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        duration_ms = _to_non_negative_int(scan_duration_ms)
        task_timestamp = _coerce_datetime(created_at)
        if normalized_task_id:
            gitleaks_task_project_map[normalized_task_id] = normalized_project_id
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(total_findings)
        if _normalize_status_token(status) == "completed":
            ensure_scan_runs(normalized_project_id)["static_runs"] += 1
        gitleaks_duration_ms += duration_ms
        register_task(
            "gitleaks",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="static",
            include_in_task_breakdown=False,
        )
        static_recent_task_records.append(
            {
                "task_id": normalized_task_id,
                "project_id": normalized_project_id,
                "engine": "gitleaks",
                "status": status,
                "created_at": created_at,
                "name": name,
            }
        )

    bandit_duration_ms = 0
    for (
        task_id,
        project_id,
        status,
        name,
        high_count,
        medium_count,
        low_count,
        scan_duration_ms,
        created_at,
    ) in bandit_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        duration_ms = _to_non_negative_int(scan_duration_ms)
        task_timestamp = _coerce_datetime(created_at)
        if normalized_task_id:
            bandit_task_project_map[normalized_task_id] = normalized_project_id
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += (
            _to_non_negative_int(high_count)
            + _to_non_negative_int(medium_count)
            + _to_non_negative_int(low_count)
        )
        if _normalize_status_token(status) == "completed":
            ensure_scan_runs(normalized_project_id)["static_runs"] += 1
        bandit_duration_ms += duration_ms
        register_task(
            "bandit",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="static",
            include_in_task_breakdown=False,
        )
        static_recent_task_records.append(
            {
                "task_id": normalized_task_id,
                "project_id": normalized_project_id,
                "engine": "bandit",
                "status": status,
                "created_at": created_at,
                "name": name,
            }
        )

    phpstan_duration_ms = 0
    for (
        task_id,
        project_id,
        status,
        name,
        total_findings,
        scan_duration_ms,
        created_at,
    ) in phpstan_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        duration_ms = _to_non_negative_int(scan_duration_ms)
        task_timestamp = _coerce_datetime(created_at)
        if normalized_task_id:
            phpstan_task_project_map[normalized_task_id] = normalized_project_id
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(total_findings)
        if _normalize_status_token(status) == "completed":
            ensure_scan_runs(normalized_project_id)["static_runs"] += 1
        phpstan_duration_ms += duration_ms
        register_task(
            "phpstan",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="static",
            include_in_task_breakdown=False,
        )
        static_recent_task_records.append(
            {
                "task_id": normalized_task_id,
                "project_id": normalized_project_id,
                "engine": "phpstan",
                "status": status,
                "created_at": created_at,
                "name": name,
            }
        )

    yasa_duration_ms = 0
    for (
        task_id,
        project_id,
        status,
        name,
        total_findings,
        scan_duration_ms,
        created_at,
    ) in yasa_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        duration_ms = _to_non_negative_int(scan_duration_ms)
        task_timestamp = _coerce_datetime(created_at)
        if normalized_task_id:
            yasa_task_project_map[normalized_task_id] = normalized_project_id
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(total_findings)
        if _normalize_status_token(status) == "completed":
            ensure_scan_runs(normalized_project_id)["static_runs"] += 1
        yasa_duration_ms += duration_ms
        register_task(
            "yasa",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="static",
            include_in_task_breakdown=False,
        )
        static_recent_task_records.append(
            {
                "task_id": normalized_task_id,
                "project_id": normalized_project_id,
                "engine": "yasa",
                "status": status,
                "created_at": created_at,
                "name": name,
            }
        )

    agent_duration_ms = 0
    for (
        task_id,
        project_id,
        status,
        name,
        description,
        verified_count,
        tokens_used,
        started_at,
        completed_at,
        created_at,
    ) in agent_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        normalized_task_id = str(task_id or "")
        task_timestamp = _coerce_datetime(completed_at) or _coerce_datetime(created_at)
        source_mode = _resolve_agent_source_mode(name, description)
        if normalized_task_id:
            agent_task_project_map[normalized_task_id] = normalized_project_id
            agent_task_source_mode_map[normalized_task_id] = source_mode
        total_model_tokens += _to_non_negative_int(tokens_used)
        verified = _to_non_negative_int(verified_count)
        project_vulns = ensure_vulns(normalized_project_id)
        if source_mode == "intelligent":
            project_vulns["intelligent_vulns"] += verified
        else:
            project_vulns["hybrid_vulns"] += verified
        if _normalize_status_token(status) == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            if source_mode == "intelligent":
                project_scan_runs["intelligent_runs"] += 1
            else:
                project_scan_runs["hybrid_runs"] += 1
        duration_ms = 0
        if started_at is not None and completed_at is not None:
            duration_ms = _to_non_negative_int(
                (_coerce_datetime(completed_at) - _coerce_datetime(started_at)).total_seconds() * 1000
            )
            agent_duration_ms += duration_ms
        register_task(
            "llm",
            normalized_project_id,
            status,
            task_timestamp,
            duration_ms,
            scan_type="intelligent" if source_mode == "intelligent" else "hybrid",
        )
        register_recent_task(
            task_id=task_id,
            project_id=normalized_project_id,
            task_type="智能扫描" if source_mode == "intelligent" else "混合扫描",
            engine="llm",
            status=status,
            created_at=created_at,
            detail_path=f"/agent-audit/{normalized_task_id}",
        )

    static_recent_tasks = _build_dashboard_static_recent_tasks(
        static_recent_task_records,
        project_name_map,
    )
    for item in static_recent_tasks:
        status_bucket = _bucket_dashboard_task_status(item.get("status"))
        task_status_breakdown[status_bucket] = _to_non_negative_int(
            task_status_breakdown.get(status_bucket, 0)
        ) + 1
        task_status_by_scan_type[status_bucket]["static"] = _to_non_negative_int(
            task_status_by_scan_type.get(status_bucket, {}).get("static", 0)
        ) + 1
    recent_task_items.extend(static_recent_tasks)

    severe_rule_rows: List[tuple[Any, Any, Any, Any, Any, Any]] = [
        row for row in rule_rows if str(row[2] or "").strip().upper() == "ERROR"
    ]
    rule_confidence_map = build_rule_confidence_map(
        [(row[0], row[3]) for row in severe_rule_rows]
    )
    rule_cwe_map: Dict[str, List[str]] = {}
    for rule_name, language, _, confidence, is_active, cwe_list in severe_rule_rows:
        bucket_key = _normalize_dashboard_rule_confidence(confidence)
        rule_confidence_buckets[bucket_key]["total_rules"] += 1
        if bool(is_active):
            rule_confidence_buckets[bucket_key]["enabled_rules"] += 1

        normalized_language = str(language or "").strip() or "unknown"
        language_bucket = rule_confidence_by_language.setdefault(
            normalized_language,
            {"high_count": 0, "medium_count": 0},
        )
        if bucket_key == "HIGH":
            language_bucket["high_count"] += 1
        elif bucket_key == "MEDIUM":
            language_bucket["medium_count"] += 1

        normalized_cwe_values: List[str] = []
        for raw_cwe in cwe_list if isinstance(cwe_list, list) else []:
            normalized_cwe = normalize_cwe_id(raw_cwe)
            if normalized_cwe and normalized_cwe not in normalized_cwe_values:
                normalized_cwe_values.append(normalized_cwe)

        for lookup_key in extract_rule_lookup_keys(rule_name):
            if lookup_key not in rule_cwe_map:
                rule_cwe_map[lookup_key] = normalized_cwe_values

    for scan_task_id, rule_data, severity, status, file_path, created_at in opengrep_finding_rows:
        project_id = opengrep_task_project_map.get(str(scan_task_id or ""))
        if not project_id:
            continue
        normalized_status = _normalize_status_token(status)
        is_false_positive = _is_static_finding_false_positive(normalized_status)
        is_verified = _is_static_finding_verified(normalized_status)
        is_effective = _is_static_finding_effective(normalized_status)
        register_finding(
            project_id=project_id,
            engine="opengrep",
            effective=is_effective,
            verified=is_verified,
            false_positive=is_false_positive,
            risk_weight=float(_risk_weight_for_opengrep(severity)) * _risk_multiplier(is_verified),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(severity, "opengrep"),
            )

        if not is_effective:
            continue

        resolved_confidence = extract_finding_payload_confidence(rule_data)
        check_id = None
        if isinstance(rule_data, dict):
            check_id = rule_data.get("check_id") or rule_data.get("id")
        if not resolved_confidence:
            for lookup_key in extract_rule_lookup_keys(check_id):
                mapped_confidence = rule_confidence_map.get(lookup_key)
                if mapped_confidence:
                    resolved_confidence = mapped_confidence
                    break
        if resolved_confidence not in {"HIGH", "MEDIUM"}:
            continue

        normalized_cwe_values = _extract_cwe_candidates_from_rule_payload(rule_data)
        if not normalized_cwe_values:
            for lookup_key in extract_rule_lookup_keys(check_id):
                fallback_cwe_values = rule_cwe_map.get(lookup_key) or []
                if fallback_cwe_values:
                    normalized_cwe_values = fallback_cwe_values
                    break
        if not normalized_cwe_values:
            continue

        for cwe_id in normalized_cwe_values:
            bucket = cwe_distribution_map.setdefault(
                cwe_id,
                {
                    "cwe_id": cwe_id,
                    "cwe_name": cwe_id,
                    "total_findings": 0,
                    "opengrep_findings": 0,
                    "agent_findings": 0,
                    "bandit_findings": 0,
                },
            )
            bucket["total_findings"] += 1
            bucket["opengrep_findings"] += 1

    for scan_task_id, status, file_path, created_at in gitleaks_finding_rows:
        project_id = gitleaks_task_project_map.get(str(scan_task_id or ""))
        if not project_id:
            continue
        normalized_status = _normalize_status_token(status)
        is_false_positive = _is_static_finding_false_positive(normalized_status)
        is_verified = _is_static_finding_verified(normalized_status)
        is_effective = _is_static_finding_effective(normalized_status)
        register_finding(
            project_id=project_id,
            engine="gitleaks",
            effective=is_effective,
            verified=is_verified,
            false_positive=is_false_positive,
            risk_weight=5.0 * _risk_multiplier(is_verified),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(None, "gitleaks"),
            )

    for (
        scan_task_id,
        test_id,
        issue_severity,
        issue_text,
        test_name,
        issue_confidence,
        status,
        file_path,
        created_at,
    ) in bandit_finding_rows:
        project_id = bandit_task_project_map.get(str(scan_task_id or ""))
        if not project_id:
            continue
        normalized_status = _normalize_status_token(status)
        is_false_positive = _is_static_finding_false_positive(normalized_status)
        is_verified = _is_static_finding_verified(normalized_status)
        is_effective = _is_static_finding_effective(normalized_status)
        register_finding(
            project_id=project_id,
            engine="bandit",
            effective=is_effective,
            verified=is_verified,
            false_positive=is_false_positive,
            risk_weight=float(_risk_weight_from_severity(issue_severity)) * _risk_multiplier(is_verified),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(issue_severity, "bandit"),
            )

        if not is_effective:
            continue

        normalized_confidence = normalize_opengrep_confidence(issue_confidence)
        if normalized_confidence not in {"HIGH", "MEDIUM"}:
            continue
        cwe_id = _BANDIT_TEST_ID_TO_CWE.get(str(test_id or "").strip().upper())
        if not cwe_id:
            continue
        bucket = cwe_distribution_map.setdefault(
            cwe_id,
            {
                "cwe_id": cwe_id,
                "cwe_name": cwe_id,
                "total_findings": 0,
                "opengrep_findings": 0,
                "agent_findings": 0,
                "bandit_findings": 0,
            },
        )
        bucket["total_findings"] += 1
        bucket["bandit_findings"] += 1

    for scan_task_id, status, file_path, created_at in phpstan_finding_rows:
        project_id = phpstan_task_project_map.get(str(scan_task_id or ""))
        if not project_id:
            continue
        normalized_status = _normalize_status_token(status)
        is_false_positive = _is_static_finding_false_positive(normalized_status)
        is_verified = _is_static_finding_verified(normalized_status)
        is_effective = _is_static_finding_effective(normalized_status)
        register_finding(
            project_id=project_id,
            engine="phpstan",
            effective=is_effective,
            verified=is_verified,
            false_positive=is_false_positive,
            risk_weight=1.0 * _risk_multiplier(is_verified),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(None, "phpstan"),
            )

    for scan_task_id, status, level, file_path, created_at in yasa_finding_rows:
        project_id = yasa_task_project_map.get(str(scan_task_id or ""))
        if not project_id:
            continue
        normalized_status = _normalize_status_token(status)
        is_false_positive = _is_static_finding_false_positive(normalized_status)
        is_verified = _is_static_finding_verified(normalized_status)
        is_effective = _is_static_finding_effective(normalized_status)
        register_finding(
            project_id=project_id,
            engine="yasa",
            effective=is_effective,
            verified=is_verified,
            false_positive=is_false_positive,
            risk_weight=float(_risk_weight_from_severity(level)) * _risk_multiplier(is_verified),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(level, "yasa"),
            )

    for (
        task_id,
        is_verified,
        references,
        vulnerability_type,
        title,
        description,
        code_snippet,
        ai_confidence,
        confidence,
        status,
        verdict,
        severity,
        file_path,
        created_at,
    ) in agent_finding_rows:
        project_id = agent_task_project_map.get(str(task_id or ""))
        if not project_id:
            continue
        source_mode = agent_task_source_mode_map.get(str(task_id or ""), "hybrid")
        is_false_positive = _is_agent_finding_false_positive(status, verdict)
        verified_flag = _is_agent_finding_verified(is_verified, status, verdict)
        is_effective = _is_agent_finding_effective(status, verdict)
        register_finding(
            project_id=project_id,
            engine="llm",
            effective=is_effective,
            verified=verified_flag,
            false_positive=is_false_positive,
            risk_weight=float(_risk_weight_from_severity(severity)) * _risk_multiplier(verified_flag),
            timestamp=_coerce_datetime(created_at),
            file_path=file_path,
        )
        if is_effective:
            register_project_risk_severity(
                project_id,
                bucket_severity(severity, "llm"),
            )

        if not verified_flag or not is_effective:
            continue
        activity_bucket = ensure_activity_bucket(_coerce_datetime(created_at))
        if activity_bucket is not None:
            field_name = (
                "intelligent_verified_findings"
                if source_mode == "intelligent"
                else "hybrid_verified_findings"
            )
            activity_bucket[field_name] = _to_non_negative_int(
                activity_bucket.get(field_name, 0)
            ) + 1
        normalized_confidence = _normalize_agent_confidence(
            ai_confidence if ai_confidence is not None else confidence
        )
        if normalized_confidence not in {"HIGH", "MEDIUM"}:
            continue
        cwe_id = normalize_cwe_id(references)
        if not cwe_id:
            continue
        profile = resolve_vulnerability_profile(
            vulnerability_type,
            title=title,
            description=description,
            code_snippet=code_snippet,
        )
        cwe_name = str(profile.get("name") or cwe_id).strip() or cwe_id
        bucket = cwe_distribution_map.setdefault(
            cwe_id,
            {
                "cwe_id": cwe_id,
                "cwe_name": cwe_name,
                "total_findings": 0,
                "opengrep_findings": 0,
                "agent_findings": 0,
                "bandit_findings": 0,
            },
        )
        if bucket.get("cwe_name") == bucket.get("cwe_id") and cwe_name != cwe_id:
            bucket["cwe_name"] = cwe_name
        bucket["total_findings"] += 1
        bucket["agent_findings"] += 1
        type_bucket = verified_vulnerability_type_map.setdefault(
            cwe_id,
            {
                "type_code": cwe_id,
                "type_name": cwe_name,
                "verified_count": 0,
            },
        )
        if type_bucket.get("type_name") == type_bucket.get("type_code") and cwe_name != cwe_id:
            type_bucket["type_name"] = cwe_name
        type_bucket["verified_count"] += 1

    scan_runs_items: List[Dict[str, Any]] = []
    for project_id, item in scan_runs_map.items():
        total_runs = (
            _to_non_negative_int(item.get("static_runs", 0))
            + _to_non_negative_int(item.get("intelligent_runs", 0))
            + _to_non_negative_int(item.get("hybrid_runs", 0))
        )
        if total_runs <= 0:
            continue
        scan_runs_items.append(
            {
                "project_id": project_id,
                "project_name": project_name_map.get(project_id, "未知项目"),
                "static_runs": _to_non_negative_int(item.get("static_runs", 0)),
                "intelligent_runs": _to_non_negative_int(item.get("intelligent_runs", 0)),
                "hybrid_runs": _to_non_negative_int(item.get("hybrid_runs", 0)),
                "total_runs": total_runs,
            }
        )

    vulns_items: List[Dict[str, Any]] = []
    for project_id, item in vulns_map.items():
        total_vulns = (
            _to_non_negative_int(item.get("static_vulns", 0))
            + _to_non_negative_int(item.get("intelligent_vulns", 0))
            + _to_non_negative_int(item.get("hybrid_vulns", 0))
        )
        if total_vulns <= 0:
            continue
        vulns_items.append(
            {
                "project_id": project_id,
                "project_name": project_name_map.get(project_id, "未知项目"),
                "static_vulns": _to_non_negative_int(item.get("static_vulns", 0)),
                "intelligent_vulns": _to_non_negative_int(item.get("intelligent_vulns", 0)),
                "hybrid_vulns": _to_non_negative_int(item.get("hybrid_vulns", 0)),
                "total_vulns": total_vulns,
            }
        )

    sorted_scan_runs = _sort_dashboard_items_by_total_and_name(
        scan_runs_items,
        total_key="total_runs",
    )[:top_n]
    sorted_vulns = _sort_dashboard_items_by_total_and_name(
        vulns_items,
        total_key="total_vulns",
    )[:top_n]

    total_scan_duration_ms = max(
        opengrep_duration_ms
        + gitleaks_duration_ms
        + bandit_duration_ms
        + phpstan_duration_ms
        + yasa_duration_ms
        + agent_duration_ms,
        0,
    )

    sorted_cwe_distribution = sorted(
        cwe_distribution_map.values(),
        key=lambda item: (
            -_to_non_negative_int(item.get("total_findings", 0)),
            str(item.get("cwe_id") or ""),
        ),
    )[:12]
    sorted_rule_confidence_by_language = sorted(
        (
            {
                "language": language,
                "high_count": _to_non_negative_int(item.get("high_count", 0)),
                "medium_count": _to_non_negative_int(item.get("medium_count", 0)),
            }
            for language, item in rule_confidence_by_language.items()
            if _to_non_negative_int(item.get("high_count", 0))
            + _to_non_negative_int(item.get("medium_count", 0))
            > 0
        ),
        key=lambda item: (
            -(
                _to_non_negative_int(item.get("high_count", 0))
                + _to_non_negative_int(item.get("medium_count", 0))
            ),
            str(item.get("language") or ""),
        ),
    )

    daily_activity = []
    for date, activity in sorted(activity_map.items(), key=lambda item: item[0]):
        activity_payload = dict(activity)
        static_findings = (
            _to_non_negative_int(activity_payload.get("opengrep_findings", 0))
            + _to_non_negative_int(activity_payload.get("gitleaks_findings", 0))
            + _to_non_negative_int(activity_payload.get("bandit_findings", 0))
            + _to_non_negative_int(activity_payload.get("phpstan_findings", 0))
            + _to_non_negative_int(activity_payload.get("yasa_findings", 0))
        )
        intelligent_verified_findings = _to_non_negative_int(
            activity_payload.pop("intelligent_verified_findings", 0)
        )
        hybrid_verified_findings = _to_non_negative_int(
            activity_payload.pop("hybrid_verified_findings", 0)
        )
        activity_payload.pop("static_findings", None)
        activity_payload.pop("total_new_findings", None)
        daily_activity.append(
            DashboardDailyActivityItem(
                date=date,
                **activity_payload,
                static_findings=static_findings,
                intelligent_verified_findings=intelligent_verified_findings,
                hybrid_verified_findings=hybrid_verified_findings,
                total_new_findings=(
                    static_findings
                    + intelligent_verified_findings
                    + hybrid_verified_findings
                ),
            )
        )

    engine_breakdown = [
        DashboardEngineBreakdownItem(
            engine=engine,  # type: ignore[arg-type]
            completed_scans=_to_non_negative_int(engine_metrics[engine]["completed_scans"]),
            effective_findings=_to_non_negative_int(engine_metrics[engine]["effective_findings"]),
            verified_findings=_to_non_negative_int(engine_metrics[engine]["verified_findings"]),
            false_positive_count=_to_non_negative_int(engine_metrics[engine]["false_positive_count"]),
            avg_scan_duration_ms=_round_non_negative_int(
                engine_metrics[engine]["duration_total"] / engine_metrics[engine]["duration_count"]
            )
            if engine_metrics[engine]["duration_count"] > 0
            else 0,
            success_rate=_to_ratio(
                engine_metrics[engine]["success_total"],
                engine_metrics[engine]["terminal_total"],
            ),
        )
        for engine in DASHBOARD_ENGINE_ORDER
    ]

    language_risk_items = []
    for language, counts in language_risk_map.items():
        loc_number = _to_non_negative_int(language_loc_totals.get(language, 0))
        findings_per_kloc = 0.0
        if loc_number > 0:
            findings_per_kloc = round(
                (_to_non_negative_int(counts.get("effective_findings", 0)) * 1000.0) / float(loc_number),
                2,
            )
        language_risk_items.append(
            {
                "language": language,
                "project_count": len(language_project_sets.get(language, set())),
                "loc_number": loc_number,
                "effective_findings": _to_non_negative_int(counts.get("effective_findings", 0)),
                "verified_findings": _to_non_negative_int(counts.get("verified_findings", 0)),
                "false_positive_count": _to_non_negative_int(counts.get("false_positive_count", 0)),
                "findings_per_kloc": findings_per_kloc,
                "rules_high": _to_non_negative_int(
                    rule_confidence_by_language.get(language, {}).get("high_count", 0)
                ),
                "rules_medium": _to_non_negative_int(
                    rule_confidence_by_language.get(language, {}).get("medium_count", 0)
                ),
            }
        )

    sorted_language_risk = sorted(
        language_risk_items,
        key=lambda item: (
            -_to_non_negative_int(item.get("effective_findings", 0)),
            -_to_non_negative_int(item.get("verified_findings", 0)),
            -_to_non_negative_int(item.get("rules_high", 0)),
            -_to_non_negative_int(item.get("rules_medium", 0)),
            str(item.get("language") or ""),
        ),
    )[:12]

    hotspot_items = []
    for project_id, hotspot in hotspots_map.items():
        risk_score = float(hotspot.get("risk_score", 0.0))
        if risk_score <= 0:
            continue
        engine_effective_counts = hotspot.get("engine_effective_counts", {})
        top_engine = next(
            (
                engine
                for engine in DASHBOARD_ENGINE_ORDER
                if _to_non_negative_int(engine_effective_counts.get(engine, 0)) > 0
            ),
            "llm",
        )
        hotspot_items.append(
            DashboardProjectHotspotItem(
                project_id=project_id,
                project_name=str(hotspot.get("project_name") or "未知项目"),
                risk_score=round(risk_score, 2),
                scan_runs_window=_to_non_negative_int(hotspot.get("scan_runs_window", 0)),
                effective_findings=_to_non_negative_int(hotspot.get("effective_findings", 0)),
                verified_findings=_to_non_negative_int(hotspot.get("verified_findings", 0)),
                false_positive_rate=_to_ratio(
                    _to_non_negative_int(hotspot.get("false_positive_count", 0)),
                    _to_non_negative_int(hotspot.get("raw_findings", 0)),
                ),
                dominant_language=str(hotspot.get("dominant_language") or "unknown"),
                last_scan_at=_coerce_datetime(hotspot.get("last_scan_at")),
                top_engine=top_engine,
            )
        )

    sorted_hotspots = sorted(
        hotspot_items,
        key=lambda item: (
            -float(item.risk_score),
            -int(item.verified_findings),
            -(item.last_scan_at.timestamp() if item.last_scan_at else 0.0),
            item.project_name,
        ),
    )[:top_n]

    sorted_recent_tasks = sorted(
        recent_task_items,
        key=lambda item: (
            -(item["created_at"].timestamp() if item.get("created_at") else 0.0),
            item["task_id"],
        ),
    )

    project_risk_distribution = [
        DashboardProjectRiskDistributionItem(
            project_id=project_id,
            project_name=project_name_map.get(project_id, "未知项目"),
            critical_count=_to_non_negative_int(metrics.get("critical", 0)),
            high_count=_to_non_negative_int(metrics.get("high", 0)),
            medium_count=_to_non_negative_int(metrics.get("medium", 0)),
            low_count=_to_non_negative_int(metrics.get("low", 0)),
            total_findings=(
                _to_non_negative_int(metrics.get("critical", 0))
                + _to_non_negative_int(metrics.get("high", 0))
                + _to_non_negative_int(metrics.get("medium", 0))
                + _to_non_negative_int(metrics.get("low", 0))
            ),
        )
        for project_id, metrics in sorted(
            (
                (
                    project_id,
                    metrics,
                )
                for project_id, metrics in project_management_metrics_map.items()
                if _normalize_status_token(metrics.get("status")) == "ready"
                and (
                    _to_non_negative_int(metrics.get("critical", 0))
                    + _to_non_negative_int(metrics.get("high", 0))
                    + _to_non_negative_int(metrics.get("medium", 0))
                    + _to_non_negative_int(metrics.get("low", 0))
                )
                > 0
            ),
            key=lambda item: (
                -(
                    _to_non_negative_int(item[1].get("critical", 0))
                    + _to_non_negative_int(item[1].get("high", 0))
                    + _to_non_negative_int(item[1].get("medium", 0))
                    + _to_non_negative_int(item[1].get("low", 0))
                ),
                project_name_map.get(item[0], "未知项目"),
            ),
        )[:top_n]
    ]

    verified_vulnerability_types = [
        DashboardVerifiedVulnerabilityTypeItem(**item)
        for item in sorted(
            verified_vulnerability_type_map.values(),
            key=lambda item: (
                -_to_non_negative_int(item.get("verified_count", 0)),
                str(item.get("type_code") or ""),
            ),
        )[:top_n]
    ]

    bandit_rule_total = _count_snapshot_rules_with_deleted_states(
        _extract_bandit_snapshot_rules(),
        bandit_rule_rows,
        rule_id_key="test_id",
        normalize_rule_id=lambda value: str(value or "").strip().upper(),
    )
    phpstan_rule_total = _count_snapshot_rules_with_deleted_states(
        _extract_phpstan_snapshot_rules(),
        phpstan_rule_rows,
        rule_id_key="id",
    )
    yasa_rule_total = await _get_yasa_rule_total(db)
    static_engine_rule_totals = [
        DashboardStaticEngineRuleTotalItem(engine="opengrep", total_rules=len(severe_rule_rows)),
        DashboardStaticEngineRuleTotalItem(engine="gitleaks", total_rules=len(gitleaks_rule_rows)),
        DashboardStaticEngineRuleTotalItem(engine="bandit", total_rules=bandit_rule_total),
        DashboardStaticEngineRuleTotalItem(engine="phpstan", total_rules=phpstan_rule_total),
        DashboardStaticEngineRuleTotalItem(engine="yasa", total_rules=_to_non_negative_int(yasa_rule_total)),
    ]

    language_loc_distribution = [
        DashboardLanguageLocItem(
            language=language,
            loc_number=_to_non_negative_int(loc_number),
            project_count=len(language_project_sets.get(language, set())),
        )
        for language, loc_number in sorted(
            language_loc_totals.items(),
            key=lambda item: (-_to_non_negative_int(item[1]), item[0]),
        )[:10]
    ]

    return DashboardSnapshotResponse(
        generated_at=now,
        total_scan_duration_ms=total_scan_duration_ms,
        scan_runs=[DashboardScanRunsItem(**item) for item in sorted_scan_runs],
        vulns=[DashboardVulnsItem(**item) for item in sorted_vulns],
        rule_confidence=[
            DashboardRuleConfidenceItem(
                confidence=confidence,
                total_rules=_to_non_negative_int(rule_confidence_buckets[confidence]["total_rules"]),
                enabled_rules=_to_non_negative_int(rule_confidence_buckets[confidence]["enabled_rules"]),
            )
            for confidence in ("HIGH", "MEDIUM", "LOW", "UNSPECIFIED")
        ],
        rule_confidence_by_language=[
            DashboardRuleConfidenceByLanguageItem(**item)
            for item in sorted_rule_confidence_by_language
        ],
        cwe_distribution=[
            DashboardCweDistributionItem(**item)
            for item in sorted_cwe_distribution
        ],
        summary=DashboardSummaryItem(
            total_projects=len(project_name_map),
            current_effective_findings=all_counts["effective"],
            current_verified_findings=all_counts["verified"],
            total_model_tokens=total_model_tokens,
            false_positive_rate=_to_ratio(all_counts["false_positive"], all_counts["raw"]),
            scan_success_rate=_to_ratio(success_totals["completed"], success_totals["terminal"]),
            avg_scan_duration_ms=_round_non_negative_int(
                duration_totals["sum"] / duration_totals["count"]
            )
            if duration_totals["count"] > 0
            else 0,
            window_scanned_projects=len(window_scanned_projects),
            window_new_effective_findings=window_counts["effective"],
            window_verified_findings=window_counts["verified"],
            window_false_positive_rate=_to_ratio(
                window_counts["false_positive"],
                window_counts["raw"],
            ),
            window_scan_success_rate=_to_ratio(
                sum(item["success_total"] for item in engine_metrics.values()),
                sum(item["terminal_total"] for item in engine_metrics.values()),
            ),
            window_avg_scan_duration_ms=_round_non_negative_int(
                duration_totals["window_sum"] / duration_totals["window_count"]
            )
            if duration_totals["window_count"] > 0
            else 0,
        ),
        daily_activity=daily_activity,
        verification_funnel=DashboardVerificationFunnelItem(
            raw_findings=window_counts["raw"],
            effective_findings=window_counts["effective"],
            verified_findings=window_counts["verified"],
            false_positive_count=window_counts["false_positive"],
        ),
        task_status_breakdown=DashboardTaskStatusBreakdownItem(**task_status_breakdown),
        task_status_by_scan_type=DashboardTaskStatusByScanTypeItem(
            **{
                status_key: DashboardTaskStatusScanTypeBreakdownItem(
                    **task_status_by_scan_type[status_key]
                )
                for status_key in DASHBOARD_TASK_STATUS_KEYS
            }
        ),
        engine_breakdown=engine_breakdown,
        project_hotspots=sorted_hotspots,
        language_risk=[
            DashboardLanguageRiskItem(**item)
            for item in sorted_language_risk
        ],
        recent_tasks=[
            DashboardRecentTaskItem(**item)
            for item in sorted_recent_tasks
        ],
        project_risk_distribution=project_risk_distribution,
        verified_vulnerability_types=verified_vulnerability_types,
        static_engine_rule_totals=static_engine_rule_totals,
        language_loc_distribution=language_loc_distribution,
    )


@router.get("/static-scan-overview", response_model=StaticScanOverviewResponse)
async def get_static_scan_overview(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(6, ge=1, le=50, description="每页数量"),
    keyword: Optional[str] = Query(
        None,
        description="按项目名称模糊搜索（大小写不敏感）",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目静态扫描概览（分页）。
    仅返回至少存在一次成功静态扫描（Opengrep/Gitleaks/Bandit/PHPStan）的项目。
    """
    opengrep_ranked_subquery = (
        select(
            OpengrepScanTask.project_id.label("project_id"),
            OpengrepScanTask.id.label("task_id"),
            OpengrepScanTask.created_at.label("created_at"),
            OpengrepScanTask.total_findings.label("total_findings"),
            OpengrepScanTask.error_count.label("error_count"),
            OpengrepScanTask.warning_count.label("warning_count"),
            func.row_number()
            .over(
                partition_by=OpengrepScanTask.project_id,
                order_by=OpengrepScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(OpengrepScanTask.status) == "completed")
        .subquery()
    )
    latest_opengrep_subquery = (
        select(
            opengrep_ranked_subquery.c.project_id,
            opengrep_ranked_subquery.c.task_id,
            opengrep_ranked_subquery.c.created_at,
            opengrep_ranked_subquery.c.total_findings,
            opengrep_ranked_subquery.c.error_count,
            opengrep_ranked_subquery.c.warning_count,
        )
        .where(opengrep_ranked_subquery.c.rn == 1)
        .subquery()
    )

    gitleaks_ranked_subquery = (
        select(
            GitleaksScanTask.project_id.label("project_id"),
            GitleaksScanTask.id.label("task_id"),
            GitleaksScanTask.created_at.label("created_at"),
            GitleaksScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=GitleaksScanTask.project_id,
                order_by=GitleaksScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(GitleaksScanTask.status) == "completed")
        .subquery()
    )
    latest_gitleaks_subquery = (
        select(
            gitleaks_ranked_subquery.c.project_id,
            gitleaks_ranked_subquery.c.task_id,
            gitleaks_ranked_subquery.c.created_at,
            gitleaks_ranked_subquery.c.total_findings,
        )
        .where(gitleaks_ranked_subquery.c.rn == 1)
        .subquery()
    )

    bandit_ranked_subquery = (
        select(
            BanditScanTask.project_id.label("project_id"),
            BanditScanTask.id.label("task_id"),
            BanditScanTask.created_at.label("created_at"),
            BanditScanTask.total_findings.label("total_findings"),
            BanditScanTask.high_count.label("high_count"),
            BanditScanTask.medium_count.label("medium_count"),
            BanditScanTask.low_count.label("low_count"),
            func.row_number()
            .over(
                partition_by=BanditScanTask.project_id,
                order_by=BanditScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(BanditScanTask.status) == "completed")
        .subquery()
    )
    latest_bandit_subquery = (
        select(
            bandit_ranked_subquery.c.project_id,
            bandit_ranked_subquery.c.task_id,
            bandit_ranked_subquery.c.created_at,
            bandit_ranked_subquery.c.total_findings,
            bandit_ranked_subquery.c.high_count,
            bandit_ranked_subquery.c.medium_count,
            bandit_ranked_subquery.c.low_count,
        )
        .where(bandit_ranked_subquery.c.rn == 1)
        .subquery()
    )

    phpstan_ranked_subquery = (
        select(
            PhpstanScanTask.project_id.label("project_id"),
            PhpstanScanTask.id.label("task_id"),
            PhpstanScanTask.created_at.label("created_at"),
            PhpstanScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=PhpstanScanTask.project_id,
                order_by=PhpstanScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(PhpstanScanTask.status) == "completed")
        .subquery()
    )
    latest_phpstan_subquery = (
        select(
            phpstan_ranked_subquery.c.project_id,
            phpstan_ranked_subquery.c.task_id,
            phpstan_ranked_subquery.c.created_at,
            phpstan_ranked_subquery.c.total_findings,
        )
        .where(phpstan_ranked_subquery.c.rn == 1)
        .subquery()
    )

    # 以 opengrep 最新 completed 为主锚，配对同批（60 秒窗口）gitleaks completed 任务
    paired_gitleaks_ranked_subquery = (
        select(
            latest_opengrep_subquery.c.project_id.label("project_id"),
            GitleaksScanTask.id.label("task_id"),
            GitleaksScanTask.created_at.label("created_at"),
            GitleaksScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=latest_opengrep_subquery.c.project_id,
                order_by=(
                    func.abs(
                        func.extract(
                            "epoch",
                            GitleaksScanTask.created_at
                            - latest_opengrep_subquery.c.created_at,
                        )
                    ).asc(),
                    GitleaksScanTask.created_at.desc(),
                ),
            )
            .label("rn"),
        )
        .select_from(latest_opengrep_subquery)
        .join(
            GitleaksScanTask,
            and_(
                GitleaksScanTask.project_id == latest_opengrep_subquery.c.project_id,
                func.lower(GitleaksScanTask.status) == "completed",
                func.abs(
                    func.extract(
                        "epoch",
                        GitleaksScanTask.created_at
                        - latest_opengrep_subquery.c.created_at,
                    )
                )
                <= 60,
            ),
        )
        .subquery()
    )

    paired_gitleaks_subquery = (
        select(
            paired_gitleaks_ranked_subquery.c.project_id,
            paired_gitleaks_ranked_subquery.c.task_id,
            paired_gitleaks_ranked_subquery.c.created_at,
            paired_gitleaks_ranked_subquery.c.total_findings,
        )
        .where(paired_gitleaks_ranked_subquery.c.rn == 1)
        .subquery()
    )

    last_scan_without_bandit_expr = case(
        (
            latest_opengrep_subquery.c.created_at.is_not(None),
            case(
                (
                    and_(
                        paired_gitleaks_subquery.c.created_at.is_not(None),
                        paired_gitleaks_subquery.c.created_at
                        > latest_opengrep_subquery.c.created_at,
                    ),
                    paired_gitleaks_subquery.c.created_at,
                ),
                else_=latest_opengrep_subquery.c.created_at,
            ),
        ),
        else_=latest_gitleaks_subquery.c.created_at,
    )
    last_scan_with_bandit_expr = case(
        (
            and_(
                latest_bandit_subquery.c.created_at.is_not(None),
                or_(
                    last_scan_without_bandit_expr.is_(None),
                    latest_bandit_subquery.c.created_at > last_scan_without_bandit_expr,
                ),
            ),
            latest_bandit_subquery.c.created_at,
        ),
        else_=last_scan_without_bandit_expr,
    )
    last_scan_at_expr = case(
        (
            and_(
                latest_phpstan_subquery.c.created_at.is_not(None),
                or_(
                    last_scan_with_bandit_expr.is_(None),
                    latest_phpstan_subquery.c.created_at > last_scan_with_bandit_expr,
                ),
            ),
            latest_phpstan_subquery.c.created_at,
        ),
        else_=last_scan_with_bandit_expr,
    )

    base_stmt = (
        select(
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            latest_opengrep_subquery.c.task_id.label("opengrep_task_id"),
            latest_opengrep_subquery.c.created_at.label("opengrep_created_at"),
            latest_opengrep_subquery.c.total_findings.label("opengrep_total_findings"),
            latest_opengrep_subquery.c.error_count.label("opengrep_error_count"),
            latest_opengrep_subquery.c.warning_count.label("opengrep_warning_count"),
            paired_gitleaks_subquery.c.task_id.label("paired_gitleaks_task_id"),
            paired_gitleaks_subquery.c.created_at.label("paired_gitleaks_created_at"),
            paired_gitleaks_subquery.c.total_findings.label(
                "paired_gitleaks_total_findings"
            ),
            latest_gitleaks_subquery.c.task_id.label("latest_gitleaks_task_id"),
            latest_gitleaks_subquery.c.created_at.label("latest_gitleaks_created_at"),
            latest_gitleaks_subquery.c.total_findings.label(
                "latest_gitleaks_total_findings"
            ),
            latest_bandit_subquery.c.task_id.label("latest_bandit_task_id"),
            latest_bandit_subquery.c.created_at.label("latest_bandit_created_at"),
            latest_bandit_subquery.c.total_findings.label("latest_bandit_total_findings"),
            latest_bandit_subquery.c.high_count.label("latest_bandit_high_count"),
            latest_bandit_subquery.c.medium_count.label("latest_bandit_medium_count"),
            latest_bandit_subquery.c.low_count.label("latest_bandit_low_count"),
            latest_phpstan_subquery.c.task_id.label("latest_phpstan_task_id"),
            latest_phpstan_subquery.c.created_at.label("latest_phpstan_created_at"),
            latest_phpstan_subquery.c.total_findings.label("latest_phpstan_total_findings"),
            last_scan_at_expr.label("last_scan_at"),
        )
        .select_from(Project)
        .outerjoin(
            latest_opengrep_subquery,
            latest_opengrep_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_gitleaks_subquery,
            latest_gitleaks_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            paired_gitleaks_subquery,
            paired_gitleaks_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_bandit_subquery,
            latest_bandit_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_phpstan_subquery,
            latest_phpstan_subquery.c.project_id == Project.id,
        )
        .where(
            or_(
                latest_opengrep_subquery.c.project_id.is_not(None),
                latest_gitleaks_subquery.c.project_id.is_not(None),
                latest_bandit_subquery.c.project_id.is_not(None),
                latest_phpstan_subquery.c.project_id.is_not(None),
            )
        )
    )
    if keyword and keyword.strip():
        base_stmt = base_stmt.where(
            func.lower(Project.name).like(f"%{keyword.strip().lower()}%")
        )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar() or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)

    paged_stmt = (
        base_stmt.order_by(last_scan_at_expr.desc(), Project.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows_result = await db.execute(paged_stmt)
    rows = rows_result.mappings().all()

    items: List[StaticScanOverviewItem] = []
    for row in rows:
        item = _build_static_scan_overview_item_from_row(dict(row))
        if item is not None:
            items.append(item)

    return StaticScanOverviewResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
