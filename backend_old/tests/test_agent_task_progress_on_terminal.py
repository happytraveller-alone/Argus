from app.models.agent_task import AgentTask, AgentTaskPhase, AgentTaskStatus
import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401


def test_progress_percentage_cancelled_keeps_phase_progress():
    task = AgentTask(
        id="task-cancelled",
        project_id="project-1",
        created_by="user-1",
        status=AgentTaskStatus.CANCELLED,
        current_phase=AgentTaskPhase.ANALYSIS,
        total_files=20,
        analyzed_files=8,
    )

    progress = task.progress_percentage
    assert progress > 0.0
    assert progress < 100.0


def test_progress_percentage_failed_keeps_phase_progress():
    task = AgentTask(
        id="task-failed",
        project_id="project-1",
        created_by="user-1",
        status=AgentTaskStatus.FAILED,
        current_phase=AgentTaskPhase.INDEXING,
        total_files=10,
        indexed_files=6,
    )

    progress = task.progress_percentage
    assert progress > 0.0
    assert progress < 100.0
