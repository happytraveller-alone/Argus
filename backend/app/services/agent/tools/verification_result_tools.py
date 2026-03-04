"""
Verification Agent 结果保存工具

供 Verification Agent 在验证完成后调用，将最终 findings
通过注入的持久化回调保存到数据库，避免依赖 Orchestrator
侧的批量写入而产生的延迟或遗漏。

设计原则：
- 工具构造时注入 save_callback（与队列工具注入 queue_service 的方式一致）
- 工具本身无 DB/ORM 依赖，持久化逻辑由调用方提供
- 支持多次调用（幂等保护由回调内部负责）
- 提供内存暂存缓冲，即使回调未注入也可缓存结果供 Orchestrator 读取
"""

import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class SaveVerificationResultsInput(BaseModel):
    """保存验证结果工具的输入参数"""

    findings: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "已验证的 findings 列表。每条 finding 必须包含：\n"
            "  - file_path: 文件路径\n"
            "  - line_start: 起始行号\n"
            "  - title: 发现标题\n"
            "  - vulnerability_type: 漏洞类型\n"
            "  - severity: 严重程度\n"
            "  - verification_result: 嵌套对象，包含 verdict / confidence / "
            "reachability / verification_evidence\n"
            "verdict 必须为 confirmed / likely（false_positive 会被自动过滤，不入库）。"
        ),
    )
    summary: Optional[str] = Field(
        default=None,
        description="可选的摘要信息，记录本轮验证的整体结论（用于日志）",
    )


