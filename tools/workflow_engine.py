"""
workflow_engine — 有状态工作流引擎（v2.0）
==========================================
受 LangGraph 启发，为 Agent 1 提供轻量级的图状工作流能力。

核心概念：
  - Node（节点）：工作流中的一个步骤，包含名称、执行函数和元数据
  - Edge（边）：节点间的连接，定义执行顺序和条件
  - State（状态）：工作流的运行时状态，可在节点间传递
  - Workflow（工作流）：由节点和边组成的有向图

特性：
  - 支持顺序执行、条件分支、并行执行
  - 状态持久化：可中断恢复
  - 与 task_tracker 集成
  - 全部使用 Python 标准库实现

v2.0 新增：
  - auto_checkpoint 模式：每步自动保存检查点
  - restore() 从检查点重建工作流实例
  - 与 CheckpointManager 深度集成，支持 File/SQLite 后端
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .checkpoint_manager import CheckpointManager

SANDBOX_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = SANDBOX_DIR / "memory" / "workflows.json"


# ── 错误类型 ──────────────────────────────────────────────


class WorkflowError(RuntimeError):
    """工作流引擎错误。"""


# ── 枚举 ──────────────────────────────────────────────────


class NodeStatus(str, Enum):
    """节点执行状态。"""
    PENDING = "待执行"
    RUNNING = "执行中"
    DONE = "已完成"
    FAILED = "失败"
    SKIPPED = "已跳过"


class WorkflowStatus(str, Enum):
    """工作流整体状态。"""
    PENDING = "待开始"
    RUNNING = "运行中"
    PAUSED = "已暂停"
    DONE = "已完成"
    FAILED = "失败"


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class Node:
    """工作流中的一个节点。"""
    name: str
    description: str = ""
    timeout: int = 120  # 节点超时秒数
    retry_count: int = 0  # 失败重试次数
    retry_delay: float = 1.0  # 重试间隔


@dataclass
class Edge:
    """节点间的连接。"""
    from_node: str
    to_node: str
    condition: str = ""  # 条件表达式（空=无条件）
    description: str = ""


@dataclass
class WorkflowDefinition:
    """工作流定义。"""
    name: str
    description: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    start_node: str = ""
    end_nodes: list[str] = field(default_factory=list)


@dataclass
class WorkflowInstance:
    """工作流运行时实例。"""
    workflow_name: str
    instance_id: str
    status: str = WorkflowStatus.PENDING.value
    current_node: str = ""
    node_statuses: dict[str, str] = field(default_factory=dict)
    node_results: dict[str, str] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    task_id: str = ""  # 关联的 task_tracker 任务ID


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "workflow",
        "description": (
            "有状态工作流引擎。支持定义和执行图状工作流，"
            "节点间可设置条件和依赖，运行时状态可持久化和恢复。"
            "从 LangGraph 借鉴的有状态工作流模式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "define",
                        "start",
                        "step",
                        "pause",
                        "resume",
                        "status",
                        "list",
                        "delete",
                        "checkpoint_restore",
                    ],
                    "description": (
                        "操作类型："
                        "define — 定义一个新的工作流；"
                        "start — 启动一个工作流实例；"
                        "step — 执行工作流的下一步；"
                        "pause — 暂停工作流；"
                        "resume — 恢复暂停的工作流；"
                        "status — 查看工作流状态；"
                        "list — 列出所有工作流定义；"
                        "delete — 删除工作流定义；"
                        "checkpoint_restore — 从自动检查点恢复工作流实例。"
                    ),
                },
                "workflow_name": {
                    "type": "string",
                    "description": "工作流名称",
                    "default": "",
                },
                "instance_id": {
                    "type": "string",
                    "description": "工作流实例ID",
                    "default": "",
                },
                "description": {
                    "type": "string",
                    "description": "工作流描述",
                    "default": "",
                },
                "nodes": {
                    "type": "string",
                    "description": "节点列表JSON字符串，如 '[{\"name\":\"step1\",\"description\":\"第一步\"}]'",
                    "default": "",
                },
                "edges": {
                    "type": "string",
                    "description": "边列表JSON字符串，如 '[{\"from_node\":\"step1\",\"to_node\":\"step2\"}]'",
                    "default": "",
                },
                "start_node": {
                    "type": "string",
                    "description": "起始节点名称",
                    "default": "",
                },
                "end_nodes": {
                    "type": "string",
                    "description": "结束节点名称列表JSON，如 '[\"step3\"]'",
                    "default": "",
                },
                "initial_state": {
                    "type": "string",
                    "description": "初始状态JSON字符串",
                    "default": "",
                },
                "node_result": {
                    "type": "string",
                    "description": "当前节点的执行结果",
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 工作流引擎 ────────────────────────────────────────────


class WorkflowEngine:
    """
    有状态工作流引擎（v2.0）。
    
    管理工作流的定义、实例化和执行。
    支持状态持久化、中断恢复、自动检查点。
    
    使用方式：
      # 默认模式（无自动检查点，向后兼容）
      engine = WorkflowEngine()
      
      # 自动检查点模式
      engine = WorkflowEngine(auto_checkpoint=True)
      
      # 自定义检查点后端
      from tools.checkpoint_backend import SQLiteBackend
      cm = CheckpointManager(backend=SQLiteBackend("memory/wf_checkpoints.db"))
      engine = WorkflowEngine(auto_checkpoint=True, checkpoint_manager=cm)
    """

    def __init__(
        self,
        auto_checkpoint: bool = False,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._instances: dict[str, WorkflowInstance] = {}
        self._auto_checkpoint = auto_checkpoint
        self._checkpoint_manager = checkpoint_manager or CheckpointManager()
        self._load()

    # ── 自动检查点辅助方法 ─────────────────────────────────

    def _checkpoint_save(self, instance: WorkflowInstance, phase: str = "") -> None:
        """如果启用了自动检查点，保存当前实例状态。"""
        if not self._auto_checkpoint:
            return
        if not instance.instance_id:
            return
        try:
            state = {
                "workflow_name": instance.workflow_name,
                "instance_id": instance.instance_id,
                "current_node": instance.current_node,
                "node_statuses": instance.node_statuses,
                "node_results": instance.node_results,
                "state": instance.state,
                "task_id": instance.task_id,
                "status": instance.status,
                "created_at": instance.created_at,
                "updated_at": instance.updated_at,
                "completed_at": instance.completed_at,
                "error": instance.error,
            }
            self._checkpoint_manager.save(
                task_id=f"wf:{instance.instance_id}",
                phase=phase or instance.current_node or "unknown",
                state=state,
            )
        except Exception:
            # 检查点保存失败不应中断工作流执行
            pass

    def restore(self, instance_id: str) -> str:
        """
        从检查点恢复工作流实例。
        
        参数：
          instance_id: 要恢复的实例 ID
        
        返回：状态描述
        
        如果找不到检查点，抛出 WorkflowError。
        """
        task_id = f"wf:{instance_id}"
        all_cps = self._checkpoint_manager.list(task_id)
        if not all_cps:
            raise WorkflowError(
                f"未找到实例 '{instance_id}' 的检查点。"
                f"请确认该实例曾启用 auto_checkpoint 且存在已保存的检查点。"
            )

        # 取最新的检查点
        latest = all_cps[0]
        full = self._checkpoint_manager.load(latest["checkpoint_id"])
        state = full.get("state", {})

        if not state or "workflow_name" not in state:
            raise WorkflowError(f"检查点数据不完整，无法恢复实例 '{instance_id}'")

        # 验证工作流定义仍存在
        wf_name = state["workflow_name"]
        if wf_name not in self._definitions:
            # 尝试从 workflows.json 重新加载
            self._load()
            if wf_name not in self._definitions:
                raise WorkflowError(
                    f"工作流定义 '{wf_name}' 已丢失，无法恢复实例 '{instance_id}'。"
                    f"请先重新 define 该工作流。"
                )

        # 重建 WorkflowInstance
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        instance = WorkflowInstance(
            workflow_name=wf_name,
            instance_id=instance_id,
            status=state.get("status", WorkflowStatus.PAUSED.value),
            current_node=state.get("current_node", ""),
            node_statuses=state.get("node_statuses", {}),
            node_results=state.get("node_results", {}),
            state=state.get("state", {}),
            error=state.get("error", ""),
            created_at=state.get("created_at", now),
            updated_at=now,
            completed_at=state.get("completed_at", ""),
            task_id=state.get("task_id", ""),
        )

        self._instances[instance_id] = instance
        self._save()

        completed = sum(
            1 for s in instance.node_statuses.values()
            if s == NodeStatus.DONE.value
        )
        total = len(instance.node_statuses)

        return (
            f"🔄 工作流实例已从检查点恢复\n"
            f"   实例ID: {instance_id}\n"
            f"   工作流: '{wf_name}'\n"
            f"   当前节点: '{instance.current_node or '无'}'\n"
            f"   进度: {completed}/{total} 节点已完成\n"
            f"   状态: {instance.status}\n"
            f"   使用 step 继续执行"
        )

    def _load(self) -> None:
        """从文件加载工作流数据。"""
        if WORKFLOW_FILE.is_file():
            try:
                raw = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
                # 恢复定义
                for name, def_data in raw.get("definitions", {}).items():
                    self._definitions[name] = WorkflowDefinition(
                        name=def_data["name"],
                        description=def_data.get("description", ""),
                        nodes=[Node(**n) for n in def_data.get("nodes", [])],
                        edges=[Edge(**e) for e in def_data.get("edges", [])],
                        start_node=def_data.get("start_node", ""),
                        end_nodes=def_data.get("end_nodes", []),
                    )
                # 恢复实例
                for iid, inst_data in raw.get("instances", {}).items():
                    self._instances[iid] = WorkflowInstance(**inst_data)
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        """保存工作流数据到文件。"""
        WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "definitions": {
                name: asdict(defn) for name, defn in self._definitions.items()
            },
            "instances": {
                iid: asdict(inst) for iid, inst in self._instances.items()
            },
        }
        WORKFLOW_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 工作流定义管理 ───────────────────────────────────

    def define(
        self,
        name: str,
        description: str = "",
        nodes: str = "",
        edges: str = "",
        start_node: str = "",
        end_nodes: str = "",
    ) -> str:
        """定义一个新的工作流。"""
        if not name.strip():
            raise WorkflowError("工作流名称不能为空")

        # 解析节点列表
        node_list: list[Node] = []
        if nodes:
            try:
                raw_nodes = json.loads(nodes)
                if not isinstance(raw_nodes, list):
                    raise WorkflowError("nodes 必须是 JSON 数组")
                node_list = [Node(**n) for n in raw_nodes]
            except json.JSONDecodeError as exc:
                raise WorkflowError(f"nodes JSON 解析错误: {exc}")

        if not node_list:
            raise WorkflowError("至少需要一个节点")

        # 解析边列表
        edge_list: list[Edge] = []
        if edges:
            try:
                raw_edges = json.loads(edges)
                if not isinstance(raw_edges, list):
                    raise WorkflowError("edges 必须是 JSON 数组")
                edge_list = [Edge(**e) for e in raw_edges]
            except json.JSONDecodeError as exc:
                raise WorkflowError(f"edges JSON 解析错误: {exc}")

        # 解析结束节点
        end_node_list: list[str] = []
        if end_nodes:
            try:
                end_node_list = json.loads(end_nodes)
                if not isinstance(end_node_list, list):
                    raise WorkflowError("end_nodes 必须是 JSON 数组")
            except json.JSONDecodeError as exc:
                raise WorkflowError(f"end_nodes JSON 解析错误: {exc}")

        # 验证起始节点
        node_names = {n.name for n in node_list}
        if start_node and start_node not in node_names:
            raise WorkflowError(f"起始节点 '{start_node}' 不在节点列表中")
        if not start_node:
            start_node = node_list[0].name

        # 验证结束节点
        for en in end_node_list:
            if en not in node_names:
                raise WorkflowError(f"结束节点 '{en}' 不在节点列表中")
        if not end_node_list:
            # 如果没有指定结束节点，最后一个节点即为结束节点
            end_node_list = [node_list[-1].name]

        # 验证边
        for edge in edge_list:
            if edge.from_node not in node_names:
                raise WorkflowError(f"边起点 '{edge.from_node}' 不在节点列表中")
            if edge.to_node not in node_names:
                raise WorkflowError(f"边终点 '{edge.to_node}' 不在节点列表中")

        definition = WorkflowDefinition(
            name=name.strip(),
            description=description.strip(),
            nodes=node_list,
            edges=edge_list,
            start_node=start_node,
            end_nodes=end_node_list,
        )

        self._definitions[name] = definition
        self._save()

        node_summary = ", ".join(f"'{n.name}'" for n in node_list)
        edge_summary = len(edge_list)

        return (
            f"📋 已定义工作流: '{name}'\n"
            f"   节点 ({len(node_list)}): {node_summary}\n"
            f"   边 ({edge_summary}): {'无' if not edge_summary else f'{edge_summary} 条连接'}\n"
            f"   起始: '{start_node}' | 结束: {end_node_list}"
        )

    # ── 工作流实例管理 ───────────────────────────────────

    def start(
        self,
        workflow_name: str,
        initial_state: str = "",
        task_id: str = "",
    ) -> str:
        """启动一个工作流实例。"""
        definition = self._definitions.get(workflow_name)
        if not definition:
            raise WorkflowError(f"未找到工作流定义: '{workflow_name}'")

        # 生成实例ID（用 uuid 保证唯一，Windows 时间戳精度不足会导致同一时间片内冲突）
        now = datetime.now()
        instance_id = f"WF-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        # 解析初始状态
        state: dict[str, Any] = {}
        if initial_state:
            try:
                state = json.loads(initial_state)
            except json.JSONDecodeError as exc:
                raise WorkflowError(f"initial_state JSON 解析错误: {exc}")

        # 创建实例
        node_statuses = {n.name: NodeStatus.PENDING.value for n in definition.nodes}
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        instance = WorkflowInstance(
            workflow_name=workflow_name,
            instance_id=instance_id,
            status=WorkflowStatus.RUNNING.value,
            current_node=definition.start_node,
            node_statuses=node_statuses,
            node_results={},
            state=state,
            created_at=timestamp,
            updated_at=timestamp,
            task_id=task_id,
        )

        # 标记起始节点为进行中
        instance.node_statuses[definition.start_node] = NodeStatus.RUNNING.value

        self._instances[instance_id] = instance
        self._save()
        self._checkpoint_save(instance, phase=f"_start:{definition.start_node}")

        node_count = len(definition.nodes)
        return (
            f"🚀 工作流实例已启动\n"
            f"   实例ID: {instance_id}\n"
            f"   工作流: '{workflow_name}' ({node_count} 个节点)\n"
            f"   当前节点: '{definition.start_node}'\n"
            f"   状态: {instance.status}"
            + (" [自动检查点已启用]" if self._auto_checkpoint else "")
        )

    def step(self, instance_id: str, node_result: str = "") -> str:
        """执行工作流的下一步。可选的 node_result 记录当前节点执行结果。"""
        instance = self._instances.get(instance_id)
        if not instance:
            raise WorkflowError(f"未找到工作流实例: '{instance_id}'")

        if instance.status in (WorkflowStatus.DONE.value, WorkflowStatus.FAILED.value):
            return f"⚠️ 工作流 '{instance_id}' 已结束，状态: {instance.status}"

        definition = self._definitions.get(instance.workflow_name)
        if not definition:
            raise WorkflowError(f"工作流定义 '{instance.workflow_name}' 已丢失")

        current = instance.current_node
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 记录当前节点的结果
        if node_result:
            instance.node_results[current] = node_result

        # 标记当前节点为已完成
        instance.node_statuses[current] = NodeStatus.DONE.value

        # 检查是否到达结束节点
        if current in definition.end_nodes:
            instance.status = WorkflowStatus.DONE.value
            instance.completed_at = now
            instance.updated_at = now
            instance.current_node = ""
            self._save()
            self._checkpoint_save(instance, phase="_done")
            return (
                f"✅ 工作流 '{instance_id}' 已完成！\n"
                f"   最后节点: '{current}'"
            )

        # 查找下一个节点
        next_node = self._find_next_node(definition, current, instance.state)

        if not next_node:
            # 没有更多节点，工作流完成
            instance.status = WorkflowStatus.DONE.value
            instance.completed_at = now
            instance.updated_at = now
            instance.current_node = ""
            self._save()
            self._checkpoint_save(instance, phase="_done")
            return f"✅ 工作流 '{instance_id}' 已完成（所有路径已走完）"

        # 移动到下一个节点
        instance.current_node = next_node
        instance.node_statuses[next_node] = NodeStatus.RUNNING.value
        instance.updated_at = now
        self._save()
        self._checkpoint_save(instance, phase=current)

        next_desc = ""
        for node in definition.nodes:
            if node.name == next_node:
                next_desc = node.description
                break

        completed = sum(1 for s in instance.node_statuses.values() if s == NodeStatus.DONE.value)
        total = len(definition.nodes)

        return (
            f"➡️ 工作流 '{instance_id}' 前进到下一步\n"
            f"   已完成: {completed}/{total} 节点\n"
            f"   上一个: '{current}' → 当前: '{next_node}'\n"
            f"   描述: {next_desc or '无'}"
        )

    def _find_next_node(
        self,
        definition: WorkflowDefinition,
        current: str,
        state: dict[str, Any],
    ) -> str | None:
        """查找当前节点的下一个节点。"""
        # 查找从当前节点出发的边
        outgoing_edges = [e for e in definition.edges if e.from_node == current]

        if not outgoing_edges:
            # 没有出边，按节点列表顺序找下一个未执行的节点
            node_names = [n.name for n in definition.nodes]
            current_idx = node_names.index(current)
            for i in range(current_idx + 1, len(node_names)):
                next_name = node_names[i]
                if next_name not in definition.end_nodes or True:
                    if self._is_node_ready(definition, next_name):
                        return next_name
            return None

        # 有出边，检查条件
        for edge in outgoing_edges:
            if not edge.condition:
                # 无条件边，直接使用
                return edge.to_node
            # 有条件边，需评估条件（简化版：检查 state 中是否有对应键）
            condition_met = self._evaluate_condition(edge.condition, state)
            if condition_met:
                return edge.to_node

        return None

    def _is_node_ready(self, definition: WorkflowDefinition, node_name: str) -> bool:
        """检查节点是否已就绪（所有入边对应的源节点已完成）。"""
        incoming_edges = [e for e in definition.edges if e.to_node == node_name]
        if not incoming_edges:
            return True  # 没有入边，视为就绪

        instance = self._get_instance_for_workflow(definition.name)
        if not instance:
            return True

        for edge in incoming_edges:
            status = instance.node_statuses.get(edge.from_node, NodeStatus.PENDING.value)
            if status != NodeStatus.DONE.value:
                return False
        return True

    def _get_instance_for_workflow(self, workflow_name: str) -> WorkflowInstance | None:
        """获取工作流的最新运行实例（仅用于检查）。"""
        matching = [
            inst for inst in self._instances.values()
            if inst.workflow_name == workflow_name
            and inst.status == WorkflowStatus.RUNNING.value
        ]
        return matching[-1] if matching else None

    @staticmethod
    def _evaluate_condition(condition: str, state: dict[str, Any]) -> bool:
        """
        评估条件表达式（简化版）。
        
        支持格式：
          - "key" — 检查 state 中是否存在该键且为真
          - "key=value" — 检查 state[key] == value
        """
        condition = condition.strip()
        if not condition:
            return True

        if "=" in condition:
            key, value = condition.split("=", 1)
            key = key.strip()
            value = value.strip()
            return str(state.get(key, "")) == value

        # 布尔检查：键是否存在且为真
        return bool(state.get(condition))

    # ── 工作流状态管理 ───────────────────────────────────

    def pause(self, instance_id: str) -> str:
        """暂停工作流。"""
        instance = self._instances.get(instance_id)
        if not instance:
            raise WorkflowError(f"未找到工作流实例: '{instance_id}'")

        if instance.status != WorkflowStatus.RUNNING.value:
            return f"⚠️ 工作流 '{instance_id}' 状态为 '{instance.status}'，无法暂停"

        instance.status = WorkflowStatus.PAUSED.value
        instance.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        self._checkpoint_save(instance, phase="_pause")

        return (
            f"⏸️ 工作流 '{instance_id}' 已暂停\n"
            f"   当前节点: '{instance.current_node}'\n"
            f"   使用 resume 恢复执行"
        )

    def resume(self, instance_id: str) -> str:
        """恢复暂停的工作流。"""
        instance = self._instances.get(instance_id)
        if not instance:
            raise WorkflowError(f"未找到工作流实例: '{instance_id}'")

        if instance.status != WorkflowStatus.PAUSED.value:
            return f"⚠️ 工作流 '{instance_id}' 状态为 '{instance.status}'，无法恢复"

        instance.status = WorkflowStatus.RUNNING.value
        instance.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()

        return (
            f"▶️ 工作流 '{instance_id}' 已恢复\n"
            f"   当前节点: '{instance.current_node}'\n"
            f"   使用 step 执行下一步"
        )

    def get_status(self, instance_id: str) -> str:
        """查看工作流实例状态。"""
        instance = self._instances.get(instance_id)
        if not instance:
            raise WorkflowError(f"未找到工作流实例: '{instance_id}'")

        definition = self._definitions.get(instance.workflow_name)

        lines = [
            f"📊 工作流状态: '{instance_id}'",
            f"{'='*50}",
            f"工作流: '{instance.workflow_name}'",
            f"状态: {instance.status}",
            f"当前节点: '{instance.current_node or '无'}'",
        ]

        if instance.task_id:
            lines.append(f"关联任务: [{instance.task_id}]")

        if instance.created_at:
            lines.append(f"创建时间: {instance.created_at}")
        if instance.completed_at:
            lines.append(f"完成时间: {instance.completed_at}")

        # 节点状态
        lines.append(f"\n节点状态 ({len(instance.node_statuses)}):")
        for node_name, status in instance.node_statuses.items():
            icon = {
                NodeStatus.DONE.value: "✅",
                NodeStatus.RUNNING.value: "🔄",
                NodeStatus.PENDING.value: "⬜",
                NodeStatus.FAILED.value: "❌",
                NodeStatus.SKIPPED.value: "⏭️",
            }.get(status, "❓")
            
            result = instance.node_results.get(node_name, "")
            result_str = f" → {result[:50]}" if result else ""
            lines.append(f"  {icon} '{node_name}': {status}{result_str}")

        # 状态摘要
        if definition:
            completed = sum(1 for s in instance.node_statuses.values()
                          if s == NodeStatus.DONE.value)
            total = len(definition.nodes)
            pct = completed * 100 // total if total else 0
            bar_len = 15
            filled = pct * bar_len // 100
            bar = "█" * filled + "░" * (bar_len - filled)
            lines.append(f"\n进度: [{bar}] {completed}/{total} ({pct}%)")

        return "\n".join(lines)

    def list_workflows(self) -> str:
        """列出所有工作流定义。"""
        if not self._definitions:
            return "暂无工作流定义。"

        lines = ["📋 工作流定义列表:\n"]
        for name, defn in sorted(self._definitions.items()):
            node_count = len(defn.nodes)
            edge_count = len(defn.edges)
            # 统计活跃实例
            active_instances = sum(
                1 for inst in self._instances.values()
                if inst.workflow_name == name
                and inst.status in (
                    WorkflowStatus.RUNNING.value,
                    WorkflowStatus.PAUSED.value,
                )
            )
            active_str = f" (活跃: {active_instances})" if active_instances else ""
            lines.append(
                f"  📂 '{name}' — {node_count} 节点, "
                f"{edge_count} 边{active_str}"
            )
            if defn.description:
                lines.append(f"      {defn.description[:80]}")

        return "\n".join(lines)

    def delete(self, name: str) -> str:
        """删除工作流定义及其关联实例。"""
        if name not in self._definitions:
            raise WorkflowError(f"未找到工作流定义: '{name}'")

        # 删除关联实例
        deleted_instances = [
            iid for iid, inst in self._instances.items()
            if inst.workflow_name == name
        ]
        for iid in deleted_instances:
            del self._instances[iid]

        del self._definitions[name]
        self._save()

        return (
            f"🗑️ 已删除工作流 '{name}'"
            + (f" 及 {len(deleted_instances)} 个关联实例" if deleted_instances else "")
        )


# ── 全局实例 ──────────────────────────────────────────────

_engine = WorkflowEngine()


def execute_workflow_tool(arguments: dict[str, Any]) -> str:
    """执行 workflow 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "define":
            return _engine.define(
                name=arguments.get("workflow_name", ""),
                description=arguments.get("description", ""),
                nodes=arguments.get("nodes", ""),
                edges=arguments.get("edges", ""),
                start_node=arguments.get("start_node", ""),
                end_nodes=arguments.get("end_nodes", ""),
            )

        elif action == "start":
            return _engine.start(
                workflow_name=arguments.get("workflow_name", ""),
                initial_state=arguments.get("initial_state", ""),
                task_id=arguments.get("task_id", ""),
            )

        elif action == "step":
            return _engine.step(
                instance_id=arguments.get("instance_id", ""),
                node_result=arguments.get("node_result", ""),
            )

        elif action == "pause":
            return _engine.pause(arguments.get("instance_id", ""))

        elif action == "resume":
            return _engine.resume(arguments.get("instance_id", ""))

        elif action == "status":
            return _engine.get_status(arguments.get("instance_id", ""))

        elif action == "list":
            return _engine.list_workflows()

        elif action == "delete":
            return _engine.delete(arguments.get("workflow_name", ""))

        elif action == "checkpoint_restore":
            return _engine.restore(arguments.get("instance_id", ""))

        else:
            return f"未知操作: {action}"

    except WorkflowError as exc:
        return f"工作流错误: {exc}"
