from pathlib import Path

import pytest

from app.api.v1.endpoints.agent_tasks import _enrich_findings_with_flow_and_logic
from app.services.agent.flow.joern.joern_client import JoernClient
from app.services.agent.logic.authz_rules import AuthzRuleEngine
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_flow_enrichment_on_partial_code_degrades_to_likely(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "service.py").write_text(
        """
from flask import request

def vulnerable_handler():
    cmd = request.args.get('cmd')
    run(cmd)
""",
        encoding="utf-8",
    )

    findings = [
        {
            "title": "Potential command injection",
            "severity": "high",
            "confidence": 0.9,
            "vulnerability_type": "command_injection",
            "file_path": "src/service.py",
            "line_start": 6,
            "line_end": 6,
            "authenticity": "confirmed",
        }
    ]

    enriched, summary = await _enrich_findings_with_flow_and_logic(
        findings,
        project_root=str(tmp_path),
        target_files=None,
        event_emitter=None,
    )

    assert len(enriched) == 1
    assert summary.get("total") == 1
    flow = enriched[0]["verification_result"]["flow"]
    assert isinstance(flow, dict)
    assert "path_score" in flow
    # unreachable policy should downgrade confirmed to likely when no path
    if not flow.get("path_found"):
        assert enriched[0].get("authenticity") == "likely"


@pytest.mark.asyncio
async def test_flow_enrichment_supports_cpp_call_chain(tmp_path: Path):
    (tmp_path / "main.cpp").write_text(
        """
#include <iostream>

void sink(const char* s) {
  std::system(s);
}

void bridge(const char* s) {
  sink(s);
}

int main(int argc, char** argv) {
  if (argc > 1) {
    bridge(argv[1]);
  }
  return 0;
}
""",
        encoding="utf-8",
    )

    findings = [
        {
            "title": "Potential command injection",
            "severity": "critical",
            "confidence": "HIGH",
            "vulnerability_type": "command_injection",
            "file_path": "main.cpp",
            "line_start": 5,
            "line_end": 5,
        }
    ]

    enriched, _ = await _enrich_findings_with_flow_and_logic(
        findings,
        project_root=str(tmp_path),
        target_files=None,
        event_emitter=None,
    )

    flow = enriched[0]["verification_result"]["flow"]
    chain = flow.get("call_chain") or []
    assert isinstance(chain, list)
    assert len(chain) >= 1


@pytest.mark.asyncio
async def test_flow_enrichment_entry_points_passthrough_sets_entry_inferred_false(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "\n".join(
            [
                "def start():",
                "    bridge()",
                "",
                "def bridge():",
                "    sink()",
                "",
                "def sink():",
                "    eval(\"1\")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    findings = [
        {
            "title": "Potential command injection",
            "severity": "high",
            "confidence": 0.8,
            "vulnerability_type": "command_injection",
            "file_path": "app.py",
            "line_start": 8,
            "line_end": 8,
            "entry_points": ["start"],
        }
    ]

    enriched, _ = await _enrich_findings_with_flow_and_logic(
        findings,
        project_root=str(tmp_path),
        target_files=None,
        event_emitter=None,
    )

    flow = enriched[0]["verification_result"]["flow"]
    assert flow.get("entry_inferred") is False
    chain = flow.get("call_chain") or []
    assert isinstance(chain, list) and chain
    assert chain[0].endswith(":start")


@pytest.mark.asyncio
async def test_joern_client_graceful_fallback_when_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.flow.joern.joern_client.shutil.which",
        lambda _name: None,
    )
    client = JoernClient(enabled=True, timeout_sec=5)

    evidence = await client.verify_reachability(
        project_root="/tmp/project",
        file_path="a.py",
        line_start=10,
        call_chain=["entry", "sink"],
    )

    assert evidence.engine == "joern"
    assert evidence.path_found is False
    assert "joern_not_available" in (evidence.blocked_reasons or [])


def test_logic_authz_rule_engine_detects_missing_authz_and_idor(tmp_path: Path):
    app_file = tmp_path / "app.py"
    app_file.write_text(
        """
from flask import Flask, request
app = Flask(__name__)

@app.route('/users/<id>', methods=['GET'])
def get_user(id):
    user_id = request.args.get('id')
    return db.users.find_by_id(user_id)
""",
        encoding="utf-8",
    )

    engine = AuthzRuleEngine(project_root=str(tmp_path), target_files=None)
    finding_result = engine.analyze_finding(
        {
            "file_path": "app.py",
            "line_start": 6,
            "vulnerability_type": "idor",
        }
    )

    assert finding_result["missing_authz_checks"] is True
    assert finding_result["idor_path"] is True
    assert finding_result["evidence"]
