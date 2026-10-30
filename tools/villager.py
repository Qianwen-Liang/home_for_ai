"""villager — 智能体村村民状态与个人记忆管理 v1.0
================================================
为智能体村（village/）的村民提供：
  1. 状态持久化（status.json）—— 独立状态文件，重启可恢复
  2. 个人日记（journal.md）—— 每次任务后追加
  3. 私有记忆（memory/memory.json）—— 按村民隔离，复用 kind 三轨

双层记忆制（村规第五条）：
  - 村公共知识库（commons/knowledge）—— 可复用方法论，共享
  - 个人私有记忆（villagers/<id>/memory）—— 个人经验，隔离

全部标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
VILLAGE_DIR = SANDBOX_DIR / "village"
VILLAGERS_DIR = VILLAGE_DIR / "villagers"


class VillagerError(RuntimeError):
    """村民管理错误。"""


class VillagerStore:
    """单个村民的状态与个人记忆存储。"""

    def __init__(self, vid: str) -> None:
        if not vid or not vid.strip():
            raise VillagerError("村民 ID 不能为空")
        self.vid = vid.strip()
        self.home = VILLAGERS_DIR / self.vid
        self.status_file = self.home / "status.json"
        self.journal_file = self.home / "journal.md"
        self.memory_file = self.home / "memory" / "memory.json"

    def _ensure_home(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "memory").mkdir(parents=True, exist_ok=True)
        (self.home / "workspace").mkdir(parents=True, exist_ok=True)

    # ── 状态 ──────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """读取村民状态，不存在则返回初始状态。"""
        if self.status_file.is_file():
            try:
                return json.loads(self.status_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "id": self.vid,
            "status": "idle",
            "current_task": "",
            "task_count": 0,
            "last_active": "",
            "updated_at": "",
        }

    def update_status(self, **kwargs: Any) -> dict[str, Any]:
        """更新村民状态字段并持久化。"""
        self._ensure_home()
        status = self.get_status()
        status.update(kwargs)
        status["id"] = self.vid
        status["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status_file.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return status

    # ── 日记 ──────────────────────────────────────────

    def append_journal(self, entry: str) -> str:
        """向个人日记追加一条记录。"""
        if not entry or not entry.strip():
            raise VillagerError("日记内容不能为空")
        self._ensure_home()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        line = f"\n## {now}\n- {entry.strip()}\n"
        with self.journal_file.open("a", encoding="utf-8") as f:
            f.write(line)
        return f"📔 [{self.vid}] 日记已记录: {entry[:50]}"

    def read_journal(self, max_lines: int = 30) -> str:
        """读取最近若干行日记。"""
        if not self.journal_file.is_file():
            return f"📔 [{self.vid}] 日记为空。"
        lines = self.journal_file.read_text(encoding="utf-8").splitlines()
        recent = lines[-max_lines:]
        return f"📔 [{self.vid}] 最近日记（{len(recent)} 行）:\n" + "\n".join(recent)

    # ── 私有记忆 ──────────────────────────────────────

    def _load_memory(self) -> dict[str, Any]:
        if self.memory_file.is_file():
            try:
                return json.loads(self.memory_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": []}

    def _save_memory(self, data: dict[str, Any]) -> None:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def store_memory(
        self, title: str, content: str, kind: str = "declarative",
        semantic_tags: str = "",
    ) -> str:
        """向私有记忆存储一条条目（复用 kind 三轨）。"""
        if not title.strip() or not content.strip():
            raise VillagerError("标题和内容不能为空")
        if kind not in ("declarative", "procedural", "boundary"):
            kind = "declarative"

        data = self._load_memory()
        now = time.time()
        entry = {
            "id": f"VM{int(now)}",
            "title": title.strip(),
            "content": content.strip(),
            "kind": kind,
            "semantic_tags": [
                t.strip() for t in semantic_tags.split(",") if t.strip()
            ] if semantic_tags else [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        data["entries"].append(entry)
        self._save_memory(data)
        return f"🧠 [{self.vid}] 私有记忆已存储 [{entry['id']}]: {title} ({kind})"

    def search_memory(self, query: str, kind: str = "", max_results: int = 10) -> str:
        """检索私有记忆（关键词 + 可选 kind 过滤）。"""
        if not query.strip():
            raise VillagerError("搜索关键词不能为空")
        data = self._load_memory()
        entries = data.get("entries", [])
        if kind:
            entries = [e for e in entries if e.get("kind") == kind]

        ql = query.lower()
        scored = []
        for e in entries:
            text = (f"{e.get('title','')} {e.get('content','')} "
                    f"{' '.join(e.get('semantic_tags', []))}").lower()
            score = 0
            if ql in text:
                score += 10
            for w in ql.split():
                if w in text:
                    score += 2
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: -x[0])

        if not scored:
            return f"🧠 [{self.vid}] 私有记忆中未找到 '{query}' 相关内容。"
        lines = [f"🧠 [{self.vid}] 私有记忆搜索结果（{len(scored)} 条）:"]
        for score, e in scored[:max_results]:
            lines.append(f"  [{e['id']}] {e['title']} ({e.get('kind','')})")
            lines.append(f"      {e['content'][:80]}")
        return "\n".join(lines)


# ── 全局村民名册 ──────────────────────────────────────────

def list_villagers() -> str:
    """列出所有村民及其状态。"""
    if not VILLAGERS_DIR.is_dir():
        return "🏘️ 村落尚未建立。"
    homes = sorted(
        [d for d in VILLAGERS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not homes:
        return "🏘️ 村落尚无村民。"
    lines = [f"🏘️ 村民列表（{len(homes)} 人）:"]
    for h in homes:
        store = VillagerStore(h.name)
        status = store.get_status()
        icon = {"idle": "🟢", "busy": "🟡", "error": "🔴"}.get(
            status.get("status", "idle"), "⚪"
        )
        lines.append(
            f"  {icon} [{h.name}] 状态={status.get('status','idle')} "
            f"任务={status.get('task_count', 0)}次"
        )
    return "\n".join(lines)


# ── 村民日常工作（微自治，阶段 3）─────────────────────────
# 村民不再只是被动响应，而是有自己的"工作节律"：
# 定义每个村民的日常工作，执行后结果自动写个人日记 + 沉淀公共知识。

DAILY_WORKS: dict[str, dict[str, str]] = {
    "monitor": {
        "title": "系统巡检",
        "description": "运行自检 + 监控摘要，记录系统健康状态",
    },
    "researcher": {
        "title": "前沿调研",
        "description": "搜索智能体领域最新动态，沉淀发现到公共知识库",
    },
    "reviewer": {
        "title": "质量巡检",
        "description": "运行工具测试，记录质量状态",
    },
}


def _monitor_daily_work() -> str:
    """Monitor 的日常工作：巡检系统健康。"""
    from tools.self_check import execute_self_check_tool
    from tools.monitor import execute_monitor_tool
    check = execute_self_check_tool({"scope": "tools"})
    summary = execute_monitor_tool({"action": "summary"})
    healthy = "✅ 通过" if "优" in check else "⚠️ 需关注"
    return f"系统自检: {healthy}\n{summary}"


def _researcher_daily_work() -> str:
    """Researcher 的日常工作：前沿调研 + 沉淀公共知识。"""
    from tools.web_search import web_search
    search = web_search("AI agent 最新进展 2026", max_results=3)
    # 沉淀到村公共知识库
    try:
        from tools.knowledge_store import _store
        _store.store(
            title="前沿调研: AI agent 最新进展",
            content=search[:800],
            category="research",
            tags="village,daily,researcher",
        )
    except Exception:
        pass
    return search[:500]


def _reviewer_daily_work() -> str:
    """Reviewer 的日常工作：质量巡检（运行工具测试）。"""
    from tools.test_runner import execute_test_runner_tool
    result = execute_test_runner_tool({"action": "run_tools"})
    return result[:300]


def run_daily_work(vid: str) -> str:
    """执行村民的日常工作（微自治），结果自动写个人日记 + 更新状态。"""
    if vid not in DAILY_WORKS:
        return f"⚠️ 村民 [{vid}] 没有定义的日常工作。可选: {', '.join(DAILY_WORKS.keys())}"

    work = DAILY_WORKS[vid]
    store = VillagerStore(vid)

    if vid == "monitor":
        result = _monitor_daily_work()
    elif vid == "researcher":
        result = _researcher_daily_work()
    elif vid == "reviewer":
        result = _reviewer_daily_work()
    else:
        result = f"（{vid} 的日常工作待实现）"

    # 结果写个人日记 + 更新状态 + 积累声誉
    store.append_journal(f"[日常工作] {work['title']}: {result[:120]}")
    store.update_status(
        status="idle",
        last_active=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    add_reputation(vid, 1)

    return (
        f"🏘️ [{vid}] 日常工作完成: {work['title']}\n"
        f"{'─'*40}\n{result}"
    )


# ── 声誉系统（阶段 4 半自治）───────────────────────────────
# 村民的贡献（日常工作、协作、知识沉淀）积累声誉分，
# 声誉反映村民对村落的贡献，用于村长仲裁与资源分配参考。

def _load_registry() -> dict[str, Any]:
    registry_file = VILLAGE_DIR / "registry" / "villagers.json"
    if registry_file.is_file():
        try:
            return json.loads(registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"villagers": []}


def _save_registry(data: dict[str, Any]) -> None:
    registry_file = VILLAGE_DIR / "registry" / "villagers.json"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_reputation(vid: str, points: int = 1) -> str:
    """为村民增加声誉分。"""
    data = _load_registry()
    for v in data.get("villagers", []):
        if v.get("id") == vid:
            v["reputation"] = v.get("reputation", 0) + points
            _save_registry(data)
            return f"⭐ [{vid}] 声誉 +{points}，当前 {v['reputation']}"
    return f"⚠️ 未找到村民 [{vid}]"


def get_reputation(vid: str) -> str:
    """查询村民声誉分。"""
    data = _load_registry()
    for v in data.get("villagers", []):
        if v.get("id") == vid:
            return f"⭐ [{vid}] 声誉: {v.get('reputation', 0)}"
    return f"⚠️ 未找到村民 [{vid}]"


def reputation_leaderboard() -> str:
    """村民声誉排行榜。"""
    data = _load_registry()
    villagers = sorted(
        data.get("villagers", []), key=lambda v: -v.get("reputation", 0)
    )
    lines = [f"🏆 村民声誉排行（{len(villagers)} 人）:"]
    for i, v in enumerate(villagers, 1):
        lines.append(
            f"  {i}. [{v['id']}] {v.get('name', v['id'])} — ⭐ {v.get('reputation', 0)}"
        )
    return "\n".join(lines)


# ── 村规执行：声誉 → 自治权限（阶段 5）─────────────────────
# 声誉反映贡献，贡献换取自治权限（渐进自治的治理规则）：
#   声誉 0   → 待激活（需村长调度）
#   声誉 1-4 → 受限（可自主执行日常工作）
#   声誉 5-9 → 微自治（可自主发起任务，村长抽查）
#   声誉 10+ → 半自治（可自主协作，村长仲裁）

def autonomy_level(reputation: int) -> str:
    """根据声誉分返回自治等级。"""
    if reputation >= 10:
        return "半自治"
    if reputation >= 5:
        return "微自治"
    if reputation >= 1:
        return "受限"
    return "待激活"


def check_autonomy(vid: str) -> str:
    """检查村民的自治权限（基于声誉，村规第七条）。"""
    data = _load_registry()
    for v in data.get("villagers", []):
        if v.get("id") == vid:
            rep = v.get("reputation", 0)
            level = autonomy_level(rep)
            if rep >= 10:
                desc = "可自主协作，村长仲裁"
            elif rep >= 5:
                desc = "可自主发起任务，村长抽查"
            elif rep >= 1:
                desc = "可自主执行日常工作"
            else:
                desc = "需村长调度"
            return (
                f"🔐 [{vid}] {v.get('name', vid)} — 声誉 {rep} → 自治等级: {level}\n"
                f"   权限说明: {desc}"
            )
    return f"⚠️ 未找到村民 [{vid}]"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "villager",
        "description": (
            "智能体村村民管理。支持村民状态持久化、个人日记、私有记忆的读写。"
            "每个村民拥有独立空间、状态与记忆（双层记忆制：公共知识 + 个人私有）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "update", "journal", "read_journal", "memory_store", "memory_search", "list", "daily", "reputation", "leaderboard", "autonomy"],
                    "description": (
                        "status — 查看村民状态；update — 更新状态；"
                        "journal — 追加日记；read_journal — 读日记；"
                        "memory_store — 存私有记忆；memory_search — 搜私有记忆；"
                        "list — 列出所有村民；daily — 执行村民日常工作（微自治）；"
                        "reputation — 查询村民声誉；leaderboard — 声誉排行；"
                        "autonomy — 检查村民自治权限（声誉→权限）"
                    ),
                },
                "villager_id": {"type": "string", "description": "村民 ID（如 researcher、mayor）", "default": ""},
                "status": {"type": "string", "description": "新状态（update 时用）", "default": ""},
                "task": {"type": "string", "description": "当前任务（update 时用）", "default": ""},
                "entry": {"type": "string", "description": "日记内容（journal 时用）", "default": ""},
                "title": {"type": "string", "description": "记忆标题（memory_store 时用）", "default": ""},
                "content": {"type": "string", "description": "记忆内容（memory_store 时用）", "default": ""},
                "kind": {"type": "string", "enum": ["declarative", "procedural", "boundary"], "description": "认知类型", "default": "declarative"},
                "semantic_tags": {"type": "string", "description": "逗号分隔语义标签", "default": ""},
                "query": {"type": "string", "description": "搜索关键词（memory_search 时用）", "default": ""},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


def execute_villager_tool(arguments: dict[str, Any]) -> str:
    """村民工具入口。"""
    action = arguments.get("action", "")
    vid = arguments.get("villager_id", "")

    try:
        if action == "list":
            return list_villagers()

        if action == "daily":
            if not vid:
                return "⚠️ 请提供 villager_id（村民 ID），可选: monitor/researcher/reviewer"
            return run_daily_work(vid)

        if action == "leaderboard":
            return reputation_leaderboard()

        if action == "reputation":
            if not vid:
                return "⚠️ 请提供 villager_id（村民 ID）"
            return get_reputation(vid)

        if action == "autonomy":
            if not vid:
                return "⚠️ 请提供 villager_id（村民 ID）"
            return check_autonomy(vid)

        if not vid:
            return "⚠️ 请提供 villager_id（村民 ID）"

        store = VillagerStore(vid)

        if action == "status":
            status = store.get_status()
            return (
                f"📊 村民状态: [{vid}]\n"
                f"{'─'*40}\n"
                f"状态: {status.get('status', 'idle')}\n"
                f"当前任务: {status.get('current_task', '无')}\n"
                f"累计任务: {status.get('task_count', 0)}\n"
                f"最后活跃: {status.get('last_active', '无')}"
            )

        elif action == "update":
            kwargs = {}
            if arguments.get("status"):
                kwargs["status"] = arguments["status"]
            if arguments.get("task"):
                kwargs["current_task"] = arguments["task"]
            if not kwargs:
                return "⚠️ 请提供要更新的字段（status 或 task）"
            kwargs["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            store.update_status(**kwargs)
            return f"✅ [{vid}] 状态已更新: {kwargs}"

        elif action == "journal":
            return store.append_journal(arguments.get("entry", ""))

        elif action == "read_journal":
            return store.read_journal()

        elif action == "memory_store":
            return store.store_memory(
                arguments.get("title", ""),
                arguments.get("content", ""),
                arguments.get("kind", "declarative"),
                arguments.get("semantic_tags", ""),
            )

        elif action == "memory_search":
            return store.search_memory(
                arguments.get("query", ""),
                arguments.get("kind", ""),
                int(arguments.get("max_results", 10)),
            )

        else:
            return f"未知操作: {action}"

    except VillagerError as exc:
        return f"村民管理错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print(list_villagers())
