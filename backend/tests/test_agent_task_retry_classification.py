import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401

from app.api.v1.endpoints.agent_tasks import _classify_retry_error


def test_classify_retry_error_timeout_is_retryable():
    result = _classify_retry_error("tool timeout after 30s")
    assert result["code"] == "timeout_error"
    assert result["retryable"] is True


def test_classify_retry_error_schema_is_non_retryable():
    result = _classify_retry_error("pydantic ValidationError: field type_error")
    assert result["code"] == "schema_hard_error"
    assert result["retryable"] is False


def test_classify_retry_error_repairable_validation_is_retryable():
    result = _classify_retry_error("工具参数校验失败: 必须提供 keyword")
    assert result["code"] == "repairable_validation_error"
    assert result["retryable"] is True


def test_classify_retry_error_scope_permission_is_non_retryable():
    result = _classify_retry_error("写入被拒绝：路径不在允许范围")
    assert result["code"] == "permission_or_scope_error"
    assert result["retryable"] is False
