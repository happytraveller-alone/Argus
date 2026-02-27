from app.api.v1.endpoints.agent_tasks import _compute_verification_pending_gate


def test_verification_pending_gate_triggered_when_pending_exists():
    payload = {
        "candidate_count": 3,
        "verification_todo_summary": {
            "total": 3,
            "pending": 1,
            "per_item_compact": [
                {"id": "todo-1", "status": "verified", "title": "A"},
                {"id": "todo-2", "status": "pending", "title": "B"},
                {"id": "todo-3", "status": "false_positive", "title": "C"},
            ],
        },
    }

    result = _compute_verification_pending_gate(payload)

    assert result["triggered"] is True
    assert result["candidate_count"] == 3
    assert result["pending_count"] == 1
    assert result["message"].startswith("verification_pending_gate:")
    assert result["pending_examples"] == [
        {"id": "todo-2", "status": "pending", "title": "B"}
    ]


def test_verification_pending_gate_uses_todo_list_fallback():
    payload = {
        "verification_todo_summary": {"total": 2, "pending": 0},
        "todo_list": [
            {"id": "todo-1", "status": "running", "title": "A"},
            {"id": "todo-2", "status": "false_positive", "title": "B"},
        ],
    }

    result = _compute_verification_pending_gate(payload)

    assert result["triggered"] is True
    assert result["candidate_count"] == 2
    assert result["pending_count"] == 1
    assert result["pending_examples"] == [
        {"id": "todo-1", "status": "running", "title": "A"}
    ]
