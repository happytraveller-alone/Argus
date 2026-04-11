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

_UPDATE_ALLOWED_TOP_LEVEL_FIELDS = {
    "file_path",
    "line_start",
    "line_end",
    "function_name",
    "title",
    "vulnerability_type",
    "severity",
    "description",
    "code_snippet",
    "source",
    "sink",
    "suggestion",
}
_UPDATE_ALLOWED_VERIFICATION_FIELDS = {
    "localization_status",
    "function_trigger_flow",
    "verification_evidence",
    "verification_details",
    "evidence",
    "verdict",
    "authenticity",
    "confidence",
    "reachability",
}
_UPDATE_FORBIDDEN_FIELDS = {
    "finding_identity",
    "verdict",
    "confidence",
    "reachability",
    "id",
    "task_id",
    "fingerprint",
}

_ALLOWED_VERDICTS = {"confirmed", "likely", "uncertain", "false_positive"}
_ALLOWED_REACHABILITY = {"reachable", "likely_reachable", "unknown", "unreachable"}


def _normalize_save_verdict(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in _ALLOWED_VERDICTS:
        return text
    return ""


def _normalize_save_status(value: Any, verdict: Optional[str]) -> str:
    text = str(value or "").strip().lower()
    if text in {"verified", "true_positive", "exists", "vulnerable", "confirmed"}:
        return "verified"
    if text in {"likely", "uncertain", "unknown", "needs_review", "needs-review"}:
        return "likely"
    if text in {"false_positive", "false-positive", "not_vulnerable", "not_exists", "non_vuln"}:
        return "false_positive"

    normalized_verdict = _normalize_save_verdict(verdict)
    if normalized_verdict == "confirmed":
        return "verified"
    if normalized_verdict in {"likely", "uncertain"}:
        return "likely"
    if normalized_verdict == "false_positive":
        return "false_positive"
    return "likely"


def build_finding_identity(task_id: str, finding: Dict[str, Any]) -> str:
    file_path = str(finding.get("file_path") or finding.get("file") or "").strip().lower()
    vuln_type = str(finding.get("vulnerability_type") or finding.get("type") or "").strip().lower()
    title = str(finding.get("title") or "").strip().lower()
    function_name = str(finding.get("function_name") or "").strip().lower()
    try:
        line_start = int(finding.get("line_start") or finding.get("line") or 0)
    except Exception:
        line_start = 0
    raw = "|".join(
        [
            str(task_id or "").strip(),
            file_path,
            str(line_start),
            vuln_type,
            title,
            function_name,
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"fid:{digest}"


def ensure_finding_identity(task_id: str, finding: Dict[str, Any]) -> str:
    if not isinstance(finding, dict):
        return ""
    existing = str(
        finding.get("finding_identity")
        or ((finding.get("finding_metadata") or {}).get("finding_identity") if isinstance(finding.get("finding_metadata"), dict) else "")
        or ((finding.get("verification_result") or {}).get("finding_identity") if isinstance(finding.get("verification_result"), dict) else "")
        or ""
    ).strip()
    identity = existing or build_finding_identity(task_id, finding)
    finding["finding_identity"] = identity
    metadata = dict(finding.get("finding_metadata") or {})
    metadata["finding_identity"] = identity
    finding["finding_metadata"] = metadata
    verification_result = dict(finding.get("verification_result") or {})
    verification_result["finding_identity"] = identity
    finding["verification_result"] = verification_result
    return identity


def merge_finding_patch(base_finding: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base_finding or {})
    for key, value in (patch or {}).items():
        if key == "verification_result" and isinstance(value, dict):
            vr = dict(merged.get("verification_result") or {})
            for vr_key, vr_value in value.items():
                if vr_value is not None:
                    vr[vr_key] = vr_value
            merged["verification_result"] = vr
            continue
        if value is not None:
            merged[key] = value
    return merged


def validate_finding_update_patch(fields_to_update: Dict[str, Any]) -> tuple[bool, Optional[str], Dict[str, Any], List[str]]:
    if not isinstance(fields_to_update, dict) or not fields_to_update:
        return False, "fields_to_update 不能为空", {}, []

    sanitized: Dict[str, Any] = {}
    updated_fields: List[str] = []
    verification_patch: Dict[str, Any] = {}

    for key, value in fields_to_update.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if key_text in _UPDATE_FORBIDDEN_FIELDS:
            return False, f"禁止更新字段: {key_text}", {}, []
        if key_text.startswith("verification_result."):
            nested_key = key_text.split(".", 1)[1]
            if nested_key not in _UPDATE_ALLOWED_VERIFICATION_FIELDS:
                return False, f"禁止更新字段: {key_text}", {}, []
            verification_patch[nested_key] = value
            updated_fields.append(key_text)
            continue
        if key_text == "verification_result":
            if not isinstance(value, dict) or not value:
                return False, "verification_result 必须是非空对象", {}, []
            for nested_key, nested_value in value.items():
                nested_text = str(nested_key or "").strip()
                if nested_text not in _UPDATE_ALLOWED_VERIFICATION_FIELDS:
                    return False, f"禁止更新字段: verification_result.{nested_text}", {}, []
                verification_patch[nested_text] = nested_value
                updated_fields.append(f"verification_result.{nested_text}")
            continue
        if key_text not in _UPDATE_ALLOWED_TOP_LEVEL_FIELDS:
            return False, f"禁止更新字段: {key_text}", {}, []
        sanitized[key_text] = value
        updated_fields.append(key_text)

    if verification_patch:
        sanitized["verification_result"] = verification_patch
    if not sanitized:
        return False, "fields_to_update 不包含可更新字段", {}, []
    return True, None, sanitized, updated_fields


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

    finding_identity: Optional[str] = Field(
        default=None,
        description="漏洞稳定身份标识。若未提供，将在保存时按 task_id + 原始定位信息生成。",
    )

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
    
    function_name: str = Field(
        ...,
        min_length=1,
        description="函数名称（必填）。无法精确定位时可使用语义化占位符（如 <function_at_line_120>）",
    )
    
    description: Optional[str] = Field(
        default=None,
        description="详细描述",
    )

    status: Optional[Literal["verified", "likely", "false_positive", "uncertain"]] = Field(
        default=None,
        description="展示状态。推荐使用 verified|likely|false_positive；传 uncertain 时会在保存时归一化为 likely。",
    )

    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="顶层置信度，若提供会与 verification_result.confidence 对齐。",
    )

    source: Optional[str] = Field(default=None, description="Source 描述")
    sink: Optional[str] = Field(default=None, description="Sink 描述")
    dataflow_path: Optional[List[str]] = Field(default=None, description="数据流路径")
    cvss_score: Optional[float] = Field(default=None, description="CVSS3.1 分数")
    cvss_vector: Optional[str] = Field(default=None, description="CVSS3.1 向量")
    poc_code: Optional[str] = Field(default=None, description="Fuzzing Harness / PoC 代码")
    suggestion: Optional[str] = Field(default=None, description="修复建议")
    code_snippet: Optional[str] = Field(default=None, description="漏洞代码片段")
    code_context: Optional[str] = Field(default=None, description="漏洞上下文代码")
    report: Optional[str] = Field(default=None, description="漏洞详情 Markdown 报告")
    
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

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, v):
        """确保 function_name 非空字符串"""
        if v is None:
            raise ValueError("function_name 为必填字段，不能为空")
        text = str(v).strip()
        if not text:
            raise ValueError("function_name 不能为空字符串")
        return text

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status_if_present(cls, v):
        if v is None:
            return v
        normalized = _normalize_save_status(v, None)
        return normalized or None

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
        min_length=1,
        description=(
            "已验证的 findings 列表（至少 1 条）。每条 finding 必须是有效的 AgentFindingModel，\n"
            "包含以下必填字段：\n"
            "  - file_path: 文件路径\n"
            "  - line_start: 起始行号（>= 1）\n"
            "  - function_name: 函数名称（必填，无法精确定位时使用语义化占位符）\n"
            "  - title: 发现标题（5-200 字符）\n"
            "  - vulnerability_type: 漏洞类型\n"
            "  - severity: 严重程度（critical|high|medium|low|info）\n"
            "  - verification_result: 嵌套的 VerificationResultModel 对象\n"
            "推荐额外提供以下展示字段：\n"
            "  - status: 展示状态（verified|likely|false_positive；legacy uncertain 会归一化为 likely）\n"
            "  - description/source/sink/dataflow_path: 用于漏洞详情展示\n"
            "  - poc_code/suggestion: 用于 PoC 与修复建议展示\n"
            "  - cvss_score/cvss_vector: 用于风险评分展示\n"
            "\n"
            "每条 finding 的 verification_result 必须包含：\n"
            "  - verdict: 真实性判定（confirmed|likely|uncertain|false_positive）\n"
            "  - confidence: 置信度 [0.0-1.0 浮点数]\n"
            "  - reachability: 可达性（reachable|likely_reachable|unknown|unreachable）\n"
            "  - verification_evidence: 验证证据（至少 10 字符）\n"
            "\n"
            "false_positive 会被标记为 false_positive；likely/uncertain 会统一落到 likely 状态，方便后续展示。"
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
            if text in _ALLOWED_REACHABILITY:
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

            verdict = _normalize_save_verdict(
                vr.get("verdict")
                or payload.get("verdict")
                or payload.get("authenticity")
                or "likely"
            )
            if not verdict:
                verdict = "likely"

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

            normalized_status = _normalize_save_status(
                vr.get("status") or payload.get("status"),
                verdict,
            )
            if normalized_status == "likely" and verdict == "uncertain":
                verdict = "likely"

            payload["verification_result"] = {
                **vr,
                "verdict": verdict,
                "confidence": confidence,
                "reachability": reachability,
                "verification_evidence": evidence_text,
                "status": normalized_status,
            }
            payload["verdict"] = verdict
            payload["confidence"] = confidence
            payload["reachability"] = reachability
            payload["verification_evidence"] = evidence_text
            payload["status"] = normalized_status

            function_name = str(payload.get("function_name") or "").strip()
            if not function_name:
                title_text = str(payload.get("title") or "")
                title_match = re.search(r"中([A-Za-z_][A-Za-z0-9_]*)函数", title_text)
                if title_match:
                    function_name = title_match.group(1).strip()
            if not function_name:
                reachability_target = vr.get("reachability_target") if isinstance(vr, dict) else None
                if isinstance(reachability_target, dict):
                    function_name = str(reachability_target.get("function") or "").strip()
            if not function_name:
                line_value = payload.get("line_start")
                function_name = f"<function_at_line_{line_value}>" if line_value else "<function_not_localized>"
            payload["function_name"] = function_name
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


class UpdateVulnerabilityFindingInput(BaseModel):
    finding_identity: str = Field(
        ...,
        min_length=8,
        description="要修正的漏洞稳定身份标识。",
    )
    fields_to_update: Dict[str, Any] = Field(
        ...,
        description=(
            "需要更新的字段。允许顶层字段："
            "file_path,line_start,line_end,function_name,title,vulnerability_type,"
            "severity,description,code_snippet,source,sink,suggestion；"
            "允许嵌套字段：verification_result.localization_status,"
            "verification_result.function_trigger_flow,"
            "verification_result.verification_evidence,"
            "verification_result.verification_details,"
            "verification_result.evidence,"
            "verification_result.verdict,"
            "verification_result.authenticity,"
            "verification_result.confidence,"
            "verification_result.reachability"
        ),
    )
    update_reason: str = Field(
        ...,
        min_length=5,
        description="本次修正原因，例如“Report阶段核对源码后修正行号”。",
    )

    @field_validator("fields_to_update")
    @classmethod
    def validate_patch(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        ok, error, sanitized, _ = validate_finding_update_patch(value)
        if not ok:
            raise ValueError(error or "非法更新字段")
        return sanitized


class SaveVerificationResultTool(AgentTool):
    """
    Verification Agent 专用：将单个验证结果持久化保存到数据库。

    核心责任：
    1. **强制验证参数** - 通过 Pydantic 模型确保 finding 的数据质量
    2. **前置校验** - 在工具执行前检查必填字段和类型
    3. **详细错误报告** - 告知 Agent 哪些字段缺失或错误，便于纠正
    4. **支持多状态** - 持久化 confirmed、likely、false_positive，并兼容 legacy uncertain 输入

    调用时机：每验证完一个漏洞，确定其 verdict / confidence / reachability /
    verification_evidence 后，立即调用此工具完成持久化，
    避免结果仅停留在内存中而丢失。

    返回：
    - saved: 是否成功保存（布尔值）
    - total_saved: 任务累计已保存的 findings 数量
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
        return "save_verification_result"

    @property
    def description(self) -> str:
        return """将单个验证结果持久化保存到数据库。

在验证完一个漏洞后立即调用，避免结果只存在会话内存中而丢失。

【文档要求的必填字段（由 LLM 提供）】
- vulnerability_type: 漏洞类型（建议使用 CWE 编码或规范化类型）
- severity: 严重程度（critical|high|medium|low|info）
- cvss_score: CVSS3.1 分数（可为 null）
- cvss_vector: CVSS3.1 向量（可为 null）
- title: 漏洞标题
- description: 漏洞描述
- file_path: 漏洞文件路径
- line_start: 起始行号（>= 1）
- line_end: 结束行号（默认等于 line_start）
- function_name: 函数名称（无法定位时可用占位符）
- source: Source 描述
- sink: Sink 描述
- dataflow_path: 数据流路径（数组）
- status: 漏洞展示状态（verified|likely|false_positive；legacy uncertain 会自动归一化为 likely）
- poc_code: Fuzzing Harness / PoC 代码
- suggestion: 修复建议
- confidence: 置信度 [0.0, 1.0]
- verification_evidence: 验证证据（必须包含验证方法、关键代码片段或执行输出、漏洞存在与否的理由）
- reachability: 可达性（reachable|likely_reachable|unreachable）

【由 Python 程序补全】
- task_id, is_verified, code_snippet, report

兼容字段（旧链路可继续传）：
- verdict, reachability, cwe_id, poc_plan, code_context, localization_status

返回值：
- saved: 是否成功保存
- total_saved: 任务累计保存数
- message: 结果描述"""

    # args_schema intentionally not overridden (returns None from base class).
    # _execute() accepts individual flat params; SaveVerificationResultInput
    # (which expects a "findings" list) does NOT match the _execute() signature
    # and would cause Pydantic ValidationError on every call.

    # ------------------------------------------------------------------ #
    # 公开属性：供 Orchestrator / 持久化兜底逻辑读取
    # ------------------------------------------------------------------ #

    @property
    def buffered_findings(self) -> List[Dict[str, Any]]:
        """返回最近一次（或历次）累积的 findings 缓冲（无论是否已持久化）"""
        return list(self._buffered_findings)

    @property
    def is_saved(self) -> bool:
        """返回是否已通过回调成功持久化（累计保存条数 > 0）。"""
        return int(self._saved_count or 0) > 0

    @property
    def saved_count(self) -> Optional[int]:
        return self._saved_count

    def clone_for_worker(self) -> "SaveVerificationResultTool":
        """
        为并行 worker 克隆独立工具实例，保留持久化回调但隔离缓冲状态。
        """
        cloned = super().clone_for_worker()
        if isinstance(cloned, SaveVerificationResultTool):
            cloned._buffered_findings = []
            cloned._saved_count = None
            cloned._seen_payload_digests = set()
        return cloned

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
        file_path: Optional[str] = None,
        line_start: Optional[int] = None,
        function_name: Optional[str] = None,
        title: Optional[str] = None,
        vulnerability_type: Optional[str] = None,
        severity: Optional[str] = None,
        confidence: Optional[float] = None,
        status: Optional[str] = None,
        description: Optional[str] = None,
        finding_identity: Optional[str] = None,
        line_end: Optional[int] = None,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        dataflow_path: Optional[List[str]] = None,
        is_verified: Optional[bool] = None,
        cvss_score: Optional[float] = None,
        cvss_vector: Optional[str] = None,
        poc_code: Optional[str] = None,
        suggestion: Optional[str] = None,
        verdict: Optional[str] = None,
        reachability: Optional[str] = None,
        verification_evidence: Optional[str] = None,
        cwe_id: Optional[str] = None,
        poc_plan: Optional[str] = None,
        code_snippet: Optional[str] = None,
        function_trigger_flow: Optional[List[str]] = None,
        code_context: Optional[str] = None,
        localization_status: Optional[str] = None,
        report: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """
        保存单个验证结果。

        Args:
            file_path: 文件路径
            line_start: 起始行号
            function_name: 函数名称
            title: 漏洞标题
            vulnerability_type: 漏洞类型
            severity: 严重程度
            status: 漏洞展示状态（verified|likely|false_positive；legacy uncertain 会自动归一化为 likely）
            verdict: 真实性判定
            confidence: 置信度
            reachability: 可达性
            verification_evidence: 验证证据
            其他可选参数...

        Returns:
            ToolResult，包含 saved、total_saved、message
        """
        task_id = self.task_id

        # 兼容旧版批量入参：{"findings": [{...}, {...}]}
        # 新规范仍推荐单条调用；这里仅做鲁棒性兜底，避免因历史提示词导致整批失败。
        findings_payload = kwargs.get("findings")
        if isinstance(findings_payload, list):
            candidate_findings = [item for item in findings_payload if isinstance(item, dict)]
            if not candidate_findings:
                return ToolResult(
                    success=False,
                    error="findings 为空或格式无效",
                    data={"saved": False, "total_saved": int(self._saved_count or 0)},
                )
            attempted_count = 0
            saved_count = 0
            failed_count = 0
            for item in candidate_findings:
                attempted_count += 1
                verification_payload = (
                    item.get("verification_result")
                    if isinstance(item.get("verification_result"), dict)
                    else {}
                )
                result = await self._execute(
                    file_path=item.get("file_path"),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    function_name=item.get("function_name"),
                    title=item.get("title"),
                    vulnerability_type=item.get("vulnerability_type"),
                    severity=item.get("severity"),
                    confidence=verification_payload.get("confidence", item.get("confidence")),
                    status=verification_payload.get("status", item.get("status")),
                    description=item.get("description"),
                    finding_identity=item.get("finding_identity"),
                    source=item.get("source"),
                    sink=item.get("sink"),
                    dataflow_path=item.get("dataflow_path"),
                    is_verified=item.get("is_verified"),
                    cvss_score=item.get("cvss_score"),
                    cvss_vector=item.get("cvss_vector"),
                    poc_code=item.get("poc_code"),
                    suggestion=item.get("suggestion"),
                    verdict=verification_payload.get("verdict", item.get("verdict")),
                    reachability=verification_payload.get("reachability", item.get("reachability")),
                    verification_evidence=verification_payload.get(
                        "verification_evidence",
                        item.get("verification_evidence"),
                    ),
                    cwe_id=item.get("cwe_id"),
                    poc_plan=verification_payload.get("poc_plan", item.get("poc_plan")),
                    code_snippet=item.get("code_snippet"),
                    function_trigger_flow=verification_payload.get(
                        "function_trigger_flow",
                        item.get("function_trigger_flow"),
                    ),
                    code_context=verification_payload.get("code_context", item.get("code_context")),
                    localization_status=verification_payload.get(
                        "localization_status",
                        item.get("localization_status"),
                    ),
                    report=item.get("report") or item.get("vulnerability_report"),
                )
                if result.success and isinstance(result.data, dict) and (
                    bool(result.data.get("saved")) or bool(result.data.get("already_saved"))
                ):
                    saved_count += 1
                elif result.success:
                    # buffered 也算执行成功，只是不一定已落库
                    saved_count += 0
                else:
                    failed_count += 1

            return ToolResult(
                success=failed_count == 0,
                data={
                    "saved": saved_count > 0,
                    "attempted_count": attempted_count,
                    "saved_count": saved_count,
                    "failed_count": failed_count,
                    "total_saved": int(self._saved_count or 0),
                    "message": (
                        f"批量保存完成：saved={saved_count}, failed={failed_count}, "
                        f"attempted={attempted_count}"
                    ),
                },
            )

        file_path = str(file_path or kwargs.get("path") or "unknown").strip() or "unknown"
        try:
            line_start = max(1, int(line_start if line_start is not None else 1))
        except Exception:
            line_start = 1
        try:
            line_end = int(line_end) if line_end is not None else line_start
        except Exception:
            line_end = line_start
        line_end = max(line_start, line_end)

        function_name = str(function_name or "").strip() or f"<function_at_line_{line_start}>"
        title = str(title or "").strip() or f"{file_path}中{function_name}函数漏洞"
        vulnerability_type = str(vulnerability_type or "unknown").strip() or "unknown"
        severity = str(severity or "medium").strip() or "medium"
        if confidence is None:
            confidence = kwargs.get("ai_confidence", 0.5)

        try:
            normalized_confidence = max(0.0, min(float(confidence), 1.0))
        except Exception:
            normalized_confidence = 0.5

        normalized_severity = str(severity or "medium").strip().lower()
        if normalized_severity not in {"critical", "high", "medium", "low", "info"}:
            normalized_severity = "medium"

        normalized_verdict = _normalize_save_verdict(verdict)
        if not normalized_verdict:
            normalized_verdict = "likely"

        normalized_status = _normalize_save_status(status, normalized_verdict)
        if normalized_status == "likely" and normalized_verdict == "uncertain":
            normalized_verdict = "likely"

        # is_verified 由程序设置：仅表示“已经过 verification 阶段”
        # SaveVerificationResultTool 只在 verification 阶段调用，因此固定为 True。
        normalized_is_verified = True

        normalized_reachability = str(reachability or "").strip().lower()
        if normalized_reachability not in _ALLOWED_REACHABILITY:
            if normalized_verdict == "confirmed":
                normalized_reachability = "reachable"
            elif normalized_verdict == "likely":
                normalized_reachability = "likely_reachable"
            elif normalized_verdict == "false_positive":
                normalized_reachability = "unreachable"
            else:
                normalized_reachability = "unknown"

        evidence_text = str(verification_evidence or "").strip()
        if len(evidence_text) < 10:
            evidence_text = (
                f"auto_generated_verification_evidence: verdict={normalized_verdict}; "
                f"confidence={normalized_confidence:.2f}; file={file_path}"
            )

        if isinstance(dataflow_path, list):
            normalized_dataflow_path = [str(item) for item in dataflow_path if str(item).strip()]
        elif dataflow_path is None:
            normalized_dataflow_path = function_trigger_flow[:] if isinstance(function_trigger_flow, list) else None
        else:
            normalized_dataflow_path = [str(dataflow_path)]

        normalized_cvss_score: Optional[float]
        if cvss_score is None:
            normalized_cvss_score = None
        else:
            try:
                normalized_cvss_score = float(cvss_score)
            except Exception:
                normalized_cvss_score = None

        # 构造 finding 字典
        finding = {
            "finding_identity": finding_identity,
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_end if line_end is not None else line_start,
            "function_name": function_name,
            "title": title,
            "vulnerability_type": vulnerability_type,
            "severity": normalized_severity,
            "cwe_id": cwe_id,
            "description": description,
            "source": source,
            "sink": sink,
            "dataflow_path": normalized_dataflow_path,
            "status": normalized_status,
            "is_verified": normalized_is_verified,
            "verification_stage_completed": True,
            "poc_code": poc_code,
            "suggestion": suggestion,
            "confidence": normalized_confidence,
            "cvss_score": normalized_cvss_score,
            "cvss_vector": cvss_vector,
            "report": report,
            # code_snippet 同时放到顶层，供 _save_findings 作为初始候选值
            # （_save_findings 仍会用文件实际内容覆盖）
            "code_snippet": code_snippet,
            "verification_result": {
                "verdict": normalized_verdict,
                "confidence": normalized_confidence,
                "reachability": normalized_reachability,
                "status": normalized_status,
                "verification_stage_completed": True,
                "verification_evidence": evidence_text,
                "poc_plan": poc_plan,
                "code_snippet": code_snippet,
                "suggestion": suggestion,
                "function_trigger_flow": function_trigger_flow,
                "code_context": code_context,
                "localization_status": localization_status,
            },
        }
        ensure_finding_identity(task_id, finding)

        # 生成指纹用于去重
        fingerprint_data = (
            f"{finding.get('finding_identity')}:{file_path}:{line_start}:"
            f"{function_name}:{vulnerability_type}:{normalized_verdict}:{normalized_status}"
        )
        fingerprint = hashlib.sha1(fingerprint_data.encode("utf-8")).hexdigest()[:12]

        if fingerprint in self._seen_payload_digests:
            logger.info(
                "[SaveVerificationResult][%s] 幂等保护：重复 finding（fingerprint=%s），跳过",
                task_id,
                fingerprint,
            )
            current_saved = int(self._saved_count or 0)
            return ToolResult(
                success=True,
                data={
                    "saved": False,
                    "total_saved": current_saved,
                    "already_saved": True,
                    "message": f"重复 finding 已跳过（{title}），累计 total_saved={current_saved}",
                },
            )

        # 更新内存缓冲（供外部兜底读取）
        self._buffered_findings.append(finding)

        logger.info(
            "[SaveVerificationResult][%s] 保存验证结果：%s (%s) - status=%s, verdict=%s, confidence=%.2f",
            task_id,
            title,
            file_path,
            normalized_status,
            normalized_verdict,
            normalized_confidence,
        )

        if self._save_callback is None:
            # 无回调时仅写入缓冲，Orchestrator 侧兜底持久化会读取 buffered_findings
            logger.warning(
                "[SaveVerificationResult][%s] 未注入 save_callback，结果仅写入内存缓冲",
                task_id,
            )
            return ToolResult(
                success=True,
                data={
                    "saved": False,
                    "total_saved": 0,
                    "buffered": True,
                    "message": f"结果已写入内存缓冲（{title}），将在任务完成时由 Orchestrator 统一持久化",
                },
            )

        # 调用注入的持久化回调
        try:
            saved = await self._save_callback([finding])
            self._seen_payload_digests.add(fingerprint)
            previous_saved = int(self._saved_count or 0)
            self._saved_count = previous_saved + int(saved)
            
            logger.info(
                "[SaveVerificationResult][%s] 持久化完成：finding=%s, total_saved=%d",
                task_id,
                title,
                self._saved_count,
            )
            
            return ToolResult(
                success=True,
                data={
                    "saved": saved > 0,
                    "total_saved": self._saved_count,
                    "message": (
                        f"验证结果已保存：{title}（status={normalized_status}, verdict={normalized_verdict}, "
                        f"confidence={normalized_confidence:.2f}），累计 {self._saved_count} 条"
                    ),
                },
            )
        except Exception as exc:
            logger.error(
                "[SaveVerificationResult][%s] 持久化失败: %s",
                task_id,
                exc,
                exc_info=True,
            )
            return ToolResult(
                success=False,
                error=str(exc),
                data={
                    "saved": False,
                    "total_saved": self._saved_count or 0,
                    "message": f"持久化失败: {exc}",
                },
            )


class UpdateVulnerabilityFindingTool(AgentTool):
    """Report 阶段用于修正已保存 finding 的工具。"""

    def __init__(
        self,
        task_id: str,
        update_callback: Optional[
            Callable[[str, Dict[str, Any], str], Coroutine[Any, Any, Dict[str, Any]]]
        ] = None,
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self._update_callback = update_callback

    @property
    def name(self) -> str:
        return "update_vulnerability_finding"

    @property
    def description(self) -> str:
        return (
            "在 Report 阶段修正已验证漏洞的结构化信息。"
            "必须提供 finding_identity、fields_to_update、update_reason。"
            "只允许修正定位/描述类字段，禁止修改 verdict/confidence/reachability。"
        )

    @property
    def args_schema(self):
        return UpdateVulnerabilityFindingInput

    async def _execute(
        self,
        finding_identity: str,
        fields_to_update: Dict[str, Any],
        update_reason: str,
    ) -> ToolResult:
        ok, error, sanitized, updated_fields = validate_finding_update_patch(fields_to_update)
        if not ok:
            return ToolResult(success=False, error=error, data={"updated": False, "message": error})

        if self._update_callback is None:
            return ToolResult(
                success=False,
                error="未注入 update_callback",
                data={
                    "updated": False,
                    "finding_identity": finding_identity,
                    "message": "update_vulnerability_finding 未配置后端更新回调",
                },
            )

        try:
            updated_finding = await self._update_callback(
                finding_identity,
                sanitized,
                update_reason,
            )
            return ToolResult(
                success=True,
                data={
                    "updated": True,
                    "finding_identity": finding_identity,
                    "updated_fields": updated_fields,
                    "updated_finding": updated_finding,
                    "message": f"已修正 finding：{finding_identity}",
                },
            )
        except Exception as exc:
            logger.error(
                "[UpdateVulnerabilityFinding][%s] 更新失败: %s",
                self.task_id,
                exc,
                exc_info=True,
            )
            return ToolResult(
                success=False,
                error=str(exc),
                data={
                    "updated": False,
                    "finding_identity": finding_identity,
                    "message": f"更新失败: {exc}",
                },
            )
