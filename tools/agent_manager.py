"""
agent_manager — Agent 注册管理系统（F1）
========================================
为 Agent 1 提供多智能体协同的基础设施。

核心功能：
  - Agent 注册/注销管理
  - 按能力发现 Agent
  - 状态管理与心跳检测
  - 健康报告生成
  - 任务分配与追踪

设计理念（AutoGen 启发）：
  - 每个 Agent 有独立身份、能力和工具集
  - 支持动态注册和发现
  - 非侵入式：不影响现有单 Agent 工作模式

使用场景：
  Agent 1 作为 Orchestrator，协调多个 Specialist Agent
  协作文档生成、游戏开发、数据分析等复杂任务

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations


import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

SANDBOX_DIR = Path(__file__).resolve().parent.parent
AGENT_FILE = SANDBOX_DIR / "memory" / "agents.json"


# ── 错误类型 ──────────────────────────────────────────────


class AgentManagerError(RuntimeError):
    """Agent Manager 错误。"""


# ── 枚举 ──────────────────────────────────────────────────


class AgentStatus(str, Enum):
    """Agent 运行状态。"""
    IDLE = "idle"          # 空闲，可接收任务
    BUSY = "busy"          # 忙碌，正在处理任务
    ERROR = "error"        # 错误状态
    OFFLINE = "offline"    # 离线/未注册


class AgentCapability(str, Enum):
    """预定义的 Agent 能力类型。"""
    # 信息处理
    RESEARCH = "research"               # 信息检索与研究
    ANALYSIS = "analysis"               # 数据分析与洞察
    WRITING = "writing"                 # 内容创作与文案
    REVIEW = "review"                   # 质量审查与校验

    # 技术实现
    CODING = "coding"                   # 代码编写
    TESTING = "testing"                 # 测试验证
    DEBUGGING = "debugging"             # 调试修复
    DESIGN = "design"                   # 架构设计

    # 监控与管理
    MONITORING = "monitoring"           # 系统监控
    ORCHESTRATION = "orchestration"     # 任务编排与协调
    DECISION = "decision"              # 决策支持

    # 创意与内容
    CREATIVE = "creative"              # 创意生成
    SUMMARIZATION = "summarization"    # 摘要总结
    TRANSLATION = "translation"        # 翻译


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class AgentRegistration:
    """Agent 注册信息。"""
    agent_id: str                        # 唯一标识符
    name: str                            # 显示名称
    role_description: str                # 角色描述
    capabilities: list[str] = field(default_factory=list)  # 能力列表
    available_tools: list[str] = field(default_factory=list)  # 可用工具列表
    status: str = AgentStatus.IDLE.value  # 当前状态
    current_task: str = ""               # 正在执行的任务
    task_count: int = 0                  # 累计任务数
    success_count: int = 0               # 成功任务数
    fail_count: int = 0                  # 失败任务数
    last_heartbeat: str = ""             # 上次心跳时间
    registered_at: str = ""              # 注册时间
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    @property
    def success_rate(self) -> float:
        """计算成功率。"""
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role_description": self.role_description,
            "capabilities": self.capabilities,
            "available_tools": self.available_tools,
            "status": self.status,
            "current_task": self.current_task,
            "task_count": self.task_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_heartbeat": self.last_heartbeat,
            "registered_at": self.registered_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRegistration:
        """从字典恢复。"""
        return cls(
            agent_id=data.get("agent_id", ""),
            name=data.get("name", ""),
            role_description=data.get("role_description", ""),
            capabilities=data.get("capabilities", []),
            available_tools=data.get("available_tools", []),
            status=data.get("status", AgentStatus.IDLE.value),
            current_task=data.get("current_task", ""),
            task_count=data.get("task_count", 0),
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
            last_heartbeat=data.get("last_heartbeat", ""),
            registered_at=data.get("registered_at", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentTaskRecord:
    """Agent 任务执行记录。"""
    task_id: str
    agent_id: str
    description: str
    assigned_at: str
    status: str = "assigned"   # assigned | running | done | failed
    completed_at: str = ""
    result: str = ""
    error: str = ""
    duration: float = 0.0      # 执行耗时（秒）


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "agent_manager",
        "description": (
            "Agent 注册管理系统。支持注册、发现、状态管理和健康监控。"
            "用于多智能体协同场景，让 Agent 1 作为 Orchestrator "
            "协调多个 Specialist Agent 的工作。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "register",
                        "unregister",
                        "discover",
                        "status",
                        "list",
                        "heartbeat",
                        "assign_task",
                        "complete_task",
                        "task_failed",
                        "report",
                        "reset",
                    ],
                    "description": (
                        "操作类型："
                        "register — 注册一个新 Agent；"
                        "unregister — 注销一个 Agent；"
                        "discover — 按能力查找可用 Agent；"
                        "status — 查看特定 Agent 的状态；"
                        "list — 列出所有已注册的 Agent；"
                        "heartbeat — Agent 发送心跳；"
                        "assign_task — 分配任务给 Agent；"
                        "complete_task — Agent 完成任务；"
                        "task_failed — Agent 任务失败；"
                        "report — 生成所有 Agent 的健康报告；"
                        "reset — 重置所有 Agent 状态。"
                    ),
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 唯一标识符",
                    "default": "",
                },
                "name": {
                    "type": "string",
                    "description": "Agent 显示名称（用于 register）",
                    "default": "",
                },
                "role": {
                    "type": "string",
                    "description": "Agent 角色描述（用于 register）",
                    "default": "",
                },
                "capabilities": {
                    "type": "string",
                    "description": "能力列表 JSON 字符串，如 '[\"research\",\"writing\"]'",
                    "default": "",
                },
                "tools": {
                    "type": "string",
                    "description": "可用工具列表 JSON 字符串，如 '[\"web_search\",\"knowledge\"]'",
                    "default": "",
                },
                "capability": {
                    "type": "string",
                    "description": "要查找的能力名称（用于 discover）",
                    "default": "",
                },
                "task_id": {
                    "type": "string",
                    "description": "任务 ID",
                    "default": "",
                },
                "task_description": {
                    "type": "string",
                    "description": "任务描述",
                    "default": "",
                },
                "result": {
                    "type": "string",
                    "description": "任务执行结果或错误信息",
                    "default": "",
                },
                "metadata": {
                    "type": "string",
                    "description": "额外元数据 JSON 字符串",
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── Agent Manager 核心 ────────────────────────────────────


class AgentManager:
    """
    Agent 注册与管理核心。
    
    管理所有 Agent 的生命周期，包括注册、状态跟踪、心跳检测。
    支持按能力发现 Agent，为任务调度提供基础。
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}
        self._task_records: list[AgentTaskRecord] = []
        self._load()

    # ── 持久化 ──────────────────────────────────────────

    def _load(self) -> None:
        """从文件加载 Agent 数据。"""
        if AGENT_FILE.is_file():
            try:
                raw = json.loads(AGENT_FILE.read_text(encoding="utf-8"))
                for agent_data in raw.get("agents", []):
                    agent = AgentRegistration.from_dict(agent_data)
                    self._agents[agent.agent_id] = agent
                for task_data in raw.get("task_records", []):
                    self._task_records.append(AgentTaskRecord(**task_data))
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        """保存 Agent 数据到文件。"""
        AGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "agents": [agent.to_dict() for agent in self._agents.values()],
            "task_records": [
                asdict(record) for record in self._task_records
            ],
        }
        AGENT_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 生成唯一 ID ─────────────────────────────────────

    def _generate_agent_id(self, name: str) -> str:
        """根据名称生成唯一 Agent ID。"""
        base = name.lower().replace(" ", "_").replace("-", "_")
        # 去除特殊字符
        base = "".join(c for c in base if c.isalnum() or c == "_")
        if not base:
            base = "agent"

        if base not in self._agents:
            return base

        # 如果已存在，添加数字后缀
        suffix = 1
        while f"{base}_{suffix}" in self._agents:
            suffix += 1
        return f"{base}_{suffix}"

    # ── Agent 生命周期管理 ─────────────────────────────

    def register(
        self,
        name: str = "",
        role: str = "",
        capabilities: str = "",
        tools: str = "",
        agent_id: str = "",
        metadata: str = "",
    ) -> str:
        """注册一个新的 Agent。"""
        # 验证必填字段
        if not name.strip():
            raise AgentManagerError("Agent 名称不能为空")

        # 解析能力列表
        cap_list: list[str] = []
        if capabilities:
            try:
                cap_list = json.loads(capabilities)
                if not isinstance(cap_list, list):
                    raise AgentManagerError("capabilities 必须是 JSON 数组")
            except json.JSONDecodeError as exc:
                raise AgentManagerError(f"capabilities JSON 解析错误: {exc}")

        # 解析工具列表
        tool_list: list[str] = []
        if tools:
            try:
                tool_list = json.loads(tools)
                if not isinstance(tool_list, list):
                    raise AgentManagerError("tools 必须是 JSON 数组")
            except json.JSONDecodeError as exc:
                raise AgentManagerError(f"tools JSON 解析错误: {exc}")

        # 解析元数据
        meta: dict[str, Any] = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise AgentManagerError(f"metadata JSON 解析错误: {exc}")

        # 生成或使用指定的 ID
        final_id = agent_id.strip() or self._generate_agent_id(name)

        if final_id in self._agents:
            raise AgentManagerError(
                f"Agent ID '{final_id}' 已存在。如需重新注册，请先注销。"
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agent = AgentRegistration(
            agent_id=final_id,
            name=name.strip(),
            role_description=role.strip(),
            capabilities=cap_list,
            available_tools=tool_list,
            status=AgentStatus.IDLE.value,
            last_heartbeat=now,
            registered_at=now,
            metadata=meta,
        )

        self._agents[final_id] = agent
        self._save()

        # 格式化输出
        cap_str = ", ".join(cap_list) if cap_list else "无"
        tool_str = ", ".join(tool_list) if tool_list else "无"

        return (
            f"✅ Agent 注册成功\n"
            f"{'─'*40}\n"
            f"ID:     {final_id}\n"
            f"名称:   {name}\n"
            f"角色:   {role or '未指定'}\n"
            f"能力:   {cap_str}\n"
            f"工具:   {tool_str}\n"
            f"状态:   {AgentStatus.IDLE.value}\n"
            f"时间:   {now}"
        )

    def unregister(self, agent_id: str) -> str:
        """注销一个 Agent。"""
        if not agent_id:
            raise AgentManagerError("请指定要注销的 Agent ID")

        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

        if agent.status == AgentStatus.BUSY.value:
            raise AgentManagerError(
                f"Agent '{agent_id}' 正在执行任务，无法注销。"
                f"请先等待任务完成。"
            )

        name = agent.name
        del self._agents[agent_id]
        self._save()

        return f"🗑️ Agent '{name}' ({agent_id}) 已注销"

    def discover(self, capability: str = "") -> str:
        """按能力查找可用 Agent。"""
        if not capability:
            return "请指定要查找的能力名称"

        matching = [
            agent for agent in self._agents.values()
            if capability in agent.capabilities
            and agent.status != AgentStatus.OFFLINE.value
        ]

        if not matching:
            return (
                f"🔍 未找到具备能力 '{capability}' 的可用 Agent\n"
                f"当前已注册 Agent: {len(self._agents)} 个"
            )

        lines = [
            f"🔍 查找能力: '{capability}'",
            f"找到 {len(matching)} 个匹配的 Agent:\n",
        ]

        for agent in matching:
            status_icon = {
                AgentStatus.IDLE.value: "🟢",
                AgentStatus.BUSY.value: "🟡",
                AgentStatus.ERROR.value: "🔴",
            }.get(agent.status, "⚪")

            lines.append(
                f"  {status_icon} [{agent.agent_id}] {agent.name}"
            )
            if agent.role_description:
                lines.append(f"     角色: {agent.role_description}")
            lines.append(f"     状态: {agent.status}")
            if agent.current_task:
                lines.append(f"     当前任务: {agent.current_task[:60]}")
            lines.append(f"     成功率: {agent.success_rate:.0%}")
            lines.append("")

        return "\n".join(lines)

    def get_status(self, agent_id: str = "") -> str:
        """查看 Agent 状态。"""
        if agent_id:
            agent = self._agents.get(agent_id)
            if not agent:
                raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

            status_icon = {
                AgentStatus.IDLE.value: "🟢",
                AgentStatus.BUSY.value: "🟡",
                AgentStatus.ERROR.value: "🔴",
                AgentStatus.OFFLINE.value: "⚫",
            }.get(agent.status, "⚪")

            lines = [
                f"📊 Agent 状态: [{agent.agent_id}] {agent.name}",
                f"{'─'*40}",
                f"{status_icon} 状态: {agent.status}",
            ]
            if agent.role_description:
                lines.append(f"🎭 角色: {agent.role_description}")
            if agent.capabilities:
                lines.append(f"💪 能力: {', '.join(agent.capabilities)}")
            if agent.available_tools:
                lines.append(f"🔧 工具: {', '.join(agent.available_tools)}")
            if agent.current_task:
                lines.append(f"📋 当前任务: {agent.current_task}")
            lines.append(f"📈 任务统计: {agent.task_count} 总 | "
                         f"✅ {agent.success_count} 成功 | "
                         f"❌ {agent.fail_count} 失败")
            lines.append(f"📊 成功率: {agent.success_rate:.0%}")
            lines.append(f"🕐 注册时间: {agent.registered_at}")
            lines.append(f"💓 最后心跳: {agent.last_heartbeat}")

            return "\n".join(lines)

        # 没有指定 agent_id，列出所有
        return self.list_agents()

    def list_agents(self) -> str:
        """列出所有已注册的 Agent。"""
        if not self._agents:
            return "📋 暂无已注册的 Agent。使用 register 注册第一个 Agent。"

        lines = [f"📋 Agent 注册列表 (共 {len(self._agents)} 个):\n"]

        # 按状态排序：空闲优先
        sorted_agents = sorted(
            self._agents.values(),
            key=lambda a: (
                0 if a.status == AgentStatus.IDLE.value else
                1 if a.status == AgentStatus.BUSY.value else
                2 if a.status == AgentStatus.ERROR.value else 3
            ),
        )

        for agent in sorted_agents:
            status_icon = {
                AgentStatus.IDLE.value: "🟢",
                AgentStatus.BUSY.value: "🟡",
                AgentStatus.ERROR.value: "🔴",
                AgentStatus.OFFLINE.value: "⚫",
            }.get(agent.status, "⚪")

            cap_summary = ", ".join(agent.capabilities[:3])
            if len(agent.capabilities) > 3:
                cap_summary += f" … +{len(agent.capabilities) - 3}"

            lines.append(
                f"  {status_icon} [{agent.agent_id}] {agent.name}"
            )
            lines.append(f"     角色: {agent.role_description or '未指定'}")
            lines.append(f"     状态: {agent.status} | "
                         f"能力: {cap_summary or '无'}")
            if agent.current_task:
                lines.append(f"     任务: {agent.current_task[:50]}")
            lines.append("")

        return "\n".join(lines)

    def heartbeat(self, agent_id: str = "") -> str:
        """Agent 发送心跳。"""
        if not agent_id:
            raise AgentManagerError("请指定要发送心跳的 Agent ID")

        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agent.last_heartbeat = now

        # 如果 Agent 处于错误状态但发送了心跳，自动恢复为空闲
        if agent.status == AgentStatus.ERROR.value:
            agent.status = AgentStatus.IDLE.value

        self._save()

        return f"💓 Agent '{agent.name}' ({agent_id}) 心跳已更新: {now}"

    # ── 任务管理 ─────────────────────────────────────────

    def assign_task(
        self,
        agent_id: str = "",
        task_id: str = "",
        task_description: str = "",
    ) -> str:
        """分配任务给 Agent。"""
        if not agent_id:
            raise AgentManagerError("请指定目标 Agent ID")
        if not task_description:
            raise AgentManagerError("请提供任务描述")

        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

        if agent.status == AgentStatus.BUSY.value:
            return (
                f"⚠️ Agent '{agent.name}' ({agent_id}) 正在忙碌中\n"
                f"当前任务: {agent.current_task[:60]}\n"
                f"请等待任务完成后再分配新任务"
            )

        if agent.status == AgentStatus.OFFLINE.value:
            return f"⚠️ Agent '{agent.name}' ({agent_id}) 当前离线"

        # 生成任务 ID
        final_task_id = task_id.strip() or f"T{int(time.time())}"

        # 更新 Agent 状态
        agent.status = AgentStatus.BUSY.value
        agent.current_task = task_description
        agent.task_count += 1

        # 记录任务
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = AgentTaskRecord(
            task_id=final_task_id,
            agent_id=agent_id,
            description=task_description,
            assigned_at=now,
            status="assigned",
        )
        self._task_records.append(record)

        self._save()

        return (
            f"📋 任务已分配\n"
            f"{'─'*40}\n"
            f"任务 ID:   {final_task_id}\n"
            f"Agent:     [{agent_id}] {agent.name}\n"
            f"描述:      {task_description}\n"
            f"状态:      已分配\n"
            f"时间:      {now}\n"
            f"\n"
            f"Agent 完成任务后，使用 complete_task 报告结果"
        )

    def complete_task(
        self,
        agent_id: str = "",
        task_id: str = "",
        result: str = "",
    ) -> str:
        """Agent 报告任务完成。"""
        if not agent_id:
            raise AgentManagerError("请指定 Agent ID")

        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

        # 更新 Agent 状态
        agent.status = AgentStatus.IDLE.value
        agent.success_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新任务记录
        task_record = None
        if task_id:
            for record in self._task_records:
                if record.task_id == task_id and record.agent_id == agent_id:
                    record.status = "done"
                    record.completed_at = now
                    record.result = result
                    task_record = record
                    break

        task_detail = agent.current_task
        agent.current_task = ""
        self._save()

        return (
            f"✅ Agent 任务完成\n"
            f"{'─'*40}\n"
            f"Agent:     [{agent_id}] {agent.name}\n"
            f"任务:      {task_detail}\n"
            f"结果:      {result[:200] if result else '无详细结果'}\n"
            f"状态:      成功 ✅\n"
            f"累计成功率: {agent.success_rate:.0%}"
        )

    def task_failed(
        self,
        agent_id: str = "",
        task_id: str = "",
        error: str = "",
    ) -> str:
        """Agent 报告任务失败。"""
        if not agent_id:
            raise AgentManagerError("请指定 Agent ID")

        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentManagerError(f"未找到 Agent: '{agent_id}'")

        # 更新 Agent 状态
        agent.status = AgentStatus.IDLE.value
        agent.fail_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新任务记录
        if task_id:
            for record in self._task_records:
                if record.task_id == task_id and record.agent_id == agent_id:
                    record.status = "failed"
                    record.completed_at = now
                    record.error = error
                    break

        task_detail = agent.current_task
        agent.current_task = ""
        self._save()

        return (
            f"❌ Agent 任务失败\n"
            f"{'─'*40}\n"
            f"Agent:     [{agent_id}] {agent.name}\n"
            f"任务:      {task_detail}\n"
            f"错误:      {error[:200] if error else '未知错误'}\n"
            f"状态:      失败 ❌\n"
            f"累计成功率: {agent.success_rate:.0%}\n"
            f"\n"
            f"💡 建议：检查错误原因后重新分配任务"
        )

    # ── 报告 ─────────────────────────────────────────────

    def report(self) -> str:
        """生成所有 Agent 的健康报告。"""
        if not self._agents:
            return "📊 暂无已注册的 Agent"

        total = len(self._agents)
        idle = sum(1 for a in self._agents.values() if a.status == AgentStatus.IDLE.value)
        busy = sum(1 for a in self._agents.values() if a.status == AgentStatus.BUSY.value)
        error = sum(1 for a in self._agents.values() if a.status == AgentStatus.ERROR.value)
        offline = sum(1 for a in self._agents.values() if a.status == AgentStatus.OFFLINE.value)

        total_tasks = sum(a.task_count for a in self._agents.values())
        total_success = sum(a.success_count for a in self._agents.values())
        total_fail = sum(a.fail_count for a in self._agents.values())
        overall_rate = total_success / total_tasks if total_tasks else 1.0

        # 检查心跳健康（最近5分钟内有心跳的视为健康）
        now = datetime.now()
        healthy_heartbeats = 0
        for agent in self._agents.values():
            if agent.last_heartbeat:
                try:
                    hb_time = datetime.strptime(
                        agent.last_heartbeat, "%Y-%m-%d %H:%M:%S"
                    )
                    if (now - hb_time).total_seconds() < 300:  # 5分钟
                        healthy_heartbeats += 1
                except ValueError:
                    pass

        lines = [
            f"📊 Agent 系统健康报告",
            f"{'='*50}",
            f"🏢 总览",
            f"  Agent 总数:   {total}",
            f"  🟢 空闲:      {idle}",
            f"  🟡 忙碌:      {busy}",
            f"  🔴 异常:      {error}",
            f"  ⚫ 离线:      {offline}",
            f"",
            f"📈 任务统计",
            f"  总任务数:     {total_tasks}",
            f"  ✅ 成功:      {total_success}",
            f"  ❌ 失败:      {total_fail}",
            f"  📊 成功率:    {overall_rate:.1%}",
            f"",
            f"💓 心跳健康",
            f"  健康 (5分钟内): {healthy_heartbeats}/{total}",
            f"",
        ]

        if self._agents:
            lines.append(f"{'─'*50}")
            lines.append(f"各 Agent 详情:\n")
            for agent in self._agents.values():
                lines.append(
                    f"  [{agent.agent_id}] {agent.name}"
                )
                lines.append(f"     状态: {agent.status} | "
                             f"任务: {agent.task_count}次 | "
                             f"成功率: {agent.success_rate:.0%}")

                if agent.current_task:
                    lines.append(f"     当前: {agent.current_task[:50]}")

                # 心跳状态
                hb_status = "✅ 健康" if agent.last_heartbeat else "❌ 无心跳"
                lines.append(f"     心跳: {hb_status}")
                lines.append("")

        return "\n".join(lines)

    def reset(self) -> str:
        """重置所有 Agent 状态（保留注册信息）。"""
        count = 0
        for agent in self._agents.values():
            if agent.status != AgentStatus.OFFLINE.value:
                agent.status = AgentStatus.IDLE.value
                agent.current_task = ""
            count += 1

        self._save()

        return (
            f"🔄 已重置 {count} 个 Agent 的状态\n"
            f"所有忙碌/异常状态的 Agent 已恢复为空闲"
        )


# ── 预定义 Specialist Agent 工厂 ───────────────────────────


def create_default_specialists(manager: AgentManager) -> list[str]:
    """
    创建默认的 Specialist Agent 集合。
    
    返回创建的 Agent ID 列表。
    """
    created = []

    # 预定义的 Specialist 配置
    specialists = [
        {
            "name": "Researcher",
            "role": "信息检索与研究专家 - 擅长联网搜索、知识库查询和信息整合",
            "capabilities": ["research", "summarization", "analysis"],
            "tools": ["web_search", "knowledge", "file_utils"],
            "metadata": {"specialist_type": "researcher", "priority": 1},
        },
        {
            "name": "Writer",
            "role": "内容创作与文案专家 - 擅长撰写文章、报告、创意内容",
            "capabilities": ["writing", "creative", "summarization"],
            "tools": ["knowledge", "file_utils"],
            "metadata": {"specialist_type": "writer", "priority": 2},
        },
        {
            "name": "Analyst",
            "role": "数据分析与洞察专家 - 擅长数据处理、统计分析和洞察提炼",
            "capabilities": ["analysis", "summarization", "decision"],
            "tools": ["calculate", "file_utils", "knowledge", "monitor"],
            "metadata": {"specialist_type": "analyst", "priority": 3},
        },
        {
            "name": "Reviewer",
            "role": "质量审查与校验专家 - 擅长检查质量、验证完整性和提出改进",
            "capabilities": ["review", "testing", "debugging"],
            "tools": ["self_check", "test_runner", "safety_net", "knowledge"],
            "metadata": {"specialist_type": "reviewer", "priority": 4},
        },
        {
            "name": "Monitor",
            "role": "系统监控与性能分析专家 - 擅长监控系统状态、分析性能和生成报告",
            "capabilities": ["monitoring", "analysis"],
            "tools": ["monitor", "file_utils", "knowledge"],
            "metadata": {"specialist_type": "monitor", "priority": 5},
        },
        {
            "name": "Designer",
            "role": "架构设计与方案规划专家 - 擅长设计方案、规划架构和评估可行性",
            "capabilities": ["design", "analysis", "decision"],
            "tools": ["knowledge", "file_utils", "task_tracker"],
            "metadata": {"specialist_type": "designer", "priority": 6},
        },
    ]

    for spec in specialists:
        # 幂等：若同名 Agent 已存在，直接复用其 ID，避免生成 researcher_1 等重复
        base_id = spec["name"].lower().replace(" ", "_").replace("-", "_")
        base_id = "".join(c for c in base_id if c.isalnum() or c == "_") or "agent"
        if base_id in manager._agents:
            created.append(base_id)
            continue
        try:
            result = manager.register(
                name=spec["name"],
                role=spec["role"],
                capabilities=json.dumps(spec["capabilities"]),
                tools=json.dumps(spec["tools"]),
                metadata=json.dumps(spec["metadata"]),
            )
            # 从结果中提取 agent_id
            for line in result.split("\n"):
                if line.startswith("ID:"):
                    agent_id = line.split(":")[1].strip()
                    created.append(agent_id)
                    break
        except AgentManagerError:
            # 如果已存在，跳过
            pass

    return created


# ── 全局实例 ──────────────────────────────────────────────

_manager = AgentManager()


def execute_agent_manager_tool(arguments: dict[str, Any]) -> str:
    """执行 agent_manager 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "register":
            return _manager.register(
                name=arguments.get("name", ""),
                role=arguments.get("role", ""),
                capabilities=arguments.get("capabilities", ""),
                tools=arguments.get("tools", ""),
                agent_id=arguments.get("agent_id", ""),
                metadata=arguments.get("metadata", ""),
            )

        elif action == "unregister":
            return _manager.unregister(arguments.get("agent_id", ""))

        elif action == "discover":
            return _manager.discover(arguments.get("capability", ""))

        elif action == "status":
            return _manager.get_status(arguments.get("agent_id", ""))

        elif action == "list":
            return _manager.list_agents()

        elif action == "heartbeat":
            return _manager.heartbeat(arguments.get("agent_id", ""))

        elif action == "assign_task":
            return _manager.assign_task(
                agent_id=arguments.get("agent_id", ""),
                task_id=arguments.get("task_id", ""),
                task_description=arguments.get("task_description", ""),
            )

        elif action == "complete_task":
            return _manager.complete_task(
                agent_id=arguments.get("agent_id", ""),
                task_id=arguments.get("task_id", ""),
                result=arguments.get("result", ""),
            )

        elif action == "task_failed":
            return _manager.task_failed(
                agent_id=arguments.get("agent_id", ""),
                task_id=arguments.get("task_id", ""),
                error=arguments.get("result", ""),
            )

        elif action == "report":
            return _manager.report()

        elif action == "reset":
            return _manager.reset()

        else:
            return f"未知操作: {action}"

    except AgentManagerError as exc:
        return f"Agent Manager 错误: {exc}"
