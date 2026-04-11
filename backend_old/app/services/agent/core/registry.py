"""
Agent 注册表和动态Agent树管理

提供：
- Agent实例注册和管理
- 动态Agent树结构
- Agent状态追踪
- 子Agent创建和销毁
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import AgentState

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Agent 注册表
    
    管理所有Agent实例，维护动态Agent树结构
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # Agent图结构
        self._agent_graph: Dict[str, Any] = {
            "nodes": {},  # agent_id -> node_info
            "edges": [],  # {from, to, type}
        }
        
        # Agent实例和状态
        self._agent_instances: Dict[str, Any] = {}  # agent_id -> agent_instance
        self._agent_states: Dict[str, "AgentState"] = {}  # agent_id -> state
        
        # 消息队列
        self._agent_messages: Dict[str, List[Dict[str, Any]]] = {}  # agent_id -> messages
        
        # 根Agent
        self._root_agent_id: Optional[str] = None
        self._root_agent_ids: Dict[str, str] = {}
        
        # 运行中的Agent线程
        self._running_agents: Dict[str, threading.Thread] = {}
    
    # ============ Agent 注册 ============
    
    def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        task: str,
        parent_id: Optional[str] = None,
        agent_instance: Any = None,
        state: Optional["AgentState"] = None,
        knowledge_modules: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        注册Agent到注册表
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            agent_type: Agent类型
            task: 任务描述
            parent_id: 父Agent ID
            agent_instance: Agent实例
            state: Agent状态
            knowledge_modules: 加载的知识模块
            
        Returns:
            注册的节点信息
        """
        logger.debug(f"[AgentRegistry] register_agent 被调用: {agent_name} (id={agent_id}, parent={parent_id})")
        logger.debug(f"[AgentRegistry] 当前节点数: {len(self._agent_graph['nodes'])}, 节点列表: {list(self._agent_graph['nodes'].keys())}")

        with self._lock:
            parent_task_id: Optional[str] = None
            if parent_id:
                parent_node = self._agent_graph["nodes"].get(parent_id)
                if parent_node:
                    parent_task_id = self._normalize_task_id(parent_node.get("task_id"))

            resolved_task_id = self._normalize_task_id(task_id) or parent_task_id
            if parent_task_id and resolved_task_id and parent_task_id != resolved_task_id:
                logger.warning(
                    "[AgentRegistry] Agent %s(%s) task_id=%s mismatches parent %s task_id=%s; inherit parent task",
                    agent_name,
                    agent_id,
                    resolved_task_id,
                    parent_id,
                    parent_task_id,
                )
                resolved_task_id = parent_task_id

            node = {
                "id": agent_id,
                "task_id": resolved_task_id,
                "name": agent_name,
                "type": agent_type,
                "task": task,
                "status": "running",
                "parent_id": parent_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "result": None,
                "knowledge_modules": knowledge_modules or [],
                "children": [],
            }
            
            self._agent_graph["nodes"][agent_id] = node
            
            if agent_instance:
                self._agent_instances[agent_id] = agent_instance
            
            if state:
                self._agent_states[agent_id] = state
            
            # 初始化消息队列
            if agent_id not in self._agent_messages:
                self._agent_messages[agent_id] = []
            
            # 添加边（父子关系）
            if parent_id:
                self._agent_graph["edges"].append({
                    "from": parent_id,
                    "to": agent_id,
                    "type": "delegation",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                
                # 更新父节点的children列表
                if parent_id in self._agent_graph["nodes"]:
                    parent_children = self._agent_graph["nodes"][parent_id]["children"]
                    if agent_id not in parent_children:
                        parent_children.append(agent_id)

            # 设置根Agent
            if parent_id is None:
                if resolved_task_id:
                    existing_root_id = self._root_agent_ids.get(resolved_task_id)
                    if existing_root_id and existing_root_id != agent_id:
                        logger.warning(
                            "[AgentRegistry] Replacing root agent for task %s: %s -> %s",
                            resolved_task_id,
                            existing_root_id,
                            agent_id,
                        )
                    self._root_agent_ids[resolved_task_id] = agent_id
                if self._root_agent_id is None:
                    self._root_agent_id = agent_id

            logger.debug(f"[AgentRegistry] 注册完成: {agent_name} ({agent_id}), parent: {parent_id}")
            logger.debug(f"[AgentRegistry] 注册后节点数: {len(self._agent_graph['nodes'])}, 节点列表: {list(self._agent_graph['nodes'].keys())}")
            return node

    def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        with self._lock:
            removed_node = self._agent_graph["nodes"].pop(agent_id, None)
            removed_task_id = self._normalize_task_id(
                removed_node.get("task_id") if removed_node else None
            )

            if removed_node:
                parent_id = removed_node.get("parent_id")
                if parent_id in self._agent_graph["nodes"]:
                    self._agent_graph["nodes"][parent_id]["children"] = [
                        child_id
                        for child_id in self._agent_graph["nodes"][parent_id].get("children", [])
                        if child_id != agent_id
                    ]

            self._agent_instances.pop(agent_id, None)
            self._agent_states.pop(agent_id, None)
            self._agent_messages.pop(agent_id, None)
            self._running_agents.pop(agent_id, None)
            
            # 移除相关边
            self._agent_graph["edges"] = [
                e for e in self._agent_graph["edges"]
                if e["from"] != agent_id and e["to"] != agent_id
            ]

            if removed_task_id and self._root_agent_ids.get(removed_task_id) == agent_id:
                self._root_agent_ids.pop(removed_task_id, None)

            if self._root_agent_id == agent_id:
                self._root_agent_id = self._resolve_root_agent_id_locked()

            logger.debug(f"Unregistered agent: {agent_id}")
    
    # ============ Agent 状态更新 ============
    
    def update_agent_status(
        self,
        agent_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """更新Agent状态"""
        with self._lock:
            if agent_id in self._agent_graph["nodes"]:
                node = self._agent_graph["nodes"][agent_id]
                node["status"] = status
                
                if status in ["completed", "failed", "stopped"]:
                    node["finished_at"] = datetime.now(timezone.utc).isoformat()
                
                if result:
                    node["result"] = result
                
                logger.debug(f"Updated agent {agent_id} status to {status}")
    
    def get_agent_status(self, agent_id: str) -> Optional[str]:
        """获取Agent状态"""
        with self._lock:
            if agent_id in self._agent_graph["nodes"]:
                return self._agent_graph["nodes"][agent_id]["status"]
            return None
    
    # ============ Agent 查询 ============
    
    def get_agent(self, agent_id: str) -> Optional[Any]:
        """获取Agent实例"""
        return self._agent_instances.get(agent_id)
    
    def get_agent_state(self, agent_id: str) -> Optional["AgentState"]:
        """获取Agent状态"""
        return self._agent_states.get(agent_id)
    
    def get_agent_node(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent节点信息"""
        return self._agent_graph["nodes"].get(agent_id)
    
    def get_root_agent_id(
        self,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取根Agent ID"""
        with self._lock:
            resolved_task_id = self._resolve_task_id_locked(
                task_id=task_id,
                agent_id=agent_id,
            )
            return self._resolve_root_agent_id_locked(resolved_task_id)
    
    def get_children(self, agent_id: str) -> List[str]:
        """获取子Agent ID列表"""
        with self._lock:
            node = self._agent_graph["nodes"].get(agent_id)
            if node:
                return node.get("children", [])
            return []
    
    def get_parent(self, agent_id: str) -> Optional[str]:
        """获取父Agent ID"""
        with self._lock:
            node = self._agent_graph["nodes"].get(agent_id)
            if node:
                return node.get("parent_id")
            return None
    
    # ============ Agent 树操作 ============
    
    def get_agent_tree(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """获取完整的Agent树结构"""
        with self._lock:
            resolved_task_id = self._normalize_task_id(task_id)
            if resolved_task_id:
                filtered_ids = {
                    agent_id
                    for agent_id, node in self._agent_graph["nodes"].items()
                    if self._normalize_task_id(node.get("task_id")) == resolved_task_id
                }
            else:
                filtered_ids = set(self._agent_graph["nodes"].keys())

            return {
                "nodes": {
                    agent_id: self._clone_node_for_tree(node, filtered_ids=filtered_ids)
                    for agent_id, node in self._agent_graph["nodes"].items()
                    if agent_id in filtered_ids
                },
                "edges": [
                    dict(edge)
                    for edge in self._agent_graph["edges"]
                    if edge.get("from") in filtered_ids and edge.get("to") in filtered_ids
                ],
                "root_agent_id": self._resolve_root_agent_id_locked(resolved_task_id),
            }

    def get_agent_tree_view(
        self,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """获取Agent树的文本视图"""
        with self._lock:
            lines = ["=== AGENT TREE ==="]
            resolved_task_id = self._resolve_task_id_locked(
                task_id=task_id,
                agent_id=agent_id,
            )
            tree = self.get_agent_tree(task_id=resolved_task_id)

            root_id = agent_id or tree.get("root_agent_id")
            if not root_id or root_id not in tree["nodes"]:
                return "No agents in the tree"

            def _build_tree(aid: str, depth: int = 0) -> None:
                node = tree["nodes"].get(aid)
                if not node:
                    return

                indent = "  " * depth
                status_emoji = {
                    "running": "🔄",
                    "waiting": "⏳",
                    "completed": "",
                    "failed": "",
                    "stopped": "🛑",
                }.get(node["status"], "❓")

                lines.append(f"{indent}{status_emoji} {node['name']} ({aid})")
                lines.append(f"{indent}   Task: {node['task'][:50]}...")
                lines.append(f"{indent}   Status: {node['status']}")

                if node.get("knowledge_modules"):
                    lines.append(f"{indent}   Modules: {', '.join(node['knowledge_modules'])}")

                for child_id in node.get("children", []):
                    _build_tree(child_id, depth + 1)

            _build_tree(root_id)
            return "\n".join(lines)

    def get_statistics(self, task_id: Optional[str] = None) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            resolved_task_id = self._normalize_task_id(task_id)
            stats = {
                "total": 0,
                "running": 0,
                "waiting": 0,
                "completed": 0,
                "failed": 0,
                "stopped": 0,
            }

            for node in self._agent_graph["nodes"].values():
                if resolved_task_id and self._normalize_task_id(node.get("task_id")) != resolved_task_id:
                    continue
                stats["total"] += 1
                status = node.get("status", "unknown")
                if status in stats:
                    stats[status] += 1

            return stats

    # ============ 清理 ============

    def clear_task(self, task_id: str) -> int:
        """清空指定任务的注册表数据"""
        resolved_task_id = self._normalize_task_id(task_id)
        if not resolved_task_id:
            return 0

        with self._lock:
            removed_ids = {
                agent_id
                for agent_id, node in self._agent_graph["nodes"].items()
                if self._normalize_task_id(node.get("task_id")) == resolved_task_id
            }
            if not removed_ids:
                return 0

            for agent_id in removed_ids:
                self._agent_graph["nodes"].pop(agent_id, None)
                self._agent_instances.pop(agent_id, None)
                self._agent_states.pop(agent_id, None)
                self._agent_messages.pop(agent_id, None)
                self._running_agents.pop(agent_id, None)

            for node in self._agent_graph["nodes"].values():
                node["children"] = [
                    child_id
                    for child_id in node.get("children", [])
                    if child_id not in removed_ids
                ]

            self._agent_graph["edges"] = [
                edge
                for edge in self._agent_graph["edges"]
                if edge.get("from") not in removed_ids and edge.get("to") not in removed_ids
            ]

            self._root_agent_ids.pop(resolved_task_id, None)
            if self._root_agent_id in removed_ids:
                self._root_agent_id = self._resolve_root_agent_id_locked()

            logger.debug(
                "Cleared %s agent nodes for task %s",
                len(removed_ids),
                resolved_task_id,
            )
            return len(removed_ids)

    def clear(self) -> None:
        """清空注册表"""
        with self._lock:
            self._agent_graph = {"nodes": {}, "edges": []}
            self._agent_instances.clear()
            self._agent_states.clear()
            self._agent_messages.clear()
            self._running_agents.clear()
            self._root_agent_id = None
            self._root_agent_ids.clear()
            logger.debug("Agent registry cleared")
    
    def cleanup_finished_agents(self) -> int:
        """清理已完成的Agent"""
        with self._lock:
            finished_ids = [
                aid for aid, node in self._agent_graph["nodes"].items()
                if node["status"] in ["completed", "failed", "stopped"]
            ]
            
            for aid in finished_ids:
                # 保留节点信息，但清理实例
                self._agent_instances.pop(aid, None)
                self._running_agents.pop(aid, None)
            
            return len(finished_ids)

    def _normalize_task_id(self, task_id: Optional[str]) -> Optional[str]:
        value = str(task_id or "").strip()
        return value or None

    def _resolve_task_id_locked(
        self,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Optional[str]:
        resolved_task_id = self._normalize_task_id(task_id)
        if resolved_task_id:
            return resolved_task_id

        for candidate_id in (agent_id, parent_id):
            if not candidate_id:
                continue
            node = self._agent_graph["nodes"].get(candidate_id)
            if node:
                node_task_id = self._normalize_task_id(node.get("task_id"))
                if node_task_id:
                    return node_task_id

        return None

    def _resolve_root_agent_id_locked(self, task_id: Optional[str] = None) -> Optional[str]:
        resolved_task_id = self._normalize_task_id(task_id)
        if resolved_task_id:
            root_id = self._root_agent_ids.get(resolved_task_id)
            if root_id:
                return root_id
            for agent_id, node in self._agent_graph["nodes"].items():
                if self._normalize_task_id(node.get("task_id")) != resolved_task_id:
                    continue
                parent_id = node.get("parent_id")
                parent_node = self._agent_graph["nodes"].get(parent_id) if parent_id else None
                parent_task_id = self._normalize_task_id(
                    parent_node.get("task_id") if parent_node else None
                )
                if not parent_id or parent_task_id != resolved_task_id:
                    return agent_id
            return None

        if self._root_agent_id and self._root_agent_id in self._agent_graph["nodes"]:
            return self._root_agent_id
        if self._root_agent_ids:
            return next(iter(self._root_agent_ids.values()))
        for agent_id, node in self._agent_graph["nodes"].items():
            if not node.get("parent_id"):
                return agent_id
        return None

    def _clone_node_for_tree(
        self,
        node: Dict[str, Any],
        *,
        filtered_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        cloned = dict(node)
        children = list(node.get("children", []))
        if filtered_ids is not None:
            children = [child_id for child_id in children if child_id in filtered_ids]
        cloned["children"] = children
        return cloned


# 全局注册表实例
agent_registry = AgentRegistry()
