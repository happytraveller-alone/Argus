from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.endpoints import static_tasks


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _mock_user():
    return SimpleNamespace(id="u-1")


def _build_upload(filename: str, content: str) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content.encode("utf-8")))


@pytest.mark.asyncio
async def test_list_pmd_presets_returns_shared_service_payload():
    rows = await static_tasks.list_pmd_presets(current_user=_mock_user())

    assert [row["id"] for row in rows] == ["security", "quickstart", "all"]
    assert rows[0]["alias"] == static_tasks._pmd.PMD_RULESET_ALIASES["security"]
    assert "description" in rows[0]
    assert "categories" in rows[0]


@pytest.mark.asyncio
async def test_list_builtin_pmd_rulesets_filters_keyword_and_language(monkeypatch):
    captured = {}

    def _fake_list_builtin_pmd_rulesets(*, keyword=None, language=None, limit=None):
        captured.update(
            {
                "keyword": keyword,
                "language": language,
                "limit": limit,
            }
        )
        return [
            {
                "id": "HardCodedCryptoKey.xml",
                "ruleset_name": "HardCodedCryptoKey Ruleset",
                "languages": ["java"],
                "rule_count": 1,
                "priorities": [3],
                "external_info_urls": ["https://example.test/hardcodedcryptokey"],
                "rules": [{"name": "HardCodedCryptoKey"}],
                "raw_xml": "<ruleset />",
                "source": "builtin",
            }
        ]

    monkeypatch.setattr(
        static_tasks._pmd,
        "service_list_builtin_pmd_rulesets",
        _fake_list_builtin_pmd_rulesets,
    )

    rows = await static_tasks.list_builtin_pmd_rulesets(
        keyword="crypto",
        language="java",
        limit=10,
        current_user=_mock_user(),
    )

    assert captured == {"keyword": "crypto", "language": "java", "limit": 10}
    assert len(rows) == 1
    assert rows[0]["id"] == "HardCodedCryptoKey.xml"


@pytest.mark.asyncio
async def test_get_builtin_pmd_ruleset_returns_raw_xml_and_rule_details(monkeypatch):
    monkeypatch.setattr(
        static_tasks._pmd,
        "service_get_builtin_pmd_ruleset_detail",
        lambda ruleset_id: {
            "id": ruleset_id,
            "ruleset_name": "HardCodedCryptoKey Ruleset",
            "rule_count": 1,
            "languages": ["java"],
            "priorities": [3],
            "external_info_urls": ["https://example.test/hardcodedcryptokey"],
            "rules": [
                {
                    "name": "HardCodedCryptoKey",
                    "ref": None,
                    "language": "java",
                    "message": "Do not use hard coded encryption keys",
                    "class_name": "net.sourceforge.pmd.lang.java.rule.security.HardCodedCryptoKeyRule",
                    "priority": 3,
                    "since": "6.4.0",
                    "external_info_url": "https://example.test/hardcodedcryptokey",
                    "description": "Avoid hard coded crypto keys.",
                }
            ],
            "raw_xml": "<ruleset name='HardCodedCryptoKey Ruleset' />",
            "source": "builtin",
        },
    )

    detail = await static_tasks.get_builtin_pmd_ruleset(
        "HardCodedCryptoKey.xml",
        current_user=_mock_user(),
    )

    assert detail["id"] == "HardCodedCryptoKey.xml"
    assert detail["rule_count"] == 1
    assert detail["rules"][0]["name"] == "HardCodedCryptoKey"
    assert detail["raw_xml"].startswith("<ruleset")


@pytest.mark.asyncio
async def test_import_pmd_rule_config_validates_xml_and_persists_record():
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with pytest.raises(HTTPException) as invalid_ext_exc:
        await static_tasks.import_pmd_rule_config(
            name="invalid",
            description="demo",
            xml_file=_build_upload("invalid.txt", "<ruleset />"),
            db=db,
            current_user=_mock_user(),
        )
    assert invalid_ext_exc.value.status_code == 400

    created = await static_tasks.import_pmd_rule_config(
        name="custom-pmd",
        description="demo",
        xml_file=_build_upload(
            "custom.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Custom PMD Ruleset"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <rule name="CustomRule" language="java" message="demo">
        <description>demo</description>
        <priority>2</priority>
    </rule>
</ruleset>
""",
        ),
        db=db,
        current_user=_mock_user(),
    )

    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()
    added_row = db.add.call_args.args[0]
    assert added_row.name == "custom-pmd"
    assert added_row.filename == "custom.xml"
    assert created["source"] == "custom"
    assert created["ruleset_name"] == "Custom PMD Ruleset"
    assert created["rule_count"] == 1


@pytest.mark.asyncio
async def test_update_pmd_rule_config_only_updates_metadata_fields():
    row = SimpleNamespace(
        id="cfg-1",
        name="old-name",
        description="old-description",
        filename="custom.xml",
        xml_content="""<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Existing Ruleset"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <rule name="ExistingRule" language="java" message="demo">
        <description>demo</description>
        <priority>3</priority>
    </rule>
</ruleset>
""",
        is_active=True,
        created_by="u-1",
        created_at=None,
        updated_at=None,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(row))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    updated = await static_tasks.update_pmd_rule_config(
        "cfg-1",
        static_tasks._pmd.PmdRuleConfigUpdateRequest(
            name="renamed",
            description="new-description",
            is_active=False,
        ),
        db=db,
        current_user=_mock_user(),
    )

    assert row.name == "renamed"
    assert row.description == "new-description"
    assert row.is_active is False
    assert row.filename == "custom.xml"
    assert "ExistingRule" in row.xml_content
    assert updated["filename"] == "custom.xml"
    assert updated["rule_count"] == 1


@pytest.mark.asyncio
async def test_delete_pmd_rule_config_removes_record():
    row = SimpleNamespace(id="cfg-1")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(row))
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    result = await static_tasks.delete_pmd_rule_config(
        "cfg-1",
        db=db,
        current_user=_mock_user(),
    )

    db.delete.assert_awaited_once_with(row)
    db.commit.assert_awaited_once()
    assert result == {"message": "规则配置已删除", "id": "cfg-1"}
