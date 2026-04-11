from types import SimpleNamespace

import pytest

from app.models.project import Project
from app.models.yasa import YasaFinding, YasaScanTask


def test_yasa_models_importable():
    assert YasaScanTask.__tablename__ == "yasa_scan_tasks"
    assert YasaFinding.__tablename__ == "yasa_findings"


def test_project_relationship_contains_yasa_scan_tasks():
    assert hasattr(Project, "yasa_scan_tasks")


def test_static_tasks_exports_yasa_contract():
    from app.api.v1.endpoints.static_tasks import (  # noqa: PLC0415
        YasaFindingResponse,
        YasaScanTaskCreate,
        YasaScanTaskResponse,
        _execute_yasa_scan,
    )

    assert YasaScanTaskCreate is not None
    assert YasaScanTaskResponse is not None
    assert YasaFindingResponse is not None
    assert callable(_execute_yasa_scan)


def test_yasa_resolve_language_profile_rejects_unsupported():
    from app.api.v1.endpoints.static_tasks_yasa import _resolve_language_profile  # noqa: PLC0415

    with pytest.raises(ValueError, match="不支持语言: php"):
        _resolve_language_profile("php")


def test_yasa_resolve_language_profile_rejects_empty():
    from app.api.v1.endpoints.static_tasks_yasa import _resolve_language_profile  # noqa: PLC0415

    with pytest.raises(ValueError, match="未检测到可用于 YASA 的项目语言"):
        _resolve_language_profile("")


def test_detect_language_supports_csv_and_json_string():
    from app.api.v1.endpoints.static_tasks_yasa import _detect_language_from_project  # noqa: PLC0415

    csv_project = SimpleNamespace(programming_languages="php,javascript")
    assert _detect_language_from_project(csv_project) == "javascript"

    json_project = SimpleNamespace(programming_languages='["php","javascript"]')
    assert _detect_language_from_project(json_project) == "javascript"

    unsupported_project = SimpleNamespace(programming_languages="php")
    assert _detect_language_from_project(unsupported_project) is None


def test_detect_language_prefers_source_tree_suffix(tmp_path):
    from app.api.v1.endpoints.static_tasks_yasa import _detect_language_from_project  # noqa: PLC0415

    (tmp_path / "main.py").write_text("print('x')", encoding="utf-8")
    project = SimpleNamespace(programming_languages='["java"]')
    assert _detect_language_from_project(project, project_root=str(tmp_path)) == "python"
