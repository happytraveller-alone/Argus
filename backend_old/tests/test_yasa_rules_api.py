from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import projects_insights, static_tasks_yasa
from app.models.yasa import YasaRuleConfig


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, *, single=None):
        self.single = single
        self.added = []
        self.commit_calls = 0
        self.refresh_calls = 0

    async def execute(self, _stmt):
        return _ScalarOneOrNoneResult(self.single)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, _item):
        self.refresh_calls += 1


def _mock_user():
    return SimpleNamespace(id="u-1")


@pytest.mark.asyncio
async def test_list_yasa_rules_uses_snapshot_and_filters(monkeypatch):
    monkeypatch.setattr(
        static_tasks_yasa,
        "extract_yasa_snapshot_rules",
        lambda: [
            {
                "checker_id": "taint_flow_go_input",
                "checker_path": "checker/go.json",
                "description": "go",
                "checker_packs": ["golang-default"],
                "languages": ["golang"],
                "demo_rule_config_path": "example-rule-config/go.json",
                "source": "builtin",
            },
            {
                "checker_id": "js_xss",
                "checker_path": "checker/js.json",
                "description": "js",
                "checker_packs": ["javascript-default"],
                "languages": ["javascript", "typescript"],
                "demo_rule_config_path": "example-rule-config/js.json",
                "source": "builtin",
            },
        ],
    )

    rows = await static_tasks_yasa.list_yasa_rules(
        checker_pack_id=None,
        language="golang",
        keyword="taint",
        skip=0,
        limit=50,
        current_user=_mock_user(),
    )

    assert len(rows) == 1
    assert rows[0].checker_id == "taint_flow_go_input"


@pytest.mark.asyncio
async def test_import_yasa_rule_config_uses_snapshot_catalog(monkeypatch):
    monkeypatch.setattr(
        static_tasks_yasa,
        "load_yasa_checker_catalog",
        lambda: {
            "checker_ids": {"taint_flow_go_input"},
            "checker_pack_ids": {"golang-default"},
            "pack_map": {"golang-default": ["taint_flow_go_input"]},
        },
    )

    db = _FakeDb()
    created = await static_tasks_yasa.import_yasa_rule_config(
        name="custom-go",
        description="demo",
        language="golang",
        checker_pack_ids="golang-default",
        checker_ids=None,
        rule_config_json='[{"checkerIds":["taint_flow_go_input"]}]',
        rule_config_file=None,
        db=db,  # type: ignore[arg-type]
        current_user=_mock_user(),
    )

    assert created.name == "custom-go"
    assert db.commit_calls == 1
    assert db.refresh_calls == 1


@pytest.mark.asyncio
async def test_import_yasa_rule_config_rejects_codeql_payload_with_clear_message():
    db = _FakeDb()
    with pytest.raises(static_tasks_yasa.HTTPException) as exc_info:
        await static_tasks_yasa.import_yasa_rule_config(
            name="codeql-demo",
            description="demo",
            language="golang",
            checker_pack_ids=None,
            checker_ids=None,
            rule_config_json='import semmle.code.cpp.security.BufferAccess\nselect 1',
            rule_config_file=None,
            db=db,  # type: ignore[arg-type]
            current_user=_mock_user(),
        )

    assert exc_info.value.status_code == 400
    assert "CodeQL" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_yasa_rule_config_uses_snapshot_catalog(monkeypatch):
    monkeypatch.setattr(
        static_tasks_yasa,
        "load_yasa_checker_catalog",
        lambda: {
            "checker_ids": {"taint_flow_go_input"},
            "checker_pack_ids": {"golang-default"},
            "pack_map": {"golang-default": ["taint_flow_go_input"]},
        },
    )

    row = YasaRuleConfig(
        id="cfg-1",
        name="custom-go",
        description="demo",
        language="golang",
        checker_pack_ids="golang-default",
        checker_ids="taint_flow_go_input",
        rule_config_json='[{"checkerIds":["taint_flow_go_input"]}]',
        is_active=True,
        source="custom",
    )
    db = _FakeDb(single=row)

    updated = await static_tasks_yasa.update_yasa_rule_config(
        "cfg-1",
        static_tasks_yasa.YasaRuleConfigUpdateRequest(
            checker_ids=["taint_flow_go_input"],
            checker_pack_ids=["golang-default"],
        ),
        db=db,  # type: ignore[arg-type]
        current_user=_mock_user(),
    )

    assert updated.checker_ids == "taint_flow_go_input"
    assert updated.checker_pack_ids == "golang-default"
    assert db.commit_calls == 1
    assert db.refresh_calls == 1


@pytest.mark.asyncio
async def test_get_yasa_rule_total_uses_snapshot(monkeypatch):
    monkeypatch.setattr(
        projects_insights,
        "extract_yasa_snapshot_rules",
        lambda: [{"checker_id": "a"}, {"checker_id": "b"}],
    )

    total = await projects_insights._get_yasa_rule_total()

    assert total == 2


@pytest.mark.asyncio
async def test_list_yasa_rules_returns_http_500_when_snapshot_missing(monkeypatch):
    def _raise_missing():
        raise FileNotFoundError("YASA 规则快照不存在: /tmp/missing.json")

    monkeypatch.setattr(static_tasks_yasa, "extract_yasa_snapshot_rules", _raise_missing)

    with pytest.raises(static_tasks_yasa.HTTPException) as exc_info:
        await static_tasks_yasa.list_yasa_rules(
            checker_pack_id=None,
            language=None,
            keyword=None,
            skip=0,
            limit=50,
            current_user=_mock_user(),
        )

    assert exc_info.value.status_code == 500
    assert "YASA 规则快照不存在" in str(exc_info.value.detail)
