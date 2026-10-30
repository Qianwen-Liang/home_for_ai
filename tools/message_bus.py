"""
message_bus — Agent 间消息通信系统（F2）
=========================================
为多智能体协同提供可靠的消息传递机制。

核心特性（AutoGen 启发）：
  - 点对点消息（direct send）
  - 广播消息（broadcast）
  - 主题订阅（publish/subscribe）
  - 优先级队列
  - 消息持久化
  - 消息历史追溯

设计原则：
  - 异步非阻塞：发送消息不阻塞
  - 可靠传递：消息持久化，不丢失
  - 优先级调度：高优先���消息优先处理
  - 完全解耦：发送方不需要知道接收方实现细节

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

SANDBOX_DIR = Path(__file__).resolve().parent.parent
MESSAGE_FILE = SANDBOX_DIR / "memory" / "messages.json"


# ── 错误类型 ──────────────────────────────────────────────


class MessageBusError(RuntimeError):
    """消息总线错误。"""


# ── 消息类型枚举 ──────────────────────────────────────────


class MessageType(str):
    """消息类型常量。"""
    TASK = "task"               # 任务分配
    RESULT = "result"           # 任务结果
    QUERY = "query"             # 信息查询
    RESPONSE = "response"       # 查询响应
    NOTIFY = "notify"           # 通知
    ERROR = "error"             # 错误报告
    HEARTBEAT = "heartbeat"     # 心跳
    BROADCAST = "broadcast"     # 广播
    REQUEST = "request"         # 请求
    COMMAND = "command"         # 命令


class MessagePriority(IntEnum):
    """消息优先级（数值越大越优先）。"""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class Message:
    """消息实体。"""
    msg_id: str                              # 唯一消息ID
    msg_type: str                            # 消息类型
    source: str                              # 发送方 agent_id
    target: str                              # 接收方 agent_id（"*" 为广播）
    content: dict[str, Any] = field(default_factory=dict)  # 消息内容
    priority: int = MessagePriority.NORMAL   # 优先级 1-10
    timestamp: str = ""                      # 发送时间
    correlation_id: str = ""                 # 关联的任务/消息ID
    ttl: int = 3600                          # 生存时间（秒），默认1小时
    status: str = "pending"                  # pending/delivered/read/failed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(**data)


@dataclass
class Subscription:
    """订阅信息。"""
    sub_id: str
    agent_id: str
    topic: str                 # 订阅的主题
    pattern: str = ""          # 匹配模式（支持 * 通配符）
    created_at: str = ""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "message_bus",
        "description": (
            "Agent 间消息通信系统。支持点对点发送、广播、主题订阅、"
            "优先级队列。用于多智能体协同场景中的通信协调。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "send",
                        "broadcast",
                        "receive",
                        "subscribe",
                        "unsubscribe",
                        "list_subscriptions",
                        "history",
                        "queue_length",
                        "clear",
                    ],
                    "description": (
                        "操作类型："
                        "send — 发送消息到指定 Agent；"
                        "broadcast — 广播消息给所有 Agent；"
                        "receive — 接收指定 Agent 的消息；"
                        "subscribe — 订阅主题；"
                        "unsubscribe — 取消订阅；"
                        "list_subscriptions — 列出所有订阅；"
                        "history — 查看消息历史；"
                        "queue_length — 查看消息队列长度；"
                        "clear — 清除已处理的消息。"
                    ),
                },
                "target": {
                    "type": "string",
                    "description": "目标 Agent ID（send 操作必需）",
                    "default": "",
                },
                "msg_type": {
                    "type": "string",
                    "enum": [
                        "task", "result", "query", "response",
                        "notify", "error", "heartbeat", "broadcast",
                        "request", "command",
                    ],
                    "description": "消息类型",
                    "default": "notify",
                },
                "content": {
                    "type": "string",
                    "description": "消息内容 JSON 字符串",
                    "default": "{}",
                },
                "priority": {
                    "type": "integer",
                    "description": "消息优先级 1-10（1=低, 5=普通, 8=高, 10=紧急）",
                    "default": 5,
                },
                "correlation_id": {
                    "type": "string",
                    "description": "关联的任务/消息 ID",
                    "default": "",
                },
                "source": {
                    "type": "string",
                    "description": "发送方 Agent ID（可选，默认自动填充）",
                    "default": "",
                },
                "topic": {
                    "type": "string",
                    "description": "订阅主题（subscribe 操作必需）",
                    "default": "",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID（用于 receive/unsubscribe 操作）",
                    "default": "",
                },
                "pattern": {
                    "type": "string",
                    "description": "订阅匹配模式，支持 * 通配符（subscribe 操作可选）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制",
                    "default": 20,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── Message Bus 核心 ──────────────────────────────────────


class MessageBus:
    """
    消息总线核心。
    
    提供 Agent 间的可靠消息传递机制。
    所有消息持久化到文件，重启后不丢失。
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[Message]] = {}      # agent_id -> [messages]
        self._history: list[Message] = []                 # 所有消息历史
        self._subscriptions: dict[str, list[Subscription]] = {}  # topic -> [subs]
        self._load()

    # ── 持久化 ──────────────────────────────────────────

    def _load(self) -> None:
        """从文件加载消息数据。"""
        if MESSAGE_FILE.is_file():
            try:
                raw = json.loads(MESSAGE_FILE.read_text(encoding="utf-8"))

                # 恢复队列
                for agent_id, msgs in raw.get("queues", {}).items():
                    self._queues[agent_id] = [
                        Message.from_dict(m) for m in msgs
                    ]

                # 恢复历史
                self._history = [
                    Message.from_dict(m) for m in raw.get("history", [])
                ]

                # 恢复订阅
                for topic, subs in raw.get("subscriptions", {}).items():
                    self._subscriptions[topic] = [
                        Subscription(**s) for s in subs
                    ]
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                pass

    def _save(self) -> None:
        """保存消息数据到文件。"""
        MESSAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "queues": {
                agent_id: [m.to_dict() for m in msgs]
                for agent_id, msgs in self._queues.items()
            },
            "history": [m.to_dict() for m in self._history],
            "subscriptions": {
                topic: [asdict(s) for s in subs]
                for topic, subs in self._subscriptions.items()
            },
        }
        MESSAGE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 消息发送 ─────────────────────────────────────────

    def send(
        self,
        target: str = "",
        msg_type: str = "notify",
        content: str = "{}",
        priority: int = MessagePriority.NORMAL,
        correlation_id: str = "",
        source: str = "",
    ) -> str:
        """发送消息到指定 Agent。"""
        if not target:
            raise MessageBusError("请指定目标 Agent ID")

        # 解析内容
        content_dict: dict[str, Any] = {}
        if content:
            try:
                content_dict = json.loads(content)
            except json.JSONDecodeError as exc:
                raise MessageBusError(f"content JSON 解析错误: {exc}")

        # 生成消息
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = Message(
            msg_id=self._generate_id(),
            msg_type=msg_type,
            source=source or "orchestrator",
            target=target,
            content=content_dict,
            priority=max(1, min(10, int(priority))),
            timestamp=now,
            correlation_id=correlation_id,
        )

        # 添加到目标队列
        if target not in self._queues:
            self._queues[target] = []
        self._queues[target].append(msg)

        # 按优先级排序
        self._queues[target].sort(key=lambda m: m.priority, reverse=True)

        # 记录历史
        self._history.append(msg)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        self._save()

        queue_len = len(self._queues[target])
        return (
            f"📨 消息已发送\n"
            f"  ID:       {msg.msg_id}\n"
            f"  类型:     {msg_type}\n"
            f"  从:       {msg.source}\n"
            f"  到:       {target}\n"
            f"  优先级:   {priority}\n"
            f"  队列长度: {queue_len}\n"
            f"  时间:     {now}"
        )

    def broadcast(
        self,
        msg_type: str = "broadcast",
        content: str = "{}",
        priority: int = MessagePriority.NORMAL,
        source: str = "",
    ) -> str:
        """广播消息给所有已注册的 Agent。"""
        # 解析内容
        content_dict: dict[str, Any] = {}
        if content:
            try:
                content_dict = json.loads(content)
            except json.JSONDecodeError as exc:
                raise MessageBusError(f"content JSON 解析错误: {exc}")

        # 获取所有 Agent ID
        from tools.agent_manager import _manager
        agent_ids = list(_manager._agents.keys())
        
        if not agent_ids:
            return "📢 广播消息：暂无已注册的 Agent，消息未投递"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sent_count = 0

        for agent_id in agent_ids:
            msg = Message(
                msg_id=self._generate_id(),
                msg_type=msg_type,
                source=source or "orchestrator",
                target=agent_id,
                content=content_dict,
                priority=max(1, min(10, int(priority))),
                timestamp=now,
            )

            if agent_id not in self._queues:
                self._queues[agent_id] = []
            self._queues[agent_id].append(msg)
            self._queues[agent_id].sort(key=lambda m: m.priority, reverse=True)
            self._history.append(msg)
            sent_count += 1

        # 限制历史长度
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        self._save()

        return (
            f"📢 广播消息已发送\n"
            f"  类型:     {msg_type}\n"
            f"  从:       {source or 'orchestrator'}\n"
            f"  送达:     {sent_count} 个 Agent\n"
            f"  优先级:   {priority}\n"
            f"  时间:     {now}"
        )

    # ── 消息接收 ─────────────────────────────────────────

    def receive(self, agent_id: str = "", limit: int = 20) -> str:
        """Agent 接收自己的消息。"""
        if not agent_id:
            raise MessageBusError("请指定 Agent ID")

        queue = self._queues.get(agent_id, [])

        if not queue:
            return f"📭 Agent '{agent_id}' 的消息队列为空"

        # 按优先级排序返回
        sorted_queue = sorted(queue, key=lambda m: m.priority, reverse=True)
        messages = sorted_queue[:limit]

        lines = [
            f"📬 Agent '{agent_id}' 的消息队列 ({len(queue)} 条待处理):",
            f"{'─'*60}",
        ]

        for i, msg in enumerate(messages, 1):
            priority_str = {
                10: "🔴 紧急",
                8: "🟠 高",
                5: "🟡 普通",
                1: "🟢 低",
            }.get(msg.priority, f"优先级{msg.priority}")

            content_summary = json.dumps(msg.content, ensure_ascii=False)
            if len(content_summary) > 60:
                content_summary = content_summary[:57] + "..."

            lines.append(
                f"\n{i}. [{priority_str}] {msg.msg_type}"
            )
            lines.append(f"   ID:   {msg.msg_id[:16]}...")
            lines.append(f"   来源: {msg.source}")
            lines.append(f"   内容: {content_summary}")
            if msg.correlation_id:
                lines.append(f"   关联: {msg.correlation_id}")
            lines.append(f"   时间: {msg.timestamp}")

        return "\n".join(lines)

    # ── 订阅管理 ─────────────────────────────────────────

    def subscribe(
        self,
        agent_id: str = "",
        topic: str = "",
        pattern: str = "",
    ) -> str:
        """Agent 订阅主题。"""
        if not agent_id:
            raise MessageBusError("请指定 Agent ID")
        if not topic:
            raise MessageBusError("请指定订阅主题")

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []

        # 检查是否已订阅
        for sub in self._subscriptions[topic]:
            if sub.agent_id == agent_id:
                return f"ℹ️ Agent '{agent_id}' 已订阅主题 '{topic}'"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sub = Subscription(
            sub_id=f"sub_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            topic=topic,
            pattern=pattern,
            created_at=now,
        )
        self._subscriptions[topic].append(sub)
        self._save()

        return (
            f"🔔 Agent '{agent_id}' 已订阅主题 '{topic}'\n"
            f"  订阅ID: {sub.sub_id}\n"
            f"  模式: {pattern or '精确匹配'}"
        )

    def unsubscribe(self, agent_id: str = "", topic: str = "") -> str:
        """Agent 取消订阅。"""
        if not agent_id:
            raise MessageBusError("请指定 Agent ID")
        if not topic:
            raise MessageBusError("请指定主题")

        subs = self._subscriptions.get(topic, [])
        before = len(subs)
        self._subscriptions[topic] = [
            s for s in subs if s.agent_id != agent_id
        ]
        removed = before - len(self._subscriptions[topic])

        if removed == 0:
            # 可能在所有主题中查找
            total_removed = 0
            for t in list(self._subscriptions.keys()):
                before = len(self._subscriptions[t])
                self._subscriptions[t] = [
                    s for s in self._subscriptions[t] if s.agent_id != agent_id
                ]
                total_removed += before - len(self._subscriptions[t])

            if total_removed == 0:
                return f"ℹ️ Agent '{agent_id}' 未订阅任何主题"

            self._save()
            return f"🔕 Agent '{agent_id}' 已取消所有订阅 ({total_removed} 个)"

        self._save()
        return f"🔕 Agent '{agent_id}' 已取消订阅主题 '{topic}'"

    def list_subscriptions(self, topic: str = "") -> str:
        """列出所有订阅。"""
        if not self._subscriptions:
            return "📋 暂无订阅"

        lines = ["📋 订阅列表:\n"]

        if topic:
            subs = self._subscriptions.get(topic, [])
            if not subs:
                return f"主题 '{topic}' 暂无订阅"
            lines.append(f"  主题: '{topic}' ({len(subs)} 个订阅):")
            for sub in subs:
                lines.append(f"    - [{sub.sub_id}] {sub.agent_id}")
                if sub.pattern:
                    lines.append(f"      模式: {sub.pattern}")
        else:
            for t, subs in sorted(self._subscriptions.items()):
                agent_list = ", ".join(s.agent_id for s in subs)
                lines.append(f"  📌 '{t}': {len(subs)} 个订阅")
                lines.append(f"     Agent: {agent_list}")
                lines.append("")

        return "\n".join(lines)

    # ── 历史与状态 ───────────────────────────────────────

    def history(
        self,
        agent_id: str = "",
        msg_type: str = "",
        limit: int = 20,
    ) -> str:
        """查看消息历史。"""
        if not self._history:
            return "📜 暂无消息历史"

        # 过滤
        filtered = self._history
        if agent_id:
            filtered = [
                m for m in filtered
                if m.source == agent_id or m.target == agent_id
            ]
        if msg_type:
            filtered = [m for m in filtered if m.msg_type == msg_type]

        # 取最近的
        recent = filtered[-limit:]
        recent.reverse()

        lines = [
            f"📜 消息历史 (共 {len(filtered)} 条匹配，显示最近 {len(recent)} 条):",
            f"{'─'*60}",
        ]

        for msg in recent:
            priority_indicator = {
                10: "🔴", 8: "🟠", 5: "🟡", 1: "🟢",
            }.get(msg.priority, "⚪")

            content_summary = json.dumps(msg.content, ensure_ascii=False)
            if len(content_summary) > 50:
                content_summary = content_summary[:47] + "..."

            lines.append(
                f"\n{priority_indicator} [{msg.msg_type}] "
                f"{msg.source} → {msg.target}"
            )
            lines.append(f"   {content_summary}")
            lines.append(f"   {msg.timestamp}")

        return "\n".join(lines)

    def queue_length(self, agent_id: str = "") -> str:
        """查看消息队列长度。"""
        if agent_id:
            queue = self._queues.get(agent_id, [])
            return (
                f"📊 Agent '{agent_id}' 消息队列: {len(queue)} 条\n"
                + (f"最高优先级: {max(m.priority for m in queue)}\n"
                   if queue else "")
                + (f"最早消息: {queue[0].timestamp[:16]}\n"
                   if queue else "")
            )

        # 所有队列
        if not self._queues:
            return "📊 所有消息队列为空"

        lines = ["📊 消息队列状态:\n"]
        total = 0
        for agent_id, queue in sorted(self._queues.items()):
            if queue:
                lines.append(
                    f"  {agent_id}: {len(queue)} 条 "
                    f"(最高优先级: {max(m.priority for m in queue)})"
                )
                total += len(queue)
            else:
                lines.append(f"  {agent_id}: 空")

        lines.append(f"\n总计: {total} 条待处理消息")
        return "\n".join(lines)

    def clear(self, agent_id: str = "") -> str:
        """清除已处理的消息。"""
        if agent_id:
            queue = self._queues.get(agent_id, [])
            count = len(queue)
            self._queues[agent_id] = []
            self._save()
            return f"🗑️ 已清除 Agent '{agent_id}' 的 {count} 条消息"
        else:
            total = sum(len(q) for q in self._queues.values())
            self._queues.clear()
            self._save()
            return f"🗑️ 已清除所有 {total} 条待处理消息"

    # ── 工具方法 ─────────────────────────────────────────

    @staticmethod
    def _generate_id() -> str:
        """生成唯一消息 ID。"""
        return f"MSG_{uuid.uuid4().hex[:12]}"


