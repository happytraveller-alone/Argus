from __future__ import annotations

from pathlib import Path


DB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = DB_ROOT.parents[2]
RUST_SCAN_RULE_ASSETS_ROOT = REPO_ROOT / "backend" / "assets" / "scan_rule_assets"


def _prefer_rust_asset_dir(*, rust_name: str, legacy_name: str) -> Path:
    rust_path = RUST_SCAN_RULE_ASSETS_ROOT / rust_name
    if rust_path.exists():
        return rust_path
    return DB_ROOT / legacy_name


def opengrep_internal_rules_dir() -> Path:
    return _prefer_rust_asset_dir(rust_name="rules_opengrep", legacy_name="rules")


def opengrep_patch_rules_dir() -> Path:
    return _prefer_rust_asset_dir(
        rust_name="rules_from_patches",
        legacy_name="rules_from_patches",
    )


def opengrep_patch_artifacts_dir() -> Path:
    return _prefer_rust_asset_dir(rust_name="patches", legacy_name="patches")


def gitleaks_builtin_toml_path() -> Path:
    return _prefer_rust_asset_dir(
        rust_name="gitleaks_builtin",
        legacy_name="gitleaks_builtin",
    ) / "gitleaks-default.toml"


def bandit_builtin_snapshot_path() -> Path:
    return _prefer_rust_asset_dir(
        rust_name="bandit_builtin",
        legacy_name="bandit_builtin",
    ) / "bandit_builtin_rules.json"


def pmd_builtin_ruleset_dir() -> Path:
    return _prefer_rust_asset_dir(rust_name="rules_pmd", legacy_name="rules_pmd")


def phpstan_rules_snapshot_path() -> Path:
    return _prefer_rust_asset_dir(
        rust_name="rules_phpstan",
        legacy_name="rules_phpstan",
    ) / "phpstan_rules_combined.json"


def phpstan_rule_sources_root_path() -> Path:
    return _prefer_rust_asset_dir(
        rust_name="rules_phpstan",
        legacy_name="rules_phpstan",
    ) / "rule_sources"
