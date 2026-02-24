from pathlib import Path

from app.services.agent.mcp.write_scope import HARD_MAX_WRITABLE_FILES_PER_TASK, TaskWriteScopeGuard


def test_write_scope_rejects_non_allowlist_without_binding(tmp_path: Path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path))

    decision = guard.evaluate_write_request(
        tool_name="write_file",
        tool_input={"file_path": "src/new_file.py", "content": "print(1)"},
    )

    assert decision.allowed is False
    assert decision.reason == "write_scope_not_allowed"


def test_write_scope_rejects_directory_wildcard_and_outside_path(tmp_path: Path):
    guard = TaskWriteScopeGuard(project_root=str(tmp_path))

    wildcard = guard.evaluate_write_request(
        tool_name="edit_file",
        tool_input={"file_path": "src/**/*.py", "reason": "fix"},
    )
    outside = guard.evaluate_write_request(
        tool_name="edit_file",
        tool_input={"file_path": "/etc/passwd", "reason": "fix"},
    )
    directory = guard.evaluate_write_request(
        tool_name="edit_file",
        tool_input={"file_path": "src", "reason": "fix"},
    )

    assert wildcard.allowed is False
    assert wildcard.reason == "write_scope_path_forbidden"
    assert outside.allowed is False
    assert outside.reason == "write_scope_path_forbidden"
    assert directory.allowed is False
    assert directory.reason == "write_scope_path_forbidden"


def test_write_scope_rejects_new_files_after_hard_limit(tmp_path: Path):
    guard = TaskWriteScopeGuard(
        project_root=str(tmp_path),
        max_writable_files_per_task=HARD_MAX_WRITABLE_FILES_PER_TASK,
    )

    for idx in range(HARD_MAX_WRITABLE_FILES_PER_TASK):
        assert guard.register_evidence_path(f"src/file_{idx}.py") is True

    limit_hit = guard.evaluate_write_request(
        tool_name="write_file",
        tool_input={
            "file_path": "src/overflow.py",
            "content": "print('x')",
            "reason": "verification patch",
            "finding_id": "finding-1",
        },
    )

    assert limit_hit.allowed is False
    assert limit_hit.reason == "write_scope_limit_reached"
    assert limit_hit.total_files == HARD_MAX_WRITABLE_FILES_PER_TASK

    existing_ok = guard.evaluate_write_request(
        tool_name="write_file",
        tool_input={
            "file_path": "src/file_1.py",
            "content": "print('y')",
        },
    )
    assert existing_ok.allowed is True
    assert existing_ok.reason == "write_scope_allowed"
