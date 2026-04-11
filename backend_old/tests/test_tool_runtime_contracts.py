import json
import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel

class ReconRiskPointInput(BaseModel):
    file_path: str
    line_start: int
    description: str


class ReconRiskPointsBatchInput(BaseModel):
    risk_points: list[ReconRiskPointInput]


_CONTRACTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "agent"
    / "tools"
    / "runtime"
    / "contracts.py"
)
_SPEC = importlib.util.spec_from_file_location("tool_runtime_contracts", _CONTRACTS_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
ToolInputContractRegistry = _MODULE.ToolInputContractRegistry


def test_validate_and_dump_recursively_serializes_nested_pydantic_models():
    payload = {
        "risk_points": [
            {
                "file_path": "src/auth.py",
                "line_start": 42,
                "description": "Potential SQL injection",
                "severity": "high",
                "confidence": 0.9,
                "vulnerability_type": "sql_injection",
            }
        ]
    }

    validated = ToolInputContractRegistry.validate_and_dump(
        schema=ReconRiskPointsBatchInput,
        payload=payload,
    )

    assert isinstance(validated, dict)
    assert isinstance(validated["risk_points"], list)
    assert isinstance(validated["risk_points"][0], dict)
    assert validated["risk_points"][0]["file_path"] == "src/auth.py"

    encoded = json.dumps(validated, ensure_ascii=False)
    assert "\"file_path\": \"src/auth.py\"" in encoded
