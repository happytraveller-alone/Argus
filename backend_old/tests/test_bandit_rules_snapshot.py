"""Bandit 内置规则快照生成服务单元测试。"""

from pathlib import Path

import pytest

from app.services import bandit_rules_snapshot


def test_bandit_builtin_snapshot_path_prefers_rust_asset_root():
    expected = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "assets"
        / "scan_rule_assets"
        / "bandit_builtin"
        / "bandit_builtin_rules.json"
    )

    assert bandit_rules_snapshot._BANDIT_BUILTIN_JSON_PATH == expected


class _FakeDescriptor:
    def __init__(self, *, name: str, plugin: object):
        self.name = name
        self.plugin = plugin


class _FakePlugin:
    def __init__(
        self,
        *,
        test_id: str = "",
        name: str = "",
        doc: str = "",
        checks: list[str] | None = None,
    ):
        self._test_id = test_id
        self.__name__ = name
        self.__doc__ = doc
        self._checks = checks or []


class _FakeManager:
    def __init__(self, plugins):
        self.plugins = plugins


def test_build_bandit_builtin_snapshot_maps_fields_and_sorts():
    manager = _FakeManager(
        plugins=[
            _FakeDescriptor(
                name="z_source",
                plugin=_FakePlugin(
                    test_id="B602",
                    name="subprocess_popen_with_shell_equals_true",
                    doc="B602 summary\nline2",
                    checks=["Call", "Call"],
                ),
            ),
            _FakeDescriptor(
                name="a_source",
                plugin=_FakePlugin(
                    test_id="B101",
                    name="assert_used",
                    doc="",
                    checks=["Assert"],
                ),
            ),
            _FakeDescriptor(
                name="skip_no_id",
                plugin=_FakePlugin(
                    test_id="",
                    name="unknown_plugin",
                    doc="ignored",
                    checks=["Call"],
                ),
            ),
        ]
    )

    snapshot = bandit_rules_snapshot.build_bandit_builtin_snapshot(
        bandit_version="1.9.4",
        manager=manager,
        generated_at="2026-03-15T00:00:00+00:00",
    )

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["generated_at"] == "2026-03-15T00:00:00+00:00"
    assert snapshot["bandit_version"] == "1.9.4"
    assert snapshot["count"] == 2

    rules = snapshot["rules"]
    assert [rule["test_id"] for rule in rules] == ["B101", "B602"]
    assert rules[0]["description"] == ""
    assert rules[0]["description_summary"] == ""
    assert rules[1]["description_summary"] == "B602 summary"
    assert rules[1]["checks"] == ["Call"]
    assert rules[1]["source"] == "z_source"
    assert rules[1]["bandit_version"] == "1.9.4"


def test_build_bandit_builtin_snapshot_raises_when_bandit_import_failed(monkeypatch):
    def _fake_import_bandit_runtime():
        raise RuntimeError("Bandit runtime import failed: mocked")

    monkeypatch.setattr(
        bandit_rules_snapshot,
        "_import_bandit_runtime",
        _fake_import_bandit_runtime,
    )

    with pytest.raises(RuntimeError, match="Bandit runtime import failed"):
        bandit_rules_snapshot.build_bandit_builtin_snapshot()


def test_write_bandit_builtin_snapshot_no_file_created_when_build_failed(
    monkeypatch,
    tmp_path: Path,
):
    target_path = tmp_path / "bandit_builtin_rules.json"

    def _fake_build_snapshot():
        raise RuntimeError("mocked build failure")

    monkeypatch.setattr(
        bandit_rules_snapshot,
        "build_bandit_builtin_snapshot",
        _fake_build_snapshot,
    )

    with pytest.raises(RuntimeError, match="mocked build failure"):
        bandit_rules_snapshot.write_bandit_builtin_snapshot(target_path)

    assert not target_path.exists()


def test_update_bandit_builtin_snapshot_rule_updates_target_rule_atomically(tmp_path: Path):
    target_path = tmp_path / "bandit_builtin_rules.json"
    target_path.write_text(
        """{
  "schema_version": "1.0",
  "generated_at": "2026-03-16T00:00:00+00:00",
  "bandit_version": "1.9.4",
  "count": 1,
  "rules": [
    {
      "test_id": "B101",
      "name": "assert_used",
      "description": "old",
      "description_summary": "old summary",
      "checks": ["Assert"],
      "source": "builtin",
      "bandit_version": "1.9.4"
    }
  ]
}
""",
        encoding="utf-8",
    )

    updated = bandit_rules_snapshot.update_bandit_builtin_snapshot_rule(
        rule_id="b101",
        updates={
            "name": "assert_used_custom",
            "description_summary": "new summary",
            "description": "new description",
            "checks": ["Assert", "Call"],
        },
        snapshot_path=target_path,
    )

    payload = bandit_rules_snapshot.load_bandit_builtin_snapshot(target_path)
    assert updated["name"] == "assert_used_custom"
    assert payload["count"] == 1
    assert payload["rules"][0]["test_id"] == "B101"
    assert payload["rules"][0]["description_summary"] == "new summary"
    assert payload["rules"][0]["checks"] == ["Assert", "Call"]


def test_update_bandit_builtin_snapshot_rule_raises_when_rule_not_found(tmp_path: Path):
    target_path = tmp_path / "bandit_builtin_rules.json"
    target_path.write_text(
        '{"schema_version":"1.0","generated_at":"x","bandit_version":"1.9.4","count":0,"rules":[]}',
        encoding="utf-8",
    )

    with pytest.raises(KeyError, match="Bandit rule not found"):
        bandit_rules_snapshot.update_bandit_builtin_snapshot_rule(
            rule_id="B999",
            updates={"name": "x"},
            snapshot_path=target_path,
        )
