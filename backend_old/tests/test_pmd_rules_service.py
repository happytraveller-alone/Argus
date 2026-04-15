from pathlib import Path

import pytest

from app.services import pmd_rulesets
import app.services.agent.tools.external_tools as external_tools


SECURITY_RULESET = "category/java/security.xml,category/java/errorprone.xml,category/apex/security.xml"
QUICKSTART_RULESET = "category/java/security.xml,category/jsp/security.xml,category/javascript/security.xml"
ALL_RULESET = (
    "category/java/security.xml,"
    "category/jsp/security.xml,"
    "category/javascript/security.xml,"
    "category/html/security.xml,"
    "category/xml/security.xml,"
    "category/plsql/security.xml,"
    "category/apex/security.xml,"
    "category/visualforce/security.xml"
)


def test_build_pmd_presets_matches_tool_alias_contract():
    assert pmd_rulesets.PMD_RULESET_ALIASES == {
        "security": SECURITY_RULESET,
        "quickstart": QUICKSTART_RULESET,
        "all": ALL_RULESET,
    }
    assert external_tools.PMD_RULESET_ALIASES is pmd_rulesets.PMD_RULESET_ALIASES
    assert set(pmd_rulesets.PMD_PRESET_SUMMARIES) == {"security", "quickstart", "all"}
    assert pmd_rulesets.PMD_PRESET_SUMMARIES["security"]["alias"] == SECURITY_RULESET
    assert "java" in pmd_rulesets.PMD_PRESET_SUMMARIES["security"]["categories"]


def test_list_builtin_pmd_rulesets_reads_repo_xml_and_returns_metadata():
    expected_dir = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "assets"
        / "scan_rule_assets"
        / "rules_pmd"
    )

    assert pmd_rulesets.get_pmd_builtin_ruleset_dir() == expected_dir

    builtin_rulesets = pmd_rulesets.list_builtin_pmd_rulesets()
    assert len(builtin_rulesets) == 143

    hard_coded_crypto_key = next(
        item for item in builtin_rulesets if item["id"] == "HardCodedCryptoKey.xml"
    )
    java_empty_catch_block = next(
        item for item in builtin_rulesets if item["id"] == "JavaErrorProneEmptyCatchBlock.xml"
    )

    assert hard_coded_crypto_key["ruleset_name"] == "HardCodedCryptoKey Ruleset"
    assert hard_coded_crypto_key["rule_count"] == 1
    assert hard_coded_crypto_key["languages"] == ["java"]
    assert hard_coded_crypto_key["priorities"] == [3]
    assert hard_coded_crypto_key["external_info_urls"] == [
        "${pmd.website.baseurl}/pmd_rules_java_security.html#hardcodedcryptokey"
    ]
    assert "<ruleset" in hard_coded_crypto_key["raw_xml"]

    assert java_empty_catch_block["ruleset_name"] == "EmptyCatchBlock Ruleset"
    assert java_empty_catch_block["rule_count"] == 1
    assert java_empty_catch_block["languages"] == ["java"]
    assert java_empty_catch_block["priorities"] == [3]
    assert java_empty_catch_block["external_info_urls"] == [
        "${pmd.website.baseurl}/pmd_rules_java_errorprone.html#emptycatchblock"
    ]
    assert (
        java_empty_catch_block["rules"][0]["class_name"]
        == "net.sourceforge.pmd.lang.rule.xpath.XPathRule"
    )
    assert 'name="EmptyCatchBlock"' in java_empty_catch_block["raw_xml"]


def test_list_builtin_pmd_rulesets_separates_duplicate_rule_names_by_filename():
    builtin_rulesets = pmd_rulesets.list_builtin_pmd_rulesets()

    apex_empty_catch_block = next(
        item for item in builtin_rulesets if item["id"] == "ApexErrorProneEmptyCatchBlock.xml"
    )
    java_empty_catch_block = next(
        item for item in builtin_rulesets if item["id"] == "JavaErrorProneEmptyCatchBlock.xml"
    )

    assert apex_empty_catch_block["rules"][0]["name"] == "EmptyCatchBlock"
    assert java_empty_catch_block["rules"][0]["name"] == "EmptyCatchBlock"
    assert apex_empty_catch_block["languages"] == ["apex"]
    assert java_empty_catch_block["languages"] == ["java"]
    assert apex_empty_catch_block["external_info_urls"] == [
        "${pmd.website.baseurl}/pmd_rules_apex_errorprone.html#emptycatchblock"
    ]
    assert java_empty_catch_block["external_info_urls"] == [
        "${pmd.website.baseurl}/pmd_rules_java_errorprone.html#emptycatchblock"
    ]


def test_list_builtin_pmd_rulesets_includes_refreshed_existing_and_new_prefixed_rules():
    builtin_rulesets = pmd_rulesets.list_builtin_pmd_rulesets()

    apex_bad_crypto = next(item for item in builtin_rulesets if item["id"] == "ApexBadCrypto.xml")
    xml_mistyped_cdata = next(
        item for item in builtin_rulesets if item["id"] == "XmlErrorProneMistypedCDATASection.xml"
    )

    assert apex_bad_crypto["rules"][0]["class_name"] == (
        "net.sourceforge.pmd.lang.apex.rule.security.ApexBadCryptoRule"
    )
    assert apex_bad_crypto["rules"][0]["external_info_url"] == (
        "${pmd.website.baseurl}/pmd_rules_apex_security.html#apexbadcrypto"
    )
    assert xml_mistyped_cdata["rules"][0]["name"] == "MistypedCDATASection"
    assert xml_mistyped_cdata["languages"] == ["xml"]
    assert xml_mistyped_cdata["external_info_urls"] == [
        "${pmd.website.baseurl}/pmd_rules_xml_errorprone.html#mistypedcdatasection"
    ]


def test_parse_pmd_ruleset_tolerates_namespace_and_ref_rules():
    ruleset = pmd_rulesets.parse_pmd_ruleset_xml(
        """<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Apex Security"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <description>demo</description>
    <rule ref="category/apex/security.xml/ApexCRUDViolation" message="Validate CRUD permission">
        <priority>2</priority>
        <description>ref rule</description>
    </rule>
</ruleset>
""",
    )

    assert ruleset["ruleset_name"] == "Apex Security"
    assert ruleset["rule_count"] == 1
    assert ruleset["priorities"] == [2]
    assert ruleset["rules"][0]["name"] is None
    assert ruleset["rules"][0]["ref"] == "category/apex/security.xml/ApexCRUDViolation"
    assert ruleset["rules"][0]["message"] == "Validate CRUD permission"
    assert ruleset["rules"][0]["description"] == "ref rule"


def test_parse_pmd_ruleset_rejects_xml_without_rule_nodes():
    with pytest.raises(ValueError, match="至少包含一个 <rule>"):
        pmd_rulesets.parse_pmd_ruleset_xml(
            """<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Empty Ruleset"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <description>demo</description>
</ruleset>
""",
        )