class SaveVerificationResultsTool(AgentTool):
    """
    Verification Agent 专用：将验证结果持久化保存到数据库。

    调用时机：在所有 findings 的 verdict / confidence / reachability /
    verification_evidence 都已确定后，调用此工具完成持久化，
    避免结果仅停留在内存中而丢失。

    返回：
    - saved_count: 实际入库的 findings 数量（经严格质量门过滤后）
    - filtered_count: 被过滤掉的数量（误报、缺少字段等）
    - already_saved: 是否为重复调用（幂等保护）
    - message: 人类可读的结果描述
    """

    def __init__(
        self,
        task_id: str,
        save_callback: Optional[Callable[[List[Dict[str, Any]]], Coroutine[Any, Any, int]]] = None,
    ):
        """
        Args:
            task_id: 当前审计任务 ID，用于日志追踪
            save_callback: 异步持久化回调 async (findings: List[Dict]) -> int
                           返回实际保存的条数。若为 None，结果仅写入内存缓冲。
        """
        super().__init__()
        self.task_id = task_id
        self._save_callback = save_callback
        # 内存缓冲：即使没有注入回调也能暂存结果
        self._buffered_findings: List[Dict[str, Any]] = []
        self._saved_count: Optional[int] = None  # None 表示尚未调用过

    # ------------------------------------------------------------------ #
    # AgentTool 必须实现的属性
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return "save_verification_results"

    @property
    def description(self) -> str:
        return """将本轮验证结果持久化保存到数据库。

在完成所有漏洞验证、确定每条 finding 的 verdict / confidence /
reachability / verification_evidence 之后，必须调用此工具，
否则结果只存在内存中，任务结束后会丢失。

必需参数:
- findings: 已验证的 findings 列表（见参数 schema）

可选参数:
- summary: 本轮验证的整体评述（纯日志，不影响保存逻辑）

返回值:
- saved_count: 成功入库条数
- filtered_count: 因质量门校验未通过而被过滤的条数
- already_saved: 是否为重复调用（本工具支持幂等）
- message: 结果描述

注意：verdict 为 false_positive 的 finding 会被自动跳过，
只有 confirmed / likely 且通过文件路径、enclosing function
等质量门的 finding 才会入库。调用一次即可，无需重复调用。"""

    @property
    def args_schema(self):
        return SaveVerificationResultsInput

    # ------------------------------------------------------------------ #
    # 公开属性：供 Orchestrator / 持久化兜底逻辑读取
    # ------------------------------------------------------------------ #

    @property
    def buffered_findings(self) -> List[Dict[str, Any]]:
        """返回最近一次（或历次）累积的 findings 缓冲（无论是否已持久化）"""
        return list(self._buffered_findings)

    @property
    def is_saved(self) -> bool:
        """返回是否已通过回调成功持久化（saved_count 不为 None）"""
        return self._saved_count is not None

    @property
    def saved_count(self) -> Optional[int]:
        return self._saved_count

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #

    async def _execute(
        self,
        findings: List[Dict[str, Any]],
        summary: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        task_id = self.task_id

        # 基础校验
        if not isinstance(findings, list):
            return ToolResult(
                success=False,
                error="findings 必须是列表",
                data={"saved_count": 0, "filtered_count": 0},
            )

        valid_findings = [f for f in findings if isinstance(f, dict)]
        if not valid_findings:
            logger.warning("[SaveVerificationResults][%s] 收到空 findings 列表", task_id)
            return ToolResult(
                success=True,
                data={
                    "saved_count": 0,
                    "filtered_count": 0,
                    "already_saved": False,
                    "message": "findings 列表为空，无需保存",
                },
            )

        # 幂等检查：已保存过则直接返回
        if self._saved_count is not None:
            logger.info(
                "[SaveVerificationResults][%s] 幂等保护：结果已保存过（saved_count=%d），跳过重复调用",
                task_id,
                self._saved_count,
            )
            return ToolResult(
                success=True,
                data={
                    "saved_count": self._saved_count,
                    "filtered_count": len(valid_findings) - self._saved_count,
                    "already_saved": True,
                    "message": f"结果已保存（幂等保护），saved_count={self._saved_count}",
                },
            )

        # 更新内存缓冲（供外部兜底读取）
        self._buffered_findings = list(valid_findings)

        if summary:
            logger.info("[SaveVerificationResults][%s] 验证摘要: %s", task_id, summary[:200])

        logger.info(
            "[SaveVerificationResults][%s] 开始保存 %d 条 findings …",
            task_id,
            len(valid_findings),
        )

        # ---- 统计各 verdict 分布（方便调试）----
        verdict_counts: Dict[str, int] = {}
        for f in valid_findings:
            vr = f.get("verification_result") or {}
            v = str(
                (vr.get("verdict") if isinstance(vr, dict) else None)
                or f.get("verdict")
                or "unknown"
            ).lower()
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
        logger.info(
            "[SaveVerificationResults][%s] verdict 分布: %s",
            task_id,
            json.dumps(verdict_counts, ensure_ascii=False),
        )

        if self._save_callback is None:
            # 无回调时仅写入缓冲，Orchestrator 侧兜底持久化会读取 buffered_findings
            logger.warning(
                "[SaveVerificationResults][%s] 未注入 save_callback，结果仅写入内存缓冲 (%d 条)",
                task_id,
                len(valid_findings),
            )
            # 标记"已缓存但未持久化"——saved_count 保持 None 以便兜底逻辑仍然运行
            return ToolResult(
                success=True,
                data={
                    "saved_count": 0,
                    "filtered_count": 0,
                    "already_saved": False,
                    "buffered": True,
                    "message": (
                        f"结果已写入内存缓冲（{len(valid_findings)} 条），"
                        "将在任务完成时由 Orchestrator 统一持久化"
                    ),
                },
            )

        # 调用注入的持久化回调
        try:
            saved = await self._save_callback(valid_findings)
            self._saved_count = int(saved)
            filtered = len(valid_findings) - self._saved_count
            logger.info(
                "[SaveVerificationResults][%s] 持久化完成：saved=%d, filtered=%d",
                task_id,
                self._saved_count,
                filtered,
            )
            return ToolResult(
                success=True,
                data={
                    "saved_count": self._saved_count,
                    "filtered_count": filtered,
                    "already_saved": False,
                    "message": (
                        f"✅ 验证结果已保存：{self._saved_count} 条成功入库"
                        + (f"，{filtered} 条被过滤（误报/质量门）" if filtered else "")
                    ),
                },
            )
        except Exception as exc:
            logger.error(
                "[SaveVerificationResults][%s] 持久化失败: %s",
                task_id,
                exc,
                exc_info=True,
            )
            return ToolResult(
                success=False,
                error=str(exc),
                data={
                    "saved_count": 0,
                    "filtered_count": len(valid_findings),
                    "already_saved": False,
                    "message": f"❌ 持久化失败: {exc}",
                },
            )
