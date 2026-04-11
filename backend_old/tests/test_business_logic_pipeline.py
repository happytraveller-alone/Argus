from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent.agents.business_logic_analysis import BusinessLogicAnalysisAgent
from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue
from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
from app.services.agent.workflow.engine import AuditWorkflowEngine


TASK_ID = "bl-task-001"


class TestBusinessLogicRiskQueueDedup:
    def test_enqueue_skips_duplicates(self):
        queue = InMemoryBusinessLogicRiskQueue()
        risk_point = {
            "file_path": "app/api/orders.py",
            "line_start": 42,
            "description": "order update without ownership check",
            "vulnerability_type": "idor",
        }

        first = queue.enqueue(TASK_ID, dict(risk_point))
        second = queue.enqueue(TASK_ID, dict(risk_point))

        assert first is True
        assert second is False
        assert queue.size(TASK_ID) == 1
        assert queue.stats(TASK_ID)["total_deduplicated"] == 1

    def test_enqueue_batch_counts_only_unique_items(self):
        queue = InMemoryBusinessLogicRiskQueue()
        batch = [
            {
                "file_path": "app/api/orders.py",
                "line_start": 42,
                "description": "risk-1",
                "vulnerability_type": "idor",
            },
            {
                "file_path": "app/api/orders.py",
                "line_start": 42,
                "description": "risk-1 duplicate",
                "vulnerability_type": "idor",
            },
            {
                "file_path": "app/api/orders.py",
                "line_start": 55,
                "description": "risk-2",
                "vulnerability_type": "state_machine_bypass",
            },
        ]

        enqueued = queue.enqueue_batch(TASK_ID, batch)

        assert enqueued == 2
        assert queue.size(TASK_ID) == 2
        assert queue.stats(TASK_ID)["total_deduplicated"] == 1


