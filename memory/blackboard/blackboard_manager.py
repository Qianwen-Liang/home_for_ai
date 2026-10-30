"""
黑板管理器 — Blackboard Manager (E-C1)

共享工作内存，所有 Agent 可读写中间产物。
设计参考 MetaGPT 的共享消息池 + 黑板架构模式（Blackboard Pattern）。

特性：
  - 发布/订阅模式：Agent 可订阅感兴趣的内容类型
  - 修订历史：保留每次修订的完整记录
  - 文件锁：防止并发写入竞态
  - TTL 自动清理
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# fcntl 仅在 Unix 可用，Windows 回退到无锁模式
try:
    import fcntl
    _HAS_FCNTL = True
except ModuleNotFoundError:
    _HAS_FCNTL = False

# ── 存储目录 ─────────────────────────────────────────────
BOARD_DIR = Path(__file__).resolve().parent
ITEMS_FILE = BOARD_DIR / "items.json"
LOCK_FILE  = BOARD_DIR / ".lock"


class ItemType(str, Enum):
    """黑板条目类型"""
    TASK       = "task"        # 任务描述
    RESULT     = "result"      # 执行结果
    ARTIFACT   = "artifact"    # 中间产物（代码、文档片段等）
    DECISION   = "decision"    # 决策记录
    FEEDBACK   = "feedback"    # 反馈意见
    ANNOUNCEMENT = "announcement"  # 公告/通知


class ItemStatus(str, Enum):
    """条目状态"""
    DRAFT     = "draft"
    REVIEW    = "review"
    FINAL     = "final"
    DEPRECATED = "deprecated"


@dataclass
class RevisionRecord:
    """单次修订记录"""
    rev_id: str
    timestamp: str
    author: str
    previous_content: str
    change_summary: str = ""


@dataclass
class BoardItem:
    """黑板条目"""
    item_id: str
    item_type: ItemType
    content: str
    author: str                          # 创建者 Agent ID
    status: ItemStatus = ItemStatus.DRAFT
    tags: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None      # 关联父条目
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    revision_history: List[RevisionRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["item_type"] = self.item_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BoardItem":
        d = dict(d)  # shallow copy
        d["item_type"] = ItemType(d.pop("item_type", "artifact"))
        d["status"] = ItemStatus(d.pop("status", "draft"))
        d["revision_history"] = [RevisionRecord(**r) for r in d.get("revision_history", [])]
        return cls(**d)


# ── 黑板主类 ──────────────────────────────────────────────

class Blackboard:
    """
    共享黑板 — 多 Agent 协作工作内存。

    用法：
        bb = Blackboard()

        # 发布
        item = bb.post(
            item_type=ItemType.ARTIFACT,
            content="...",
            author="evolver",
            tags=["evolution", "plan"],
        )

        # 读取
        results = bb.read(item_type=ItemType.DECISION, author="architect")

        # 订阅
        bb.subscribe(ItemType.FEEDBACK, callback=my_handler)

        # 修订
        bb.revise(item.item_id, new_content="...", author="evolver")

        # 定稿
        bb.finalize(item.item_id)

        # 清理
        bb.cleanup(ttl_days=30)
    """

    MAX_ITEMS = 500
    DEFAULT_TTL_DAYS = 90

    def __init__(self):
        self._items: Dict[str, BoardItem] = {}
        self._subscriptions: Dict[ItemType, List[Callable[[BoardItem], None]]] = {
            t: [] for t in ItemType
        }
        self._load()

    # ── 发布 ────────────────────────────────────────────

    def post(
        self,
        item_type: ItemType,
        content: str,
        author: str,
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BoardItem:
        """发布一条新条目到黑板。"""
        item = BoardItem(
            item_id=f"bb-{uuid.uuid4().hex[:12]}",
            item_type=item_type,
            content=content,
            author=author,
            tags=tags or [],
            parent_id=parent_id,
            metadata=metadata or {},
        )
        self._items[item.item_id] = item
        self._enforce_limit()
        self._save()

        # 通知订阅者
        self._notify(item_type, item)

        return item

    # ── 读取 ────────────────────────────────────────────

    def read(
        self,
        item_id: Optional[str] = None,
        item_type: Optional[ItemType] = None,
        author: Optional[str] = None,
        status: Optional[ItemStatus] = None,
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[BoardItem]:
        """
        读取黑板条目，支持多条件筛选。

        Args:
            item_id: 精确匹配 ID
            item_type: 按类型筛选
            author: 按作者筛选
            status: 按状态筛选
            tags: 按标签筛选（包含任一匹配）
            parent_id: 按父条目筛选
            limit: 最大返回数
        """
        if item_id:
            item = self._items.get(item_id)
            return [item] if item else []

        results = []
        for item in self._items.values():
            if item_type and item.item_type != item_type:
                continue
            if author and item.author != author:
                continue
            if status and item.status != status:
                continue
            if tags and not any(t in item.tags for t in tags):
                continue
            if parent_id and item.parent_id != parent_id:
                continue
            results.append(item)

        # 按时间倒序
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get(self, item_id: str) -> Optional[BoardItem]:
        """按 ID 获取单条条目。"""
        return self._items.get(item_id)

    # ── 修订 ────────────────────────────────────────────

    def revise(
        self,
        item_id: str,
        new_content: str,
        author: str,
        change_summary: str = "",
    ) -> Optional[BoardItem]:
        """
        修订条目，保留修订历史。

        Returns:
            修订后的条目，若条目不存在则返回 None。
        """
        item = self._items.get(item_id)
        if not item:
            return None

        rev = RevisionRecord(
            rev_id=f"rev-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now().isoformat(),
            author=author,
            previous_content=item.content,
            change_summary=change_summary,
        )
        item.revision_history.append(rev)
        item.content = new_content
        self._save()

        # 通知订阅者
        self._notify(item.item_type, item)

        return item

    # ── 状态管理 ────────────────────────────────────────

    def finalize(self, item_id: str) -> Optional[BoardItem]:
        """标记条目为最终版本。"""
        item = self._items.get(item_id)
        if item:
            item.status = ItemStatus.FINAL
            self._save()
        return item

    def deprecate(self, item_id: str) -> Optional[BoardItem]:
        """标记条目为已废弃。"""
        item = self._items.get(item_id)
        if item:
            item.status = ItemStatus.DEPRECATED
            self._save()
        return item

    def set_review(self, item_id: str) -> Optional[BoardItem]:
        """标记条目为待审查。"""
        item = self._items.get(item_id)
        if item:
            item.status = ItemStatus.REVIEW
            self._save()
        return item

    # ── 订阅 ────────────────────────────────────────────

    def subscribe(self, item_type: ItemType, callback: Callable[[BoardItem], None]):
        """
        订阅某种类型的条目变更通知。

        Args:
            item_type: 关注的消息类型
            callback: 收到新消息/修订时的回调函数 callback(item)
        """
        self._subscriptions[item_type].append(callback)

    def _notify(self, item_type: ItemType, item: BoardItem):
        """通知所有相关订阅者。"""
        for cb in self._subscriptions.get(item_type, []):
            try:
                cb(item)
            except Exception:
                pass  # 订阅者异常不应影响黑板

    # ── 清理 ────────────────────────────────────────────

    def cleanup(self, ttl_days: int = DEFAULT_TTL_DAYS) -> int:
        """
        清理过期条目。

        Args:
            ttl_days: 条目保留天数（仅清理 DRAFT 和 DEPRECATED 状态）

        Returns:
            清理的条目数量。
        """
        cutoff = datetime.now() - timedelta(days=ttl_days)
        to_remove = []
        for item_id, item in self._items.items():
            if item.status in (ItemStatus.DRAFT, ItemStatus.DEPRECATED):
                try:
                    ts = datetime.fromisoformat(item.timestamp)
                    if ts < cutoff:
                        to_remove.append(item_id)
                except (ValueError, TypeError):
                    pass

        for item_id in to_remove:
            del self._items[item_id]

        if to_remove:
            self._save()

        return len(to_remove)

    # ── 统计 ────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """黑板统计信息。"""
        type_counts = {t.value: 0 for t in ItemType}
        status_counts = {s.value: 0 for s in ItemStatus}
        author_counts: Dict[str, int] = {}

        for item in self._items.values():
            type_counts[item.item_type.value] = type_counts.get(item.item_type.value, 0) + 1
            status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1
            author_counts[item.author] = author_counts.get(item.author, 0) + 1

        return {
            "total_items": len(self._items),
            "by_type": type_counts,
            "by_status": status_counts,
            "by_author": author_counts,
        }

    # ── 持久化（文件锁防竞态）─────────────────────────────

    def _save(self):
        """保存到文件，使用文件锁防止并发写入（Windows 无 fcntl 时回退到无锁）。"""
        data = {iid: item.to_dict() for iid, item in self._items.items()}
        if _HAS_FCNTL:
            try:
                with open(LOCK_FILE, "w") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    try:
                        ITEMS_FILE.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    finally:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                return
            except OSError:
                pass  # 锁失败则回退到无锁保存
        # 回退：无锁保存
        ITEMS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        """从文件加载。"""
        if not ITEMS_FILE.exists():
            return
        try:
            data = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
            self._items = {iid: BoardItem.from_dict(d) for iid, d in data.items()}
        except (json.JSONDecodeError, KeyError, TypeError):
            self._items = {}

    def _enforce_limit(self):
        """超过上限时移除最旧的条目。"""
        if len(self._items) > self.MAX_ITEMS:
            sorted_items = sorted(self._items.values(), key=lambda x: x.timestamp)
            to_remove = sorted_items[: len(self._items) - self.MAX_ITEMS]
            for item in to_remove:
                del self._items[item.item_id]


# ── 全局单例 ───────────────────────────────────────────────

_blackboard = Blackboard()


# ── 工具函数 ──────────────────────────────────────────────

def execute_blackboard_tool(arguments: dict) -> str:
    """黑板工具入口。"""
    action = arguments.get("action", "read")

    try:
        if action == "post":
            item_type_str = arguments.get("item_type", "artifact")
            content = arguments.get("content", "")
            author = arguments.get("author", "unknown")
            if not content:
                return "❌ 请提供 content 参数（条目内容）。"

            try:
                item_type = ItemType(item_type_str)
            except ValueError:
                valid = ", ".join(t.value for t in ItemType)
                return f"❌ 无效类型: {item_type_str}。可用: {valid}"

            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                import json as _json
                tags = _json.loads(tags)

            item = _blackboard.post(
                item_type=item_type,
                content=content,
                author=author,
                tags=tags,
                parent_id=arguments.get("parent_id"),
                metadata=arguments.get("metadata", {}),
            )
            return f"📌 已发布到黑板: {item.item_id}\n类型: {item.item_type.value} | 作者: {item.author}"

        elif action == "read":
            item_id = arguments.get("item_id")
            item_type_str = arguments.get("item_type")
            item_type = ItemType(item_type_str) if item_type_str else None
            author = arguments.get("author")
            status_str = arguments.get("status")
            status = ItemStatus(status_str) if status_str else None
            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                import json as _json
                tags = _json.loads(tags)
            limit = int(arguments.get("limit", 20))

            results = _blackboard.read(
                item_id=item_id,
                item_type=item_type,
                author=author,
                status=status,
                tags=tags,
                parent_id=arguments.get("parent_id"),
                limit=limit,
            )

            if not results:
                return "📭 黑板上没有匹配的条目。"

            lines = [f"📋 找到 {len(results)} 条黑板条目:"]
            for item in results:
                status_icon = {
                    "draft": "📝", "review": "👀", "final": "✅", "deprecated": "🗑️"
                }.get(item.status.value, "•")
                preview = item.content[:80].replace("\n", " ")
                lines.append(
                    f"  {status_icon} [{item.item_id}] [{item.item_type.value}] "
                    f"by {item.author} — {preview}{'...' if len(item.content) > 80 else ''}"
                )
            return "\n".join(lines)

        elif action == "revise":
            item_id = arguments.get("item_id", "")
            new_content = arguments.get("new_content", "")
            author = arguments.get("author", "unknown")
            change_summary = arguments.get("change_summary", "")
            if not item_id or not new_content:
                return "❌ 请提供 item_id 和 new_content 参数。"

            item = _blackboard.revise(item_id, new_content, author, change_summary)
            if item:
                rev_count = len(item.revision_history)
                return f"✏️ 已修订 {item_id}（第 {rev_count} 次修订）: {change_summary or '(无描述)'}"
            return f"❌ 未找到条目: {item_id}"

        elif action == "finalize":
            item_id = arguments.get("item_id", "")
            item = _blackboard.finalize(item_id)
            if item:
                return f"✅ 已定稿: {item_id}"
            return f"❌ 未找到条目: {item_id}"

        elif action == "deprecate":
            item_id = arguments.get("item_id", "")
            item = _blackboard.deprecate(item_id)
            if item:
                return f"🗑️ 已废弃: {item_id}"
            return f"❌ 未找到条目: {item_id}"

        elif action == "stats":
            stats = _blackboard.stats()
            import json as _json
            return _json.dumps(stats, ensure_ascii=False, indent=2)

        elif action == "cleanup":
            ttl_days = int(arguments.get("ttl_days", 90))
            count = _blackboard.cleanup(ttl_days)
            return f"🧹 已清理 {count} 条过期条目（TTL={ttl_days}天）"

        else:
            return f"未知操作: {action}。可用: post, read, revise, finalize, deprecate, stats, cleanup"

    except Exception as exc:
        return f"黑板错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "blackboard",
        "description": (
            "共享黑板 — 多 Agent 协作工作内存。支持发布、读取、修订、定稿、废弃条目，"
            "保留完整修订历史。Evolver/Debugger/Architect 等 Agent 可在此共享中间产物和决策结果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["post", "read", "revise", "finalize", "deprecate", "stats", "cleanup"],
                    "description": (
                        "操作类型：post — 发布条目；"
                        "read — 读取/搜索条目；"
                        "revise — 修订条目（保留历史）；"
                        "finalize — 定稿；"
                        "deprecate — 废弃；"
                        "stats — 黑板统计；"
                        "cleanup — 清理过期条目"
                    ),
                    "default": "read",
                },
                "item_type": {
                    "type": "string",
                    "enum": ["task", "result", "artifact", "decision", "feedback", "announcement"],
                    "description": "条目类型",
                    "default": "artifact",
                },
                "content": {
                    "type": "string",
                    "description": "条目内容（post 操作必需）",
                    "default": "",
                },
                "new_content": {
                    "type": "string",
                    "description": "修订后的新内容（revise 操作必需）",
                    "default": "",
                },
                "author": {
                    "type": "string",
                    "description": "创建者/修订者 Agent ID",
                    "default": "unknown",
                },
                "item_id": {
                    "type": "string",
                    "description": "条目 ID（用于 read/revise/finalize/deprecate）",
                    "default": "",
                },
                "tags": {
                    "type": "string",
                    "description": "标签 JSON 数组，如 '[\"plan\",\"v2\"]'",
                    "default": "[]",
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "review", "final", "deprecated"],
                    "description": "按状态筛选（用于 read）",
                },
                "parent_id": {
                    "type": "string",
                    "description": "父条目 ID",
                },
                "change_summary": {
                    "type": "string",
                    "description": "修订摘要",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大返回数",
                    "default": 20,
                },
                "ttl_days": {
                    "type": "integer",
                    "description": "清理超过此天数的 DRAFT/DEPRECATED 条目",
                    "default": 90,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


# ── 便捷函数 ──────────────────────────────────────────────

def get_blackboard() -> Blackboard:
    """获取黑板单例。"""
    return _blackboard
