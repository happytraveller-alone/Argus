from app.services.agent.flow.joern.joern_client import JoernClient
from app.services.agent.flow.pipeline import FlowEvidencePipeline


def test_joern_client_initializes_codebadger_when_enabled():
    client = JoernClient(
        enabled=True,
        timeout_sec=45,
        mcp_enabled=True,
        mcp_url="http://codebadger-mcp:4242/mcp",
        mcp_prefer=True,
        mcp_cpg_timeout_sec=240,
        mcp_query_timeout_sec=90,
    )

    assert client._mcp_enabled is True
    assert client._mcp_prefer is True
    assert client._mcp_url == "http://codebadger-mcp:4242/mcp"
    assert client._mcp_cpg_timeout_sec == 240
    assert client._mcp_query_timeout_sec == 90
    assert client._mcp is not None


def test_flow_pipeline_passes_joern_mcp_settings(monkeypatch, tmp_path):
    captured = {}

    class _RecorderJoernClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.core.config.settings.FLOW_JOERN_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.FLOW_JOERN_TIMEOUT_SEC", 75)
    monkeypatch.setattr("app.core.config.settings.JOERN_MCP_ENABLED", True)
    monkeypatch.setattr(
        "app.core.config.settings.JOERN_MCP_URL",
        "http://codebadger-mcp:4242/mcp",
    )
    monkeypatch.setattr("app.core.config.settings.JOERN_MCP_PREFER", True)
    monkeypatch.setattr("app.core.config.settings.JOERN_MCP_CPG_TIMEOUT_SEC", 180)
    monkeypatch.setattr("app.core.config.settings.JOERN_MCP_QUERY_TIMEOUT_SEC", 60)
    monkeypatch.setattr(
        "app.services.agent.flow.pipeline.JoernClient",
        _RecorderJoernClient,
    )

    FlowEvidencePipeline(project_root=str(tmp_path))

    assert captured == {
        "enabled": True,
        "timeout_sec": 75,
        "mcp_enabled": True,
        "mcp_url": "http://codebadger-mcp:4242/mcp",
        "mcp_prefer": True,
        "mcp_cpg_timeout_sec": 180,
        "mcp_query_timeout_sec": 60,
    }
