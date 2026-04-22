import json
import subprocess
from pathlib import Path

from app.services.agent.finding_payload_runtime import FindingPayloadRuntimeBridge


def test_finding_payload_runtime_bridge_writes_request_and_reads_response(monkeypatch, tmp_path):
    seen = {}

    def _fake_run(args, *, capture_output, text, check, timeout):
        assert capture_output is True
        assert text is True
        assert check is False
        seen["args"] = list(args)
        seen["timeout"] = timeout
        request_path = Path(args[4])
        seen["request"] = json.loads(request_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "normalized_payload": {
                        "file_path": "src/auth.py",
                        "line_start": 18,
                        "title": "SQL injection",
                        "description": "bad",
                        "vulnerability_type": "sql_injection",
                    },
                    "repair_map": {"line": "line_start"},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.finding_payload_runtime.subprocess.run",
        _fake_run,
    )

    bridge = FindingPayloadRuntimeBridge(timeout_seconds=33)
    normalized, repair_map = bridge.normalize_payload(
        {
            "finding": {
                "file_path": "src/auth.py",
                "line": 18,
                "title": "SQL injection",
                "description": "bad",
                "vulnerability_type": "sql_injection",
            }
        }
    )

    assert seen["args"][1:4] == ["finding-payload", "normalize", "--request"]
    assert seen["timeout"] == 33
    assert seen["request"] == {
        "payload": {
            "finding": {
                "file_path": "src/auth.py",
                "line": 18,
                "title": "SQL injection",
                "description": "bad",
                "vulnerability_type": "sql_injection",
            }
        },
        "ordering": {
            "payload": ["finding"],
            "payload.finding": [
                "file_path",
                "line",
                "title",
                "description",
                "vulnerability_type",
            ],
        },
    }
    assert normalized["line_start"] == 18
    assert repair_map == {"line": "line_start"}


def test_finding_payload_runtime_bridge_serializes_non_json_extra_values(monkeypatch):
    seen = {}

    def _fake_run(args, *, capture_output, text, check, timeout):
        assert capture_output is True
        assert text is True
        assert check is False
        _ = timeout
        request_path = Path(args[4])
        seen["request"] = json.loads(request_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "normalized_payload": {
                        "file_path": "src/auth.py",
                        "title": "SQL injection",
                        "description": "bad",
                        "vulnerability_type": "sql_injection",
                        "finding_metadata": {
                            "extra_tool_input": {"custom_extra": "demo.txt"}
                        },
                    },
                    "repair_map": {
                        "__extra.custom_extra": "finding_metadata.extra_tool_input.custom_extra"
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.finding_payload_runtime.subprocess.run",
        _fake_run,
    )

    bridge = FindingPayloadRuntimeBridge(timeout_seconds=33)
    normalized, repair_map = bridge.normalize_payload(
        {
            "file_path": "src/auth.py",
            "title": "SQL injection",
            "description": "bad",
            "vulnerability_type": "sql_injection",
            "custom_extra": Path("demo.txt"),
        }
    )

    assert seen["request"]["payload"]["custom_extra"] == "demo.txt"
    assert normalized["finding_metadata"]["extra_tool_input"]["custom_extra"] == "demo.txt"
    assert repair_map["__extra.custom_extra"] == "finding_metadata.extra_tool_input.custom_extra"


def test_finding_payload_runtime_bridge_raises_when_binary_is_missing(monkeypatch):
    def _fake_run(*args, **kwargs):
        _ = args, kwargs
        raise OSError("backend runtime startup missing")

    monkeypatch.setattr(
        "app.services.agent.finding_payload_runtime.subprocess.run",
        _fake_run,
    )

    bridge = FindingPayloadRuntimeBridge(timeout_seconds=10)
    try:
        bridge.normalize_payload({"line": 8})
    except RuntimeError as error:
        assert "finding_payload_runtime_unavailable" in str(error)
    else:
        raise AssertionError("expected runtime bridge failure to raise")
