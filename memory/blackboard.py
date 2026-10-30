"""
共享黑板 — Shared Blackboard (E-C1)
================================
多 Agent 协作工作内存。任何 Agent 均可发布/读取/修订/定稿条目，
实现跨 Agent 的状态同步与知识传递。

设计理念（借鉴 Linda Tuple Space + CrewAI 共享上下文）：
  - 发布 (post):     写入一条黑板条目，标记为 draft
  - 读取 (read):     按 ID 或标签查询条目
  - 修订 (revise):   更新条目内容，记录修订历史
  - 定稿 (finalize): 锁定条目为只读，标记为 final
  - 撤销 (revoke):   删除一条条目（仅 draft 可删）
  - 搜索 (search):   按关键词/标签搜索所有条目
  - 摘要 (summary):  黑板状态概览

使用场景：
  - Debugger 诊断结果发布到黑板，Evolver 读取后决策
  - Researcher 搜索结果发布到黑板，Writer/Analyst 读取处理
  - 任务进度同步（各 Agent 发布自己的状态）
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 数据目录 ─────────────────────────────────────────────
MEMORY_DIR = Path(__file__).resolve().parent
BLACKBOARD_FILE = MEMORY_DIR / "blackboard.json"
MAX_ENTRIES = 200


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class BlackboardEntry:
    """单条黑板条目"""
    entry_id: str
    title: str
    content: str
    status: str = "draft"             # draft | revised | final | revoked
    author: str = "agent1"            # 发布者标识
    tags: List[str] = field(default_factory=list)
    priority: str = "中"               # 高 | 中 | 低
    created_at: str = ""
    updated_at: str = ""
    revision_count: int = 0
    revision_history: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BlackboardEntry":
        # 兼容旧数据缺少字段
        d.setdefault("revision_history", [])
        d.setdefault("metadata", {})
        d.setdefault("priority", "中")
        return cls(**d)


# ── 主类 ──────────────────────────────────────────────────


class BlackboardManager:
    """
    共享黑板管理器。

    用法：
        bb = BlackboardManager()
        entry = bb.post("系统状态", "一切正常", author="debugger", tags=["health"])
        results = bb.search("状态")
        bb.revise(entry.entry_id, "系统状态更新", author="evolver")
        bb.finalize(entry.entry_id)
    """

    def __init__(self):
        self._entries: Dict[str, BlackboardEntry] = {}
        self._load()

    # ── 发布 ────────────────────────────────────────────

    def post(
        self,
        title: str,
        content: str,
        author: str = "agent1",
        tags: Optional[List[str]] = None,
        priority: str = "中",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BlackboardEntry:
        """
        发布一条黑板条目（状态为 draft）。
        
        Returns:
            创建的条目
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = BlackboardEntry(
            entry_id=f"bb-{uuid.uuid4().hex[:10]}",
            title=title.strip(),
            content=content.strip(),
            status="draft",
            author=author,
            tags=tags or [],
            priority=priority,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        self._entries[entry.entry_id] = entry
        self._enforce_limit()
        self._save()
        return entry

    # ── 读取 ────────────────────────────────────────────

    def read(self, entry_id: str) -> Optional[BlackboardEntry]:
        """按 ID 读取条目。"""
        return self._entries.get(entry_id)

    def read_all(
        self,
        status: Optional[str] = None,
        author: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[BlackboardEntry]:
        """
        按条件读取条目列表。

        Args:
            status: 筛选状态 (draft / revised / final / revoked)
            author: 筛选作者
            priority: 筛选优先级
            limit: 最大返回数
        """
        results = list(self._entries.values())

        # 默认不返回已撤销条目
        if status:
            results = [e for e in results if e.status == status]
        else:
            results = [e for e in results if e.status != "revoked"]

        if author:
            results = [e for e in results if e.author == author]
        if priority:
            results = [e for e in results if e.priority == priority]

        # 按时间倒序
        results.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
        return results[:limit]

    # ── 修订 ────────────────────────────────────────────

    def revise(
        self,
        entry_id: str,
        new_content: str,
        author: str = "agent1",
        tags: Optional[List[str]] = None,
        priority: Optional[str] = None,
    ) -> Optional[BlackboardEntry]:
        """
        修订一条条目。

        - 已定稿 (final) 的条目不可修订。
        - 修订后状态变为 revised，revision_count +1。
        - 记录修订历史。

        Returns:
            修订后的条目，或 None（条目不存在或已锁定）
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return None
        if entry.status == "final":
            return None  # 已定稿，不可修订
        if entry.status == "revoked":
            return None

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 记录修订历史
        entry.revision_history.append({
            "timestamp": now,
            "author": author,
            "previous_content": entry.content[:200],
        })

        entry.content = new_content.strip()
        entry.status = "revised"
        entry.revision_count += 1
        entry.updated_at = now
        if tags is not None:
            entry.tags = tags
        if priority is not None:
            entry.priority = priority

        self._save()
        return entry

    # ── 定稿 ────────────────────────────────────────────

    def finalize(self, entry_id: str) -> Optional[BlackboardEntry]:
        """
        锁定条目为只读（status → final）。

        Returns:
            定稿后的条目，或 None
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return None
        if entry.status == "revoked":
            return None

        entry.status = "final"
        entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return entry

    # ── 撤销 ────────────────────────────────────────────

    def revoke(self, entry_id: str) -> bool:
        """
        撤销（软删除）一条条目。

        - 仅 draft 或 revised 可撤销。
        - final 条目不可撤销（需先 unfinalize）。

        Returns:
            是否成功撤销
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        if entry.status == "final":
            return False

        entry.status = "revoked"
        entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return True

    def unfinalize(self, entry_id: str) -> Optional[BlackboardEntry]:
        """解除定稿状态（final → revised），使其可重新修订。"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != "final":
            return None
        entry.status = "revised"
        entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return entry

    # ── 搜索 ────────────────────────────────────────────

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        limit: int = 20,
    ) -> List[BlackboardEntry]:
        """
        按关键词 + 标签搜索条目。

        搜索范围：title + content + tags + author。
        """
        q = query.lower()
        results = []

        for entry in self._entries.values():
            if entry.status == "revoked":
                continue
            # 标签筛选
            if tags and not any(t in entry.tags for t in tags):
                continue
            if author and entry.author != author:
                continue
            # 全文匹配
            if q:
                searchable = (
                    entry.title.lower() + " " +
                    entry.content.lower() + " " +
                    " ".join(entry.tags).lower() + " " +
                    entry.author.lower()
                )
                if q not in searchable:
                    continue
            results.append(entry)

        results.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
        return results[:limit]

    # ── 摘要 ────────────────────────────────────────────

    def summary(self) -> str:
        """黑板状态概览。"""
        total = len(self._entries)
        status_counts = {"draft": 0, "revised": 0, "final": 0, "revoked": 0}
        author_counts: Dict[str, int] = {}
        tag_counts: Dict[str, int] = {}

        for entry in self._entries.values():
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            author_counts[entry.author] = author_counts.get(entry.author, 0) + 1
            for tag in entry.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        active = total - status_counts.get("revoked", 0)

        lines = [
            f"📋 共享黑板状态",
            f"{'─'*40}",
            f"总条目:   {total}（活跃: {active}）",
            f"  📝 draft:   {status_counts.get('draft', 0)}",
            f"  ✏️ revised: {status_counts.get('revised', 0)}",
            f"  🔒 final:   {status_counts.get('final', 0)}",
            f"  🗑️ revoked: {status_counts.get('revoked', 0)}",
        ]

        if author_counts:
            lines.append(f"\n作者分布:")
            for author, count in sorted(author_counts.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  • {author}: {count} 条")

        if tag_counts:
            top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:5]
            lines.append(f"\n热门标签:")
            for tag, count in top_tags:
                lines.append(f"  • #{tag}: {count} 条")

        return "\n".join(lines)

    # ── 清理 ────────────────────────────────────────────

    def cleanup(self, max_age_days: int = 30) -> int:
        """
        清理过期条目（revoked 状态超过 N 天的物理删除）。

        Returns:
            清理的条目数
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=max_age_days)
        to_delete = []

        for entry_id, entry in self._entries.items():
            if entry.status != "revoked":
                continue
            try:
                updated = datetime.strptime(entry.updated_at, "%Y-%m-%d %H:%M:%S")
                if updated < cutoff:
                    to_delete.append(entry_id)
            except (ValueError, TypeError):
                pass

        for entry_id in to_delete:
            del self._entries[entry_id]

        if to_delete:
            self._save()

        return len(to_delete)

    # ── 持久化 ──────────────────────────────────────────

    def _save(self):
        data = {eid: entry.to_dict() for eid, entry in self._entries.items()}
        BLACKBOARD_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        if not BLACKBOARD_FILE.is_file():
            return
        try:
            data = json.loads(BLACKBOARD_FILE.read_text(encoding="utf-8"))
            self._entries = {eid: BlackboardEntry.from_dict(d) for eid, d in data.items()}
        except (json.JSONDecodeError, KeyError, TypeError):
            self._entries = {}

    def _enforce_limit(self):
        if len(self._entries) > MAX_ENTRIES:
            # 优先删除 revoked，然后删除最旧的
            revoked = [(eid, e) for eid, e in self._entries.items() if e.status == "revoked"]
            for eid, _ in revoked[:len(self._entries) - MAX_ENTRIES]:
                del self._entries[eid]

            while len(self._entries) > MAX_ENTRIES:
                oldest = min(self._entries.values(), key=lambda x: x.created_at)
                del self._entries[oldest.entry_id]


# ── 全局单例 ───────────────────────────────────────────────

blackboard_manager = BlackboardManager()


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "blackboard",
        "description": (
            "共享黑板 — 多 Agent 协作工作内存。发布/读取/修订/定稿/搜索条目，"
            "实现跨 Agent 的状态同步与知识传递。"
            "Debugger 诊断结果、Researcher 搜索结果、各 Agent 进度均可发布到黑板共享。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["post", "read", "revise", "finalize", "revoke", "search", "summary", "cleanup"],
                    "description": (
                        "操作类型：post — 发布条目；read — 读取条目（按 ID 或条件列表）；"
                        "revise — 修订条目；finalize — 定稿锁定；revoke — 撤销条目；"
                        "search — 搜索条目；summary — 黑板状态概览；cleanup — 清理过期条目"
                    ),
                    "default": "summary",
                },
                "entry_id": {
                    "type": "string",
                    "description": "条目 ID（用于 read/revise/finalize/revoke）",
                    "default": "",
                },
                "title": {
                    "type": "string",
                    "description": "条目标题（post 时需要）",
                    "default": "",
                },
                "content": {
                    "type": "string",
                    "description": "条目内容（post 或 revise 时使用）",
                    "default": "",
                },
                "author": {
                    "type": "string",
                    "description": "发布者/修订者标识，如 'debugger'、'evolver'、'researcher'",
                    "default": "agent1",
                },
                "tags": {
                    "type": "string",
                    "description": "标签 JSON 数组，如 '[\"health\",\"diagnosis\"]'",
                    "default": "[]",
                },
                "priority": {
                    "type": "string",
                    "enum": ["高", "中", "低"],
                    "description": "优先级",
                    "default": "中",
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "revised", "final", "revoked"],
                    "description": "状态筛选（用于 read_all）",
                    "default": "",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（用于 search）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大返回数",
                    "default": 20,
                },
                "max_age_days": {
                    "type": "integer",
                    "description": "清理超过此天数的已撤销条目",
                    "default": 30,
                },
                "metadata": {
                    "type": "string",
                    "description": "额外元数据 JSON",
                    "default": "{}",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


# ── 工具入口函数 ──────────────────────────────────────────


def execute_blackboard_tool(arguments: Dict[str, Any]) -> str:
    """共享黑板工具入口。"""
    action = arguments.get("action", "summary")
    bb = blackboard_manager

    try:
        # ── post ──
        if action == "post":
            title = arguments.get("title", "")
            content = arguments.get("content", "")
            if not title.strip():
                return "❌ 标题不能为空"
            if not content.strip():
                return "❌ 内容不能为空"

            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags)
            metadata = arguments.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            entry = bb.post(
                title=title,
                content=content,
                author=arguments.get("author", "agent1"),
                tags=tags,
                priority=arguments.get("priority", "中"),
                metadata=metadata,
            )
            return (
                f"📝 黑板条目已发布\n"
                f"ID:    {entry.entry_id}\n"
                f"标题:  {entry.title}\n"
                f"作者:  {entry.author}\n"
                f"状态:  {entry.status}\n"
                f"标签:  {', '.join(entry.tags) if entry.tags else '无'}"
            )

        # ── read ──
        elif action == "read":
            entry_id = arguments.get("entry_id", "")
            if entry_id:
                entry = bb.read(entry_id)
                if not entry:
                    return f"❌ 未找到条目: {entry_id}"
                return _format_entry(entry)
            else:
                # 列表模式
                entries = bb.read_all(
                    status=arguments.get("status") or None,
                    author=arguments.get("author") or None,
                    priority=arguments.get("priority") or None,
                    limit=int(arguments.get("limit", 20)),
                )
                if not entries:
                    return "📭 黑板上暂无符合条件的条目。"
                lines = [f"📋 黑板条目 ({len(entries)} 条):"]
                for e in entries:
                    icon = {"draft": "📝", "revised": "✏️", "final": "🔒", "revoked": "🗑️"}.get(e.status, "•")
                    lines.append(
                        f"  {icon} [{e.entry_id}] {e.title[:50]} "
                        f"— {e.author} ({e.status})"
                    )
                return "\n".join(lines)

        # ── revise ──
        elif action == "revise":
            entry_id = arguments.get("entry_id", "")
            new_content = arguments.get("content", "")
            if not entry_id or not new_content.strip():
                return "❌ 请提供 entry_id 和 content"

            tags = arguments.get("tags")
            if isinstance(tags, str) and tags:
                tags = json.loads(tags)

            entry = bb.revise(
                entry_id=entry_id,
                new_content=new_content,
                author=arguments.get("author", "agent1"),
                tags=tags if tags else None,
                priority=arguments.get("priority") or None,
            )
            if not entry:
                return f"❌ 无法修订条目 {entry_id}（可能不存在或已定稿/已撤销）"
            return (
                f"✏️ 条目已修订\n"
                f"ID:          {entry.entry_id}\n"
                f"修订次数:    {entry.revision_count}\n"
                f"状态:        {entry.status}"
            )

        # ── finalize ──
        elif action == "finalize":
            entry_id = arguments.get("entry_id", "")
            if not entry_id:
                return "❌ 请提供 entry_id"
            entry = bb.finalize(entry_id)
            if not entry:
                return f"❌ 无法定稿条目 {entry_id}（可能不存在或已撤销）"
            return f"🔒 条目已定稿: {entry.entry_id} — {entry.title[:50]}"

        # ── revoke ──
        elif action == "revoke":
            entry_id = arguments.get("entry_id", "")
            if not entry_id:
                return "❌ 请提供 entry_id"
            if bb.revoke(entry_id):
                return f"🗑️ 条目已撤销: {entry_id}"
            return f"❌ 无法撤销条目 {entry_id}（可能不存在或已定稿）"

        # ── search ──
        elif action == "search":
            query = arguments.get("query", "")
            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags) if tags else []
            entries = bb.search(
                query=query,
                tags=tags,
                author=arguments.get("author") or None,
                limit=int(arguments.get("limit", 20)),
            )
            if not entries:
                return f"🔍 未找到匹配 '{query}' 的条目。"
            lines = [f"🔍 搜索结果 ({len(entries)} 条):"]
            for e in entries:
                snippet = e.content[:80].replace("\n", " ") + ("..." if len(e.content) > 80 else "")
                lines.append(f"  • [{e.entry_id}] {e.title} — {snippet}")
            return "\n".join(lines)

        # ── summary ──
        elif action == "summary":
            return bb.summary()

        # ── cleanup ──
        elif action == "cleanup":
            max_days = int(arguments.get("max_age_days", 30))
            count = bb.cleanup(max_days)
            return f"🧹 已清理 {count} 条过期条目。"

        else:
            return f"未知操作: {action}。可用: post, read, revise, finalize, revoke, search, summary, cleanup"

    except json.JSONDecodeError as exc:
        return f"JSON 解析错误: {exc}"
    except Exception as exc:
        return f"黑板工具错误: {exc}"


def _format_entry(entry: BlackboardEntry) -> str:
    """格式化单条条目。"""
    icon = {"draft": "📝", "revised": "✏️", "final": "🔒", "revoked": "🗑️"}.get(entry.status, "•")
    lines = [
        f"{icon} 黑板条目: {entry.entry_id}",
        f"{'─'*40}",
        f"标题:   {entry.title}",
        f"作者:   {entry.author}",
        f"状态:   {entry.status}",
        f"优先级: {entry.priority}",
        f"标签:   {', '.join(entry.tags) if entry.tags else '无'}",
        f"创建:   {entry.created_at}",
        f"更新:   {entry.updated_at}",
        f"修订次数: {entry.revision_count}",
        f"",
        f"内容:",
        f"{entry.content}",
    ]
    if entry.revision_history:
        lines.append(f"\n修订历史:")
        for rev in entry.revision_history[-3:]:
            lines.append(f"  • {rev['timestamp']} by {rev['author']}")
    if entry.metadata:
        lines.append(f"\n元数据: {json.dumps(entry.metadata, ensure_ascii=False)}")
    return "\n".join(lines)


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    bb = BlackboardManager()
    e = bb.post("测试条目", "共享黑板测试内容", author="evolver", tags=["test"])
    print(f"Posted: {e.entry_id}")
    print(bb.summary())
    results = bb.search("测试")
    print(f"Search results: {len(results)}")
    bb.revoke(e.entry_id)
    print("Revoked. Clean.")
