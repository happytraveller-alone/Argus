import logging
import yaml
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.schemas.opengrep import (
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
)
from app.db.session import get_db
from app.models.opengrep import OpengrepRule
from app.services.rule import get_rule_by_patch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/rules/create", response_model=OpengrepRulePatchResponse)
async def create_opengrep_rule(
    request: OpengrepRuleCreateRequest, db: AsyncSession = Depends(get_db)
):
    """
    创建一个新的 Opengrep 规则
    """
    result = await get_rule_by_patch(request)

    attempts = result.get("attempts", [])
    meta = result.get("meta", {})

    try:
        for attempt in attempts:
            rule = attempt.get("rule")
            validation = attempt.get("validation") or {}
            is_valid = bool(validation.get("is_valid"))
            message = validation.get("message")

            if rule:
                name = rule.get("id") or f"llm-attempt-{attempt.get('attempt', 0)}"
                languages = rule.get("languages") or []
                language = languages[0] if isinstance(languages, list) and languages else None
                language = language or meta.get("language") or "unknown"
                severity = rule.get("severity") or "ERROR"
                pattern_yaml = yaml.safe_dump({"rules": [rule]}, sort_keys=False)
            else:
                name = f"llm-attempt-{attempt.get('attempt', 0)}"
                language = meta.get("language") or "unknown"
                severity = "ERROR"
                pattern_yaml = yaml.safe_dump(
                    {"rules": [], "error": message or "LLM rule generation failed"},
                    sort_keys=False,
                )

            opengrep_rule = OpengrepRule(
                name=name,
                pattern_yaml=pattern_yaml,
                language=language,
                severity=severity,
                source="patch",
                patch=request.commit_content,
                correct=is_valid,
                is_active=is_valid,
            )
            db.add(opengrep_rule)

        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Failed to persist opengrep rule attempts: {e}")

    return result


