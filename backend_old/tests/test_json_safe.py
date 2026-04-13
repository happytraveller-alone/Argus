import json

from pydantic import BaseModel

from app.services.agent.json_safe import dump_json_safe, normalize_json_safe


class ReconRiskPointInput(BaseModel):
    file_path: str
    line_start: int
    description: str


class ReconRiskPointsBatchInput(BaseModel):
    risk_points: list[ReconRiskPointInput]


def test_normalize_json_safe_recursively_serializes_nested_pydantic_models():
    payload = ReconRiskPointsBatchInput(
        risk_points=[
            ReconRiskPointInput(
                file_path="src/auth.py",
                line_start=42,
                description="Potential SQL injection",
            )
        ]
    )

    normalized = normalize_json_safe(
        {
            "risk_points": payload.risk_points,
        }
    )

    assert normalized == {
        "risk_points": [
            {
                "file_path": "src/auth.py",
                "line_start": 42,
                "description": "Potential SQL injection",
            }
        ]
    }


def test_dump_json_safe_serializes_nested_pydantic_models_without_type_error():
    payload = {
        "risk_points": [
            ReconRiskPointInput(
                file_path="src/auth.py",
                line_start=42,
                description="Potential SQL injection",
            )
        ]
    }

    encoded = dump_json_safe(payload, ensure_ascii=False, sort_keys=True)

    assert json.loads(encoded) == {
        "risk_points": [
            {
                "file_path": "src/auth.py",
                "line_start": 42,
                "description": "Potential SQL injection",
            }
        ]
    }
