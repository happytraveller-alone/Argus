from app.services.agent.core.registry import AgentRegistry


def test_agent_registry_scopes_tree_by_task_and_inherits_child_task_id():
    registry = AgentRegistry()

    registry.register_agent(
        agent_id="agent-root-1",
        agent_name="Orchestrator",
        agent_type="orchestrator",
        task="root task 1",
        task_id="task-1",
    )
    registry.register_agent(
        agent_id="agent-child-1",
        agent_name="Recon",
        agent_type="recon",
        task="child task 1",
        parent_id="agent-root-1",
    )
    registry.register_agent(
        agent_id="agent-root-2",
        agent_name="Orchestrator",
        agent_type="orchestrator",
        task="root task 2",
        task_id="task-2",
    )

    task_one_tree = registry.get_agent_tree(task_id="task-1")
    assert task_one_tree["root_agent_id"] == "agent-root-1"
    assert set(task_one_tree["nodes"].keys()) == {"agent-root-1", "agent-child-1"}
    assert task_one_tree["nodes"]["agent-root-1"]["children"] == ["agent-child-1"]
    assert task_one_tree["nodes"]["agent-child-1"]["task_id"] == "task-1"

    task_one_stats = registry.get_statistics(task_id="task-1")
    assert task_one_stats["total"] == 2
    assert task_one_stats["running"] == 2
    assert registry.get_root_agent_id(agent_id="agent-child-1") == "agent-root-1"

    cleared = registry.clear_task("task-1")
    assert cleared == 2
    assert set(registry.get_agent_tree()["nodes"].keys()) == {"agent-root-2"}
    assert registry.get_agent_tree(task_id="task-1")["nodes"] == {}
