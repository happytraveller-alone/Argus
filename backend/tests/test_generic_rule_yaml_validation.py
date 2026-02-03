import asyncio

from app.services.rule import validate_generic_rule


TOP_LEVEL_LIST_RULE_YAML = """
- id: demo-rule-with-dash
  message: Detect demo usage
  severity: ERROR
  languages:
    - generic
  pattern: demo($X)
"""

WRAPPED_RULE_YAML = """
rules:
  - id: function-use-after-free
    message: Detect use-after-free
    severity: WARNING
    languages:
      - c
    pattern: free($X)
"""


def test_validate_generic_rule_accepts_top_level_list():
    result = asyncio.run(validate_generic_rule(TOP_LEVEL_LIST_RULE_YAML))

    assert result["validation"]["is_valid"] is True
    assert result["rule"]["id"] == "demo-rule-with-dash"


def test_validate_generic_rule_accepts_hyphen_rule_id():
    result = asyncio.run(validate_generic_rule(WRAPPED_RULE_YAML))

    assert result["validation"]["is_valid"] is True
    assert result["rule"]["id"] == "function-use-after-free"
