"""PHPStan 规则快照写回辅助函数测试。"""

import json
from pathlib import Path

import pytest

from app.api.v1.endpoints import static_tasks


def test_update_phpstan_snapshot_rule_updates_target_rule(tmp_path: Path, monkeypatch):
    snapshot_path = tmp_path / "phpstan_rules_combined.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-03-16T00:00:00+00:00",
                "sources": ["official_extension"],
                "count": 1,
                "rules": [
                    {
                        "id": "pkg:RuleClass",
                        "package": "pkg",
                        "repo": "repo",
                        "rule_class": "RuleClass",
                        "name": "RuleClass",
                        "description_summary": "old",
                        "source_file": "src/RuleClass.php",
                        "source": "official_extension",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(static_tasks._phpstan, "_phpstan_rules_snapshot_path", lambda: snapshot_path)
    static_tasks._phpstan._update_phpstan_snapshot_rule(
        "pkg:RuleClass",
        {
            "name": "RuleClassCustom",
            "description_summary": "new summary",
        },
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rule = payload["rules"][0]
    assert rule["id"] == "pkg:RuleClass"
    assert rule["name"] == "RuleClassCustom"
    assert rule["description_summary"] == "new summary"
    assert payload["count"] == 1


def test_update_phpstan_snapshot_rule_raises_for_missing_rule(tmp_path: Path, monkeypatch):
    snapshot_path = tmp_path / "phpstan_rules_combined.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "x",
                "sources": ["official_extension"],
                "count": 0,
                "rules": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(static_tasks._phpstan, "_phpstan_rules_snapshot_path", lambda: snapshot_path)

    with pytest.raises(KeyError, match="PHPStan 规则不存在"):
        static_tasks._phpstan._update_phpstan_snapshot_rule("pkg:Nope", {"name": "x"})
