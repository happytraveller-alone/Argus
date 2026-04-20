from app.services.agent.task_models import AgentTask, AgentTaskPhase, AgentTaskStatus


def test_agent_task_models_module_exports_status_and_progress_behavior():
    task = AgentTask(
        name="demo",
        project_id="project-1",
        created_by="user-1",
        status=AgentTaskStatus.FAILED,
        current_phase=AgentTaskPhase.INDEXING,
        total_files=10,
        indexed_files=5,
    )

    assert task.status == AgentTaskStatus.FAILED
    assert 0 < task.progress_percentage < 100