class TestBusinessLogicAnalysisAgent:
    @pytest.mark.asyncio
    async def test_analysis_collects_findings_and_context_pack(self):
        agent = BusinessLogicAnalysisAgent(
            llm_service=MagicMock(),
            tools={},
            event_emitter=None,
        )

        responses = [
            (
                "Thought: 先读取上下文\n"
                "Action: read_file\n"
                "Action Input: {\"file_path\": \"app/api/orders.py\", \"start_line\": 10, \"end_line\": 120}",
                11,
            ),
            (
                "Thought: 已确认存在越权\n"
                "Action: push_finding_to_queue\n"
                "Action Input: {"
                "\"file_path\": \"app/api/orders.py\", "
                "\"line_start\": 42, "
                "\"line_end\": 55, "
                "\"title\": \"app/api/orders.py中update_order函数IDOR越权漏洞\", "
                "\"description\": \"update_order 未验证订单归属。\", "
                "\"vulnerability_type\": \"idor\", "
                "\"severity\": \"high\", "
                "\"confidence\": 0.92, "
                "\"function_name\": \"update_order\", "
                "\"source\": \"request.path_params['order_id']\", "
                "\"sink\": \"Order.query.get(order_id)\", "
                "\"attacker_flow\": \"PUT /api/orders/2 -> update_order -> Order.query.get(2)\", "
                "\"evidence_chain\": [\"read_file\", \"search_code\"], "
                "\"finding_metadata\": {"
                "\"sink_reachable\": true, "
                "\"upstream_call_chain\": [\"PUT /api/orders/{order_id}\", \"update_order(order_id)\", \"Order.query.get(order_id)\"], "
                "\"sink_trigger_condition\": \"攻击者可以控制 order_id，且路径上不存在 owner 校验\""
                "}"
                "}",
                17,
            ),
            ("Thought: 分析完成\nFinal Answer: 已完成。", 5),
        ]
        agent.stream_llm_call = AsyncMock(side_effect=responses)

        async def fake_execute_tool(tool_name, tool_input):
            if tool_name == "read_file":
                return "order = Order.query.get(order_id)\n# no ownership check"
            if tool_name == "push_finding_to_queue":
                return "{\"message\": \"漏洞已入队\"}"
            return "{}"

        agent.execute_tool = fake_execute_tool

        result = await agent.run(
            {
                "risk_point": {
                    "file_path": "app/api/orders.py",
                    "line_start": 42,
                    "description": "update_order 通过请求参数获取 order_id",
                    "vulnerability_type": "idor",
                    "entry_function": "update_order",
                    "context": "PUT /api/orders/{order_id}",
                    "auth_context": "@login_required",
                    "object_type": "order",
                    "sensitive_action": "update",
                    "related_symbols": ["Order", "OrderService"],
                    "evidence_refs": ["app/api/orders.py:42"],
                },
                "context_pack": {
                    "route": "/api/orders/{order_id}",
                    "http_method": "PUT",
                    "auth_context": "@login_required",
                },
            }
        )

        assert result.success is True
        assert result.data["findings_pushed"] == 1
        assert result.data["findings_with_complete_evidence"] == 1
        assert result.data["findings_with_real_source_sink"] == 1
        assert result.data["analysis_with_evidence"] == 1
        assert result.data["context_pack"]["route"] == "/api/orders/{order_id}"
        assert result.data["context_pack"]["object_type"] == "order"
        assert result.data["findings"][0]["title"].endswith("IDOR越权漏洞")

    def test_validate_real_source_sink_rejects_unknown_placeholder(self):
        agent = BusinessLogicAnalysisAgent(
            llm_service=MagicMock(),
            tools={},
            event_emitter=None,
        )
        finding = {
            "file_path": "app/api/orders.py",
            "line_start": 42,
            "title": "app/api/orders.py中update_order函数IDOR越权漏洞",
            "description": "update_order 未验证订单归属。",
            "vulnerability_type": "idor",
            "source": "unknown",
            "sink": "Order.query.get(order_id)",
            "attacker_flow": "PUT /api/orders/2 -> update_order -> Order.query.get(2)",
            "evidence_chain": ["read_file", "search_code"],
            "finding_metadata": {
                "sink_reachable": True,
                "upstream_call_chain": [
                    "PUT /api/orders/{order_id}",
                    "update_order(order_id)",
                    "Order.query.get(order_id)",
                ],
                "sink_trigger_condition": "攻击者可以控制 order_id，且路径上不存在 owner 校验",
            },
        }

        errors = agent._validate_real_source_sink_finding(finding)
        assert any("`source` 必须是可定位的真实代码表达式" in item for item in errors)

    def test_validate_real_source_sink_rejects_non_boolean_sink_reachable(self):
        agent = BusinessLogicAnalysisAgent(
            llm_service=MagicMock(),
            tools={},
            event_emitter=None,
        )
        finding = {
            "file_path": "app/api/orders.py",
            "line_start": 42,
            "title": "app/api/orders.py中update_order函数IDOR越权漏洞",
            "description": "update_order 未验证订单归属。",
            "vulnerability_type": "idor",
            "source": "request.path_params['order_id']",
            "sink": "Order.query.get(order_id)",
            "attacker_flow": "PUT /api/orders/2 -> update_order -> Order.query.get(2)",
            "evidence_chain": ["read_file", "search_code"],
            "finding_metadata": {
                "sink_reachable": 2,
                "upstream_call_chain": [
                    "PUT /api/orders/{order_id}",
                    "update_order(order_id)",
                    "Order.query.get(order_id)",
                ],
                "sink_trigger_condition": "攻击者可以控制 order_id，且路径上不存在 owner 校验",
            },
        }

        errors = agent._validate_real_source_sink_finding(finding)
        assert any("`finding_metadata.sink_reachable` 必须明确为 true" in item for item in errors)


class TestBusinessLogicWorkflowDedupStrategy:
    @pytest.mark.asyncio
    async def test_bl_dedup_is_diagnostic_only(self):
        bl_queue = InMemoryBusinessLogicRiskQueue()
        bl_queue.enqueue(
            TASK_ID,
            {
                "file_path": "app/api/orders.py",
                "line_start": 42,
                "description": "risk-1",
                "vulnerability_type": "idor",
            },
        )
        bl_queue.enqueue(
            TASK_ID,
            {
                "file_path": "app/api/orders.py",
                "line_start": 43,
                "description": "risk-2",
                "vulnerability_type": "state_machine_bypass",
            },
        )

        orchestrator = SimpleNamespace(
            _workflow_config=None,
            sub_agents={},
            stream_llm_call=AsyncMock(),
            emit_event=AsyncMock(),
            _agent_results={},
            _all_findings=[],
        )

        engine = AuditWorkflowEngine(
            recon_queue_service=MagicMock(),
            vuln_queue_service=InMemoryVulnerabilityQueue(),
            task_id=TASK_ID,
            orchestrator=orchestrator,
            business_logic_queue_service=bl_queue,
        )

        await engine._dedup_bl_risk_queue(TASK_ID)

        assert bl_queue.size(TASK_ID) == 2
        orchestrator.stream_llm_call.assert_not_called()
        orchestrator.emit_event.assert_awaited()
