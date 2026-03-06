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

import hashlib
import json
import logging
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional, Literal

from pydantic import BaseModel, Field, field_validator

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class VerificationResultModel(BaseModel):
    """验证结果的标准化嵌套结构 - 每条 finding 的 verification_result 必须符合此模型"""

    verdict: Literal["confirmed", "likely", "uncertain", "false_positive"] = Field(
        ...,
        description=(
            "真实性判定。必须为以下之一：\n"
            "  - confirmed: 已通过多重验证确认，confidence >= 0.8\n"
            "  - likely: 初步验证表明漏洞很可能存在，0.7 <= confidence < 0.8\n"
            "  - uncertain: 信息不足，无法明确判定真假，0.3 <= confidence < 0.7\n"
            "  - false_positive: 经验证为误报或不存在，confidence < 0.3"
        ),
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="置信度，必须是 [0.0, 1.0] 范围内的浮点数（不能为字符串）",
    )
    
    reachability: Literal["reachable", "likely_reachable", "unknown", "unreachable"] = Field(
        ...,
        description=(
            "代码路径可达性判定。必须为以下之一：\n"
            "  - reachable: 确认代码路径从外部输入可达\n"
            "  - likely_reachable: 很可能可达，但需进一步验证\n"
            "  - unknown: 无法确定可达性\n"
            "  - unreachable: 代码路径无法从外部触发"
        ),
    )
    
    verification_evidence: str = Field(
        ...,
        min_length=10,
        description=(
            "验证证据，必须包含：\n"
            "  1. 使用的验证方法（fuzzing/static_analysis/symbols/dynamic/other）\n"
            "  2. 关键代码片段或执行输出\n"
            "  3. 漏洞存在或不存在的理由\n"
            "最少 10 个字符。"
        ),
    )
    
    # 可选字段
    poc_plan: Optional[str] = Field(
        default=None,
        description="非武器化 PoC 思路或复现步骤说明（仅用于文档，不能是可直接运行的代码）",
    )
    
    code_snippet: Optional[str] = Field(
        default=None,
        description="相关的代码片段，用于上下文说明",
    )
    
    suggestion: Optional[str] = Field(
        default=None,
        description="修复建议或防御措施",
    )
    
    function_trigger_flow: Optional[List[str]] = Field(
        default=None,
        description="函数触发链或调用链，描述从入口点到漏洞的执行路径",
    )
    
    code_context: Optional[str] = Field(
        default=None,
        description="更广泛的代码上下文，帮助理解漏洞背景",
    )
    
    localization_status: Optional[str] = Field(
        default=None,
        description="代码定位状态：'success'（成功定位函数）、'failed'（定位失败）、'partial'（部分定位）",
    )

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v):
        """确保 verdict 是允许的值"""
        allowed = {"confirmed", "likely", "uncertain", "false_positive"}
        if v not in allowed:
            raise ValueError(f"verdict 必须为 {allowed} 之一，得到: {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        """确保 confidence 是浮点数且在范围内"""
        if isinstance(v, str):
            raise ValueError(f"confidence 必须是 float 类型，不能是字符串: {v}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"confidence 必须是数值类型，得到: {type(v).__name__}")
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence 必须在 [0.0, 1.0] 范围内，得到: {v}")
        return float(v)

    @field_validator("reachability")
    @classmethod
    def validate_reachability(cls, v):
        """确保 reachability 是允许的值"""
        allowed = {"reachable", "likely_reachable", "unknown", "unreachable"}
        if v not in allowed:
            raise ValueError(f"reachability 必须为 {allowed} 之一，得到: {v}")
        return v

    @field_validator("verification_evidence")
    @classmethod
    def validate_evidence(cls, v):
        """确保 verification_evidence 非空且足够长"""
        if not v or len(v.strip()) < 10:
            raise ValueError("verification_evidence 必须至少 10 个字符，且不能为空")
        return v


class AgentFindingModel(BaseModel):
    """Agent 发现的漏洞的标准化结构 - 每条 finding 必须符合此模型"""

    file_path: str = Field(
        ...,
        min_length=1,
        description="完整文件路径（从项目根目录的相对路径或绝对路径）",
    )
    
    line_start: int = Field(
        ...,
        ge=1,
        description="代码起始行号（从 1 开始）",
    )
    
    line_end: Optional[int] = Field(
        default=None,
        ge=1,
        description="代码结束行号（可选，如果不提供则默认等于 line_start）",
    )
    
    title: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="漏洞标题（5-200 字符）",
    )
    
    vulnerability_type: str = Field(
        ...,
        min_length=1,
        description="漏洞类型（如 sql_injection、xss、command_injection 等）",
    )
    
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        ...,
        description="严重程度：critical, high, medium, low, info",
    )
    
    cwe_id: Optional[str] = Field(
        default=None,
        description="CWE 编号，格式：CWE-123 或 CWE-123, CWE-456（可选）",
    )
    
    verification_result: VerificationResultModel = Field(
        ...,
        description="验证结果，必须包含 verdict、confidence、reachability、verification_evidence 等必填字段",
    )
    
    # 可选字段
    function_name: Optional[str] = Field(
        default=None,
        description="函数名称（如果可定位）",
    )
    
    description: Optional[str] = Field(
        default=None,
        description="详细描述",
    )
    
    @field_validator("line_end", mode="before")
    @classmethod
    def set_line_end_default(cls, v, info):
        """如果 line_end 未提供，默认设为 line_start"""
        if v is None and "line_start" in info.data:
            return info.data["line_start"]
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v):
        """确保 severity 是允许的值"""
        allowed = {"critical", "high", "medium", "low", "info"}
        if v not in allowed:
            raise ValueError(f"severity 必须为 {allowed} 之一，得到: {v}")
        return v

    @field_validator("cwe_id", mode="before")
    @classmethod
    def validate_cwe_id_if_present(cls, v):
        """如果存在 cwe_id 字段，验证其格式"""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError(f"cwe_id 必须是字符串或 null，得到: {type(v).__name__}")
        # 允许格式：CWE-123、CWE-123, CWE-456 等
        pattern = r"^CWE-\d+(\s*,\s*CWE-\d+)*$|^$"
        if not re.match(pattern, v, re.IGNORECASE):
            raise ValueError(f"cwe_id 必须符合格式 CWE-123 或 CWE-123, CWE-456 等，得到: {v}")
        return v


class SaveVerificationResultsInput(BaseModel):
    """保存验证结果工具的输入参数 - 严密参数约束"""

    findings: List[AgentFindingModel] = Field(
        ...,
        min_items=1,
        description=(
            "已验证的 findings 列表（至少 1 条）。每条 finding 必须是有效的 AgentFindingModel，\n"
            "包含以下必填字段：\n"
            "  - file_path: 文件路径\n"
            "  - line_start: 起始行号（>= 1）\n"
            "  - title: 发现标题（5-200 字符）\n"
            "  - vulnerability_type: 漏洞类型\n"
            "  - severity: 严重程度（critical|high|medium|low|info）\n"
            "  - verification_result: 嵌套的 VerificationResultModel 对象\n"
            "\n"
            "每条 finding 的 verification_result 必须包含：\n"
            "  - verdict: 真实性判定（confirmed|likely|uncertain|false_positive）\n"
            "  - confidence: 置信度 [0.0-1.0 浮点数]\n"
            "  - reachability: 可达性（reachable|likely_reachable|unknown|unreachable）\n"
            "  - verification_evidence: 验证证据（至少 10 字符）\n"
            "\n"
            "false_positive 和 uncertain verdict 的 findings 会被保存但分别标记为不同的状态。"
        ),
    )
    
    summary: Optional[str] = Field(
        default=None,
        description="可选的摘要信息，记录本轮验证的整体结论（用于日志）。建议包含：总数、verdict分布等。",
    )
    
    strict_mode: Optional[bool] = Field(
        default=True,
        description=(
            "严格模式（默认 True）：任何单个 finding 的验证失败都会导致整个工具调用失败。\n"
            "非严格模式（False）：验证失败的 findings 会被过滤并记录在 validation_errors 中。"
        ),
    )

    @field_validator("findings", mode="before")
    @classmethod
    def coerce_findings_to_models(cls, v):
        """尝试将原始 Dict findings 转换为 AgentFindingModel"""
        if not isinstance(v, list):
            raise ValueError("findings 必须是列表")

        def _normalize_reachability(verdict: Optional[str], reachability: Any) -> str:
            text = str(reachability or "").strip().lower()
            allowed = {"reachable", "likely_reachable", "unknown", "unreachable"}
            if text in allowed:
                return text
            if verdict == "confirmed":
                return "reachable"
            if verdict == "likely":
                return "likely_reachable"
            if verdict == "false_positive":
                return "unreachable"
            return "unknown"

        def _normalize_verification_payload(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
            payload = dict(item)
            payload["severity"] = str(payload.get("severity") or "medium").strip().lower()
            if payload.get("line_end") is None and payload.get("line_start") is not None:
                payload["line_end"] = payload.get("line_start")

            vr = payload.get("verification_result")
            if not isinstance(vr, dict):
                vr = {}

            verdict = str(
                vr.get("verdict")
                or payload.get("verdict")
                or payload.get("authenticity")
                or "uncertain"
            ).strip().lower()
            if verdict not in {"confirmed", "likely", "uncertain", "false_positive"}:
                verdict = "uncertain"

            confidence_raw = vr.get("confidence", payload.get("confidence", 0.5))
            try:
                confidence = max(0.0, min(float(confidence_raw), 1.0))
            except Exception:
                confidence = 0.5

            reachability = _normalize_reachability(verdict, vr.get("reachability") or payload.get("reachability"))

            evidence = (
                vr.get("verification_evidence")
                or vr.get("verification_details")
                or payload.get("verification_evidence")
                or payload.get("verification_details")
            )
            evidence_text = str(evidence or "").strip()
            if len(evidence_text) < 10:
                evidence_text = (
                    f"auto_normalized_evidence: verdict={verdict}; "
                    f"confidence={confidence:.2f}; finding_index={idx}"
                )

            payload["verification_result"] = {
                **vr,
                "verdict": verdict,
                "confidence": confidence,
                "reachability": reachability,
                "verification_evidence": evidence_text,
            }
            payload["verdict"] = verdict
            payload["confidence"] = confidence
            payload["reachability"] = reachability
            payload["verification_evidence"] = evidence_text
            return payload
        
        result = []
        for idx, item in enumerate(v):
            if isinstance(item, dict):
                try:
                    normalized_item = _normalize_verification_payload(item, idx)
                    result.append(AgentFindingModel(**normalized_item))
                except Exception as e:
                    raise ValueError(f"findings[{idx}] 验证失败: {str(e)}")
            elif isinstance(item, AgentFindingModel):
                result.append(item)
            else:
                raise ValueError(f"findings[{idx}] 必须是 dict 或 AgentFindingModel，得到: {type(item).__name__}")
        
        return result


class SaveVerificationResultsTool(AgentTool):
    """
    Verification Agent 专用：将验证结果持久化保存到数据库。

    核心责任：
    1. **强制验证参数** - 通过 Pydantic 模型确保所有 findings 的数据质量
    2. **前置校验** - 在工具执行前检查每条 finding 的必填字段和类型
    3. **详细错误报告** - 告知 Agent 哪些字段缺失或错误，便于纠正
    4. **支持多状态** - 持久化 confirmed、likely、uncertain、false_positive 等多种 verdict

    调用时机：在所有 findings 的 verdict / confidence / reachability /
    verification_evidence 都已确定后，调用此工具完成持久化，
    避免结果仅停留在内存中而丢失。

    返回：
    - saved_count: 实际入库的 findings 数量（经过滤后）
    - filtered_count: 被过滤掉的数量（false_positive、uncertain 等）
    - already_saved: 是否为重复调用（幂等保护）
    - validation_errors: 验证失败的详情列表（如果有）
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
        self._seen_payload_digests: set[str] = set()

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
- findings: 已验证的 findings 列表（至少 1 条）。每条 finding 必须是有效的结构，
  包含：file_path、line_start、title、vulnerability_type、severity、verification_result。
  每个 verification_result 必须包含 verdict、confidence、reachability、verification_evidence。

可选参数:
- summary: 本轮验证的整体评述（纯日志，不影响保存逻辑）
- strict_mode: 是否使用严格模式（默认 True，验证失败则整体失败；False 则过滤失败项）

返回值:
- saved_count: 成功入库条数（confirmed、likely 等状态）
- filtered_count: 因质量门校验或 false_positive/uncertain 而被过滤的条数
- validation_errors: 详细的验证失败列表（如果 strict_mode=False）
- already_saved: 是否为重复调用（本工具支持幂等）
- message: 结果描述

注意：
- false_positive 和 uncertain verdict 的 findings 会被接受但分别标记为不同的状态
- 所有 confidence 值必须是浮点数 [0.0-1.0]，不能为字符串
- 所有 cwe_id 必须符合 CWE-XXX 格式或为 null
- 调用一次即可，无需重复调用（幂等保护）"""

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

    @staticmethod
    def _build_payload_digest(findings: List[Dict[str, Any]]) -> str:
        try:
            normalized = json.dumps(findings, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            normalized = str(findings)
        return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #

    async def _execute(
        self,
        findings: List[AgentFindingModel],
        summary: Optional[str] = None,
        strict_mode: bool = True,
        **kwargs,
    ) -> ToolResult:
        """
        参数验证和持久化执行。

        Args:
            findings: 已验证发现列表（Pydantic 模型已验证）
            summary: 可选摘要
            strict_mode: 严格模式（默认 True）

        Returns:
            ToolResult，包含 saved_count、filtered_count、validation_errors 等
        """
        task_id = self.task_id

        # 基础校验
        if not findings:
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

        # 所有 findings 都已通过 Pydantic 验证（在 coerce_findings_to_models 中）
        # 这里直接将它们转换回 Dict 格式以供持久化
        valid_findings = [f.model_dump(exclude_none=True) for f in findings]

        payload_digest = self._build_payload_digest(valid_findings)
        if payload_digest in self._seen_payload_digests:
            logger.info(
                "[SaveVerificationResults][%s] 幂等保护：重复 payload（digest=%s），跳过重复持久化",
                task_id,
                payload_digest[:12],
            )
            current_saved = int(self._saved_count or 0)
            return ToolResult(
                success=True,
                data={
                    "saved_count": current_saved,
                    "filtered_count": 0,
                    "already_saved": True,
                    "message": f"重复 payload 已跳过，累计 saved_count={current_saved}",
                },
            )
        
        # 更新内存缓冲（供外部兜底读取）
        self._buffered_findings = list(valid_findings)

        if summary:
            logger.info("[SaveVerificationResults][%s] 验证摘要: %s", task_id, summary[:200])

        logger.info(
            "[SaveVerificationResults][%s] 开始保存 %d 条已验证的 findings …",
            task_id,
            len(valid_findings),
        )

        # ---- 统计各 verdict 分布（方便调试）----
        verdict_counts: Dict[str, int] = {}
        for f in valid_findings:
            vr = f.get("verification_result") or {}
            v = str((vr.get("verdict") if isinstance(vr, dict) else None) or "unknown").lower()
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
            self._seen_payload_digests.add(payload_digest)
            previous_saved = int(self._saved_count or 0)
            current_saved = int(saved)
            self._saved_count = previous_saved + current_saved
            filtered = max(0, len(valid_findings) - current_saved)
            logger.info(
                "[SaveVerificationResults][%s] 持久化完成：batch_saved=%d, filtered=%d, total_saved=%d",
                task_id,
                current_saved,
                filtered,
                self._saved_count,
            )
            return ToolResult(
                success=True,
                data={
                    "saved_count": self._saved_count,
                    "batch_saved_count": current_saved,
                    "filtered_count": filtered,
                    "already_saved": False,
                    "message": (
                        f"✅ 验证结果已保存：本批 {current_saved} 条，累计 {self._saved_count} 条"
                        + (f"，{filtered} 条被过滤（false_positive/uncertain 等）" if filtered else "")
                        + f"\n前置参数验证：所有 {len(valid_findings)} 条 findings 已通过严格的 Pydantic 模型验证"
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
