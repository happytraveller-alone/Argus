import pytest

from app.services.agent.tools.sandbox_runner_client import (
    SandboxRunResult,
    SandboxRunSpec,
)


def test_sandbox_run_spec_validation():
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["echo", "hello"],
        workspace_dir="/tmp/test",
    )
    assert spec.image == "alpine:latest"
    assert spec.network_mode == "none"
    assert "ALL" in spec.cap_drop
    assert spec.timeout_seconds == 60

    with pytest.raises(ValueError, match="image is required"):
        SandboxRunSpec(image="", command=[], workspace_dir="/tmp")

    with pytest.raises(ValueError, match="workspace_dir is required"):
        SandboxRunSpec(image="test", command=[], workspace_dir="")


def test_sandbox_run_result_serialization_and_output_flag():
    result = SandboxRunResult(
        success=True,
        exit_code=0,
        stdout="output",
        stderr="",
        image="alpine:latest",
    )

    data = result.to_dict()
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert data["stdout"] == "output"
    assert isinstance(data["image_candidates"], list)
    assert result.has_output is True
