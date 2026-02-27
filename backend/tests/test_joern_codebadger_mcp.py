import base64
import json

import pytest

from app.services.agent.flow.joern.joern_client import JoernClient
from app.services.agent.flow.joern.codebadger_poc_query import parse_codebadger_query_data
from app.services.agent.flow.joern.codebadger_reachability_query import build_reachability_cpgql_query


@pytest.mark.asyncio
async def test_reachability_engine_selection_no_local_joern_mcp_enabled_but_unreachable(monkeypatch):
    monkeypatch.setattr("app.services.agent.flow.joern.joern_client.shutil.which", lambda _name: None)

    client = JoernClient(enabled=True, timeout_sec=5, mcp_enabled=True, mcp_url="http://127.0.0.1:4242/mcp")
    evidence = await client.verify_reachability(
        project_root="/tmp/deepaudit/test",
        file_path="src/App.java",
        line_start=10,
        call_chain=["src/app.py:handler"],
    )

    assert evidence.path_found is False
    assert "joern_not_available" in (evidence.blocked_reasons or [])


def test_codebadger_reachability_query_builder_payload_safe():
    query = build_reachability_cpgql_query(
        file_path="src/app.py",
        line_start=12,
        sink_hint="a\"b\\\\c",
        max_nodes=80,
    )
    assert "<codebadger_result>" in query
    assert query.strip().startswith("{")
    assert query.strip().endswith("}")
    assert ".toString()" in query.strip()[-120:]

    marker = 'java.util.Base64.getDecoder.decode("'
    start = query.find(marker)
    assert start != -1, "payload base64 marker not found in query"
    start += len(marker)
    end = query.find('")', start)
    assert end != -1, "payload base64 terminator not found in query"

    payload_b64 = query[start:end]
    payload_json = base64.b64decode(payload_b64.encode("ascii")).decode("utf-8")
    payload = json.loads(payload_json)
    assert payload["hint"] == 'a"b\\\\c'


def test_codebadger_parse_logic_handles_list_of_json_string():
    payload = {
        "version": 1,
        "engine": "joern_dataflow",
        "results": {"k1": {"nodes": []}},
        "errors": {"k2": "no_flow"},
    }
    data = [json.dumps(payload, ensure_ascii=False)]
    parsed = parse_codebadger_query_data(data)
    assert parsed == payload
