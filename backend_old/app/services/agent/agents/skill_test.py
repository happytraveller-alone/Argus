from __future__ import annotations

import time
from typing import Any, Dict, List

from .base import AgentConfig, AgentPattern, AgentResult, AgentType, BaseAgent
from .react_parser import parse_react_response


class SkillTestAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_service,
        tools: Dict[str, Any],
        selected_skill_id: str,
        max_iterations: int = 4,
        event_emitter=None,
    ):
        self.selected_skill_id = str(selected_skill_id or "").strip()
        selected_skill_contract = self._build_selected_skill_contract(tools.get(self.selected_skill_id))
        tool_whitelist = ", ".join(dict.fromkeys(tools.keys())) or "无"
        system_prompt = (
            "你是 VulHunter 的 Skill Test Agent，用于在默认测试项目 libplist 上验证单个 scan-core skill 是否按预期工作。\n\n"
            "## 目标\n"
            "- 回答用户的自然语言问题。\n"
            f"- 当前测试 skill: {self.selected_skill_id}\n"
            "- 在给出 Final Answer 前，必须至少调用一次当前测试 skill。\n"
            "- 严禁切换到其他业务 skill。\n\n"
            "## 参数契约\n"
            "- Action Input 必须是 JSON 对象，键名必须与工具 schema 一致。\n"
            "- 禁止输出数组、`items` 包裹或位置参数形式。\n"
            f"{selected_skill_contract}\n\n"
            "## 工具白名单\n"
            f"{tool_whitelist}\n\n"
            "## 输出协议\n"
            "每轮请使用纯文本 ReAct 格式：\n"
            "Thought: ...\n"
            "Action: <tool_name>\n"
            "Action Input: { ... }\n\n"
            "结束时输出：\n"
            'Final Answer: {"final_text": "用户可读的最终回答"}'
        )
        config = AgentConfig(
            name="SkillTest",
            agent_type=AgentType.ANALYSIS,
            pattern=AgentPattern.REACT,
            max_iterations=max_iterations,
            system_prompt=system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        self._conversation_history: List[Dict[str, str]] = []
        self._selected_skill_calls = 0

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        started_at = time.time()
        project_info = input_data.get("project_info", {}) if isinstance(input_data, dict) else {}
        prompt = str((input_data or {}).get("task") or "").strip()
        initial_message = (
            f"你正在默认测试项目 {project_info.get('name', 'libplist')} 上执行单技能严格模式测试。\n"
            f"项目根目录: {project_info.get('root', '.')}\n"
            f"用户问题: {prompt}\n\n"
            "请优先调用当前测试 skill 获取证据，再给出用户可读的最终回答。\n\n"
            "请特别注意：Action Input 只能输出工具参数对象，不能输出数组，也不能包成 `items`。\n\n"
            "## 可用工具说明\n"
            f"{self.get_tools_description()}"
        )
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(self.config.max_iterations):
            if self.is_cancelled:
                break

            self._iteration = iteration + 1
            llm_output, tokens_this_round = await self.stream_llm_call(self._conversation_history)
            self._total_tokens += tokens_this_round

            parsed = parse_react_response(
                llm_output,
                final_default={"final_text": str(llm_output or "").strip()},
            )
            if parsed.thought:
                await self.emit_llm_thought(parsed.thought, self._iteration)

            if parsed.action:
                action = str(parsed.action or "").strip()
                action_input = parsed.action_input or {}
                await self.emit_llm_action(action, action_input)
                observation = await self.execute_tool(action, action_input)
                if action == self.selected_skill_id:
                    self._selected_skill_calls += 1
                self._conversation_history.extend(
                    [
                        {"role": "assistant", "content": llm_output or ""},
                        {"role": "user", "content": f"Observation: {observation}"},
                    ]
                )
                continue

            if parsed.is_final:
                final_payload = parsed.final_answer if isinstance(parsed.final_answer, dict) else {}
                final_text = str(
                    final_payload.get("final_text")
                    or final_payload.get("raw_answer")
                    or ""
                ).strip()
                if self._selected_skill_calls <= 0:
                    self._conversation_history.extend(
                        [
                            {"role": "assistant", "content": llm_output or ""},
                            {
                                "role": "user",
                                "content": (
                                    f"你还没有调用当前测试 skill `{self.selected_skill_id}`。"
                                    "请先优先调用该 skill，再输出 Final Answer。"
                                ),
                            },
                        ]
                    )
                    continue
                if not final_text:
                    final_text = "测试完成，但模型未返回最终文本。"
                return AgentResult(
                    success=True,
                    data={"final_text": final_text},
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=int((time.time() - started_at) * 1000),
                    metadata={"selected_skill_id": self.selected_skill_id},
                )

            self._conversation_history.extend(
                [
                    {"role": "assistant", "content": llm_output or ""},
                    {
                        "role": "user",
                        "content": (
                            "请按格式继续：先输出 Thought，再输出 Action + Action Input；"
                            "在结束时输出 Final Answer JSON。"
                        ),
                    },
                ]
            )

        return AgentResult(
            success=False,
            data={"final_text": "测试结束，模型未在限定轮次内给出最终回答。"},
            error="max_iterations_exceeded",
            iterations=self._iteration,
            tool_calls=self._tool_calls,
            tokens_used=self._total_tokens,
            duration_ms=int((time.time() - started_at) * 1000),
            metadata={"selected_skill_id": self.selected_skill_id},
        )

    @staticmethod
    def _build_selected_skill_contract(tool: Any) -> str:
        if tool is None:
            return "- 当前 skill 未找到 schema。"

        args_schema = getattr(tool, "args_schema", None)
        if args_schema is None:
            return "- 当前 skill 未声明参数 schema。"

        schema = {}
        if hasattr(args_schema, "model_json_schema"):
            schema = args_schema.model_json_schema() or {}
        elif hasattr(args_schema, "schema"):
            schema = args_schema.schema() or {}

        properties = schema.get("properties") if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        if not isinstance(properties, dict) or not properties:
            return "- 当前 skill 未声明参数字段。"

        field_lines: List[str] = []
        for field_name, field_schema in properties.items():
            field_type = str((field_schema or {}).get("type") or "any")
            required_text = "required" if field_name in required else "optional"
            field_lines.append(f"`{field_name}` ({field_type}, {required_text})")
        return "- 当前 skill 参数: " + "；".join(field_lines) + "。"