# ── 全局实例 ──────────────────────────────────────────────

_bus = MessageBus()


def execute_message_bus_tool(arguments: dict[str, Any]) -> str:
    """执行 message_bus 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "send":
            return _bus.send(
                target=arguments.get("target", ""),
                msg_type=arguments.get("msg_type", "notify"),
                content=arguments.get("content", "{}"),
                priority=arguments.get("priority", MessagePriority.NORMAL),
                correlation_id=arguments.get("correlation_id", ""),
                source=arguments.get("source", ""),
            )

        elif action == "broadcast":
            return _bus.broadcast(
                msg_type=arguments.get("msg_type", "broadcast"),
                content=arguments.get("content", "{}"),
                priority=arguments.get("priority", MessagePriority.NORMAL),
                source=arguments.get("source", ""),
            )

        elif action == "receive":
            return _bus.receive(
                agent_id=arguments.get("agent_id", ""),
                limit=arguments.get("limit", 20),
            )

        elif action == "subscribe":
            return _bus.subscribe(
                agent_id=arguments.get("agent_id", ""),
                topic=arguments.get("topic", ""),
                pattern=arguments.get("pattern", ""),
            )

        elif action == "unsubscribe":
            return _bus.unsubscribe(
                agent_id=arguments.get("agent_id", ""),
                topic=arguments.get("topic", ""),
            )

        elif action == "list_subscriptions":
            return _bus.list_subscriptions(arguments.get("topic", ""))

        elif action == "history":
            return _bus.history(
                agent_id=arguments.get("agent_id", ""),
                msg_type=arguments.get("msg_type", ""),
                limit=arguments.get("limit", 20),
            )

        elif action == "queue_length":
            return _bus.queue_length(arguments.get("agent_id", ""))

        elif action == "clear":
            return _bus.clear(arguments.get("agent_id", ""))

        else:
            return f"未知操作: {action}"

    except MessageBusError as exc:
        return f"Message Bus 错误: {exc}"
