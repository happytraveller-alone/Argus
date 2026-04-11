"""YASA 规则快照服务与生成脚本测试。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.services import yasa_rules_snapshot


def _write_resource_dir(resource_dir: Path) -> None:
    checker_dir = resource_dir / "checker"
    checker_dir.mkdir(parents=True, exist_ok=True)
    (checker_dir / "checker-config.json").write_text(
        json.dumps(
            [
                {
                    "checkerId": "zz_rule",
                    "checkerPath": "checker/zz_rule.json",
                    "description": "z rule",
                    "demoRuleConfigPath": "example-rule-config/z.json",
                },
                {
                    "checkerId": "aa_rule",
                    "checkerPath": "checker/aa_rule.json",
                    "description": "a rule",
                    "demoRuleConfigPath": "example-rule-config/a.json",
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (checker_dir / "checker-pack-config.json").write_text(
        json.dumps(
            [
                {
                    "checkerPackId": "javascript-default",
                    "checkerIds": ["zz_rule", "aa_rule"],
                },
                {
                    "checkerPackId": "golang-default",
                    "checkerIds": ["aa_rule"],
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_yasa_rules_snapshot_maps_fields_and_sorts(tmp_path: Path):
    resource_dir = tmp_path / "resource"
    _write_resource_dir(resource_dir)

    snapshot = yasa_rules_snapshot.build_yasa_rules_snapshot(
        resource_dir=resource_dir,
        generated_at="2026-03-24T00:00:00+00:00",
    )

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["generated_at"] == "2026-03-24T00:00:00+00:00"
    assert snapshot["count"] == 2
    assert snapshot["checker_ids"] == ["aa_rule", "zz_rule"]
    assert snapshot["checker_pack_ids"] == ["golang-default", "javascript-default"]
    assert snapshot["pack_map"]["javascript-default"] == ["zz_rule", "aa_rule"]

    rules = snapshot["rules"]
    assert [item["checker_id"] for item in rules] == ["aa_rule", "zz_rule"]
    assert rules[0]["languages"] == ["javascript", "typescript", "golang"]
    assert rules[0]["demo_rule_config_path"] == "example-rule-config/a.json"


def test_load_yasa_checker_catalog_builds_sets_from_snapshot(tmp_path: Path):
    snapshot_path = tmp_path / "yasa_rules_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-03-24T00:00:00+00:00",
                "count": 1,
                "checker_ids": ["taint_flow_go_input"],
                "checker_pack_ids": ["golang-default"],
                "pack_map": {"golang-default": ["taint_flow_go_input"]},
                "rules": [
                    {
                        "checker_id": "taint_flow_go_input",
                        "checker_path": "checker/taint_flow_go_input.json",
                        "description": "go input",
                        "checker_packs": ["golang-default"],
                        "languages": ["golang"],
                        "demo_rule_config_path": "example-rule-config/go.json",
                        "source": "builtin",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = yasa_rules_snapshot.load_yasa_checker_catalog(snapshot_path)

    assert catalog["checker_ids"] == {"taint_flow_go_input"}
    assert catalog["checker_pack_ids"] == {"golang-default"}
    assert catalog["pack_map"] == {"golang-default": ["taint_flow_go_input"]}


def test_load_yasa_rules_snapshot_raises_when_snapshot_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="YASA 规则快照不存在"):
        yasa_rules_snapshot.load_yasa_rules_snapshot(tmp_path / "missing.json")


def test_repo_bundled_snapshot_exists_and_is_readable():
    payload = yasa_rules_snapshot.load_yasa_rules_snapshot()
    rules = yasa_rules_snapshot.extract_yasa_snapshot_rules()
    catalog = yasa_rules_snapshot.load_yasa_checker_catalog()

    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["generated_at"], str) and payload["generated_at"]
    assert payload["count"] > 0
    assert len(rules) == payload["count"]
    assert all(item["source"] == "builtin" for item in rules)
    assert catalog["checker_ids"]
    assert catalog["checker_pack_ids"]
    assert catalog["pack_map"]


def test_generate_yasa_rules_snapshot_script_writes_snapshot(tmp_path: Path):
    resource_dir = tmp_path / "resource"
    _write_resource_dir(resource_dir)
    output_path = tmp_path / "generated.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_yasa_rules_snapshot.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--resource-dir",
            str(resource_dir),
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "wrote YASA snapshot" in result.stdout
    assert payload["count"] == 2
    assert payload["rules"][0]["checker_id"] == "aa_rule"
