"""Schema validation tests for runner_input.schema.json.

These tests verify that:
  - Legacy runner inputs (no new fields) still validate cleanly.
  - New inputs with agent_kind/wire_api/api_key_env validate correctly.
  - Invalid enum values for agent_kind are rejected.
"""

import json
import pathlib

import jsonschema
import pytest

SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "schemas" / "runner_input.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())

# Minimal valid base input matching the schema's required fields.
_BASE_INPUT = {
    "contract_version": "argus-agentflow-p1/v1",
    "task_id": "task-test-1",
    "project_id": "project-test-1",
    "project_root": "/workspace/project",
    "target": "local",
    "topology_version": "p1-fixed-dag-v1",
    "audit_scope": {
        "target_files": ["src/main.rs"],
        "exclude_patterns": [],
        "target_vulnerabilities": ["authz"],
        "verification_level": "standard",
    },
    "output_dir": "/workspace/output/task-test-1",
    "llm": {
        "provider": "openai_compatible",
        "model": "gpt-4o",
        "base_url": None,
        "api_key_ref": None,
    },
    "resource_budget": {
        "max_cpu_cores": 2.0,
        "max_memory_mb": 4096,
        "max_duration_seconds": 3600,
        "max_concurrency": 2,
    },
}


def _make_input(**llm_overrides):
    """Return a deep-copied base input with the given llm overrides applied."""
    import copy
    inp = copy.deepcopy(_BASE_INPUT)
    inp["llm"].update(llm_overrides)
    return inp


def test_legacy_input_validates_without_new_fields():
    """A runner_input without agent_kind/wire_api/api_key_env must still validate."""
    legacy_input = _make_input()
    # Confirm none of the new keys are present.
    assert "agent_kind" not in legacy_input["llm"]
    assert "wire_api" not in legacy_input["llm"]
    assert "api_key_env" not in legacy_input["llm"]
    jsonschema.validate(legacy_input, SCHEMA)


def test_new_input_with_agent_kind_claude_validates():
    """A runner_input with agent_kind=claude, wire_api=messages, api_key_env set must validate."""
    new_input = _make_input(
        provider="anthropic_compatible",
        agent_kind="claude",
        wire_api="messages",
        api_key_env="ANTHROPIC_API_KEY",
    )
    jsonschema.validate(new_input, SCHEMA)


def test_new_input_with_agent_kind_codex_validates():
    """A runner_input with agent_kind=codex and wire_api=responses must validate."""
    new_input = _make_input(
        agent_kind="codex",
        wire_api="responses",
        api_key_env="OPENAI_API_KEY",
    )
    jsonschema.validate(new_input, SCHEMA)


def test_invalid_agent_kind_rejected():
    """agent_kind value not in enum must be rejected."""
    bad_input = _make_input(agent_kind="gpt-claude")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_input, SCHEMA)


def test_invalid_wire_api_rejected():
    """wire_api value not in enum must be rejected."""
    bad_input = _make_input(wire_api="grpc")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_input, SCHEMA)


def test_additional_properties_still_rejected():
    """additionalProperties: false on llm object must still reject unknown keys."""
    import copy
    bad_input = copy.deepcopy(_BASE_INPUT)
    bad_input["llm"]["unknown_field"] = "value"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_input, SCHEMA)
