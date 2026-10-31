"""task_tracker — 任务追踪与进度管理工具（树状分级版 v3.0）

以"树状分级结构"管理任务：
  - 大任务可无限层级包含子任务（parent_id / subtasks 构成树）
  - 每级任务有独立的"重视程度"（weight；层级越深默认权重越低）
  - 进度按重视程度加权递归计算（父任务进度 = 子任务加权平均）
  - 树形视图展示层级关系

v3.0 相对 v2.0 新增：
  - level（层级深度）与 weight（重视程度权重）字段
  - 加权进度计算（替代简单平均）
  - 树形展示（list / report / tree）
  - set_weight / set_priority 操作
  - create 支持直接指定 parent_id / weight / importance
  - 子任务环检测（防止 A→B→A）
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = SANDBOX_DIR / "memory" / "tasks.json"

# 容量护栏：任务总数上限，防止压力测试/失控创建导致 tasks.json 膨胀。
MAX_TASKS = 500


class TaskTrackerError(RuntimeError):
    """任务追踪器操作错误。"""


def _related_boundaries(title: str, description: str = "", limit: int = 2) -> list[str]:
    """检索与任务标题相关的失效边界卡片。

    设计演进（两次否决）：
      首版用 2-3 字片段子串匹配 → 假阳性严重：'xyzzynothinghere' 这类无意义
      标题也能撞上英文片段（the/there），返回完全无关的卡片。
      提高门槛到"2 个片段命中"仍不够，且反向漏报（'门禁误报观察者效应'
      明明是已记录的边界，却匹配不到）。

    结论：**降级为复用 knowledge_store.search 的关键词 + kind 过滤**。
    代价是每次建任务约 0.1s（批量建 100 个任务约 10s，可接受），
    换来的是不误导——错误的提示比没有提示更糟。
    """
    import re

    query = f"{title} {description}".strip()
    if not query:
        return []
    try:
        from tools.knowledge_store import _store
        out = _store.search(query, limit, mode="keyword", kind="boundary")
    except Exception:  # noqa: BLE001  知识库异常不应阻塞建任务
        return []
    if not out or "未找到" in out:
        return []

    # 解析形如：  ⭐⭐⭐ [K1793367001] 标题 (category)
    # 解析并**按分数过滤**：knowledge_store.search 没有相关性阈值，
    # 即便查询是无意义词（如 'xyzzynothinghere'）也会返回"最像的"几条。
    # 实测分数能清楚分离：真正相关 32+，无关 8.5。
    # 取 15.0 作阈值（实测中点偏保守，宁缺勿滥）。
    MIN_SCORE = 15.0
    lines = out.splitlines()
    results: list[str] = []
    for i, line in enumerate(lines):
        m = re.match(r"\s*⭐*\s*\[(K[0-9A-Za-z_]+)\]\s*(.+)", line)
        if not m:
            continue
        name = m.group(2)
        score = 0.0
        for follow in lines[i + 1:i + 3]:
            sm = re.search(r"关键词:\s*([\d.]+)", follow)
            if sm:
                score = float(sm.group(1))
                break
        if score < MIN_SCORE:
            continue
        clean = name.split(" (")[0].strip()[:60]
        if clean and clean not in results:
            results.append(clean)
        if len(results) >= limit:
            break
    return results


# ── 状态与优先级 ──────────────────────────────────────────
TASK_STATUS_TODO = "待办"
TASK_STATUS_IN_PROGRESS = "进行中"
TASK_STATUS_DONE = "已完成"
TASK_STATUS_BLOCKED = "被阻塞"

TASK_PRIORITY_HIGH = "高"
TASK_PRIORITY_MEDIUM = "中"
TASK_PRIORITY_LOW = "低"


class TaskStatus(str, Enum):
    TODO = TASK_STATUS_TODO
    IN_PROGRESS = TASK_STATUS_IN_PROGRESS
    DONE = TASK_STATUS_DONE
    BLOCKED = TASK_STATUS_BLOCKED


class TaskPriority(str, Enum):
    HIGH = TASK_PRIORITY_HIGH
    MEDIUM = TASK_PRIORITY_MEDIUM
    LOW = TASK_PRIORITY_LOW


# ── 重视程度（权重）体系 ─────────────────────────────────
# 每级任务的默认权重：层级越深（越细分）重视程度越低。
LEVEL_DEFAULT_WEIGHT = {
    0: 5.0,  # 根任务 / 大任务
    1: 3.0,  # 一级子任务
    2: 2.0,  # 二级子任务
    3: 1.0,  # 三级及以下
}
DEFAULT_WEIGHT_DEEP = 1.0  # 层级 >= 4 时的默认权重

# 语义级重视程度 → 数值权重（供快速指定）
IMPORTANCE_WEIGHT = {
    "关键": 5.0,
    "重要": 3.0,
    "普通": 2.0,
    "次要": 1.0,
    "低": 0.5,
}


def level_default_weight(level: int) -> float:
    """返回某层级的默认重视程度权重。"""
    return LEVEL_DEFAULT_WEIGHT.get(level, DEFAULT_WEIGHT_DEEP)


def _fmt_weight(w: float) -> str:
    """格式化权重显示（去掉多余的 .0）。"""
    return f"{w:g}"


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "task_tracker",
        "description": (
            "任务追踪与进度管理工具（树状分级 v3.0）。"
            "支持大任务包含多层子任务，每级任务有独立的重视程度（权重），"
            "进度按权重加权计算，树形展示层级关系。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create", "complete", "start", "block",
                        "list", "report", "tree", "delete",
                        "add_dependency", "add_subtask",
                        "set_weight", "set_priority",
                        "propose", "stop_loss_quality",
                    ],
                    "description": (
                        "操作类型：create 创建任务(可指定父任务/重视程度)；"
                        "complete 完成；start 开始；block 阻塞；"
                        "list 树形列表；report 树形进度报告；tree 树形视图；"
                        "delete 删除(级联删除整棵子树)；"
                        "add_dependency 添加依赖；add_subtask 设为某任务子任务；"
                        "set_weight 设置重视程度；set_priority 设置优先级；"
                        "propose 立项(先过 decision_engine 立项门禁 gate 再创建)；"
                        "stop_loss_quality 止损质量度量。"
                    ),
                },
                "task_id": {"type": "string", "description": "任务 ID", "default": ""},
                "title": {"type": "string", "description": "任务标题（create 必需）", "default": ""},
                "description": {"type": "string", "description": "任务描述", "default": ""},
                "phase": {"type": "string", "description": "所属阶段，如 'A'、'B'", "default": ""},
                "status": {"type": "string", "description": "按状态筛选（list 用）", "default": ""},
                "priority": {
                    "type": "string", "enum": ["高", "中", "低"],
                    "description": "优先级（create/set_priority，默认'中'）", "default": "中",
                },
                "weight": {
                    "type": "number",
                    "description": "重视程度权重(>0)，层级越深默认越低。create/set_weight 用", "default": 0,
                },
                "importance": {
                    "type": "string", "enum": ["关键", "重要", "普通", "次要", "低"],
                    "description": "重视程度级别，自动映射为权重。create/set_weight 用", "default": "",
                },
                "depends_on": {"type": "string", "description": "依赖的任务ID（add_dependency 用）", "default": ""},
                "parent_id": {"type": "string", "description": "父任务ID（create 直接作为子任务 / add_subtask 用）", "default": ""},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 图标 ─────────────────────────────────────────────────
_STATUS_ICON = {
    TASK_STATUS_DONE: "✅",
    TASK_STATUS_IN_PROGRESS: "🟡",
    TASK_STATUS_TODO: "⬜",
    TASK_STATUS_BLOCKED: "⛔",
}

_PRIORITY_ICON = {
    TASK_PRIORITY_HIGH: "🔴",
    TASK_PRIORITY_MEDIUM: "🟡",
    TASK_PRIORITY_LOW: "🟢",
}

# ── 任务追踪引擎 ──────────────────────────────────────────


class TaskTracker:
    """任务追踪管理器（v3.0 树状分级版）。"""

    def __init__(self, path: Path = TASKS_FILE) -> None:
        self._path = path
        self._tasks: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载任务并迁移旧数据。"""
        if self._path.is_file():
            try:
                raw = self._path.read_text(encoding="utf-8")
                self._tasks = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                self._tasks = {}
        else:
            self._tasks = {}
        self._migrate()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._tasks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _migrate(self) -> None:
        """补齐 v2.0 旧数据缺失字段，并重算层级与默认权重。"""
        changed = False
        for t in self._tasks.values():
            if not isinstance(t, dict):
                continue
            if "level" not in t:
                t["level"] = 0
                changed = True
            if "weight" not in t:
                t["weight"] = 0.0
                changed = True
            if "subtasks" not in t:
                t["subtasks"] = []
                changed = True
            if "dependencies" not in t:
                t["dependencies"] = []
                changed = True
            if "parent_id" not in t:
                t["parent_id"] = ""
                changed = True
        # 重算层级与默认权重（仅对 weight<=0 的任务赋予层级默认值）
        for tid in list(self._tasks.keys()):
            if not self._tasks[tid].get("parent_id"):
                self._refresh_levels(tid)
        if changed:
            self._save()

    def _next_id(self) -> str:
        existing = [int(k[1:]) for k in self._tasks.keys() if k.startswith("T")]
        next_num = max(existing) + 1 if existing else 1
        return f"T{next_num:03d}"

    # ── 层级与权重 ────────────────────────────────────────

    def _refresh_levels(self, task_id: str) -> None:
        """递归重算任务及其后代的 level，并为未设置权重的任务赋层级默认权重。"""
        task = self._tasks.get(task_id)
        if not task:
            return
        parent_id = task.get("parent_id", "")
        level = 0
        if parent_id and parent_id in self._tasks:
            level = self._tasks[parent_id].get("level", 0) + 1
        task["level"] = level
        w = task.get("weight", 0.0)
        if not w or w <= 0:
            task["weight"] = level_default_weight(level)
        for cid in list(task.get("subtasks", [])):
            if cid in self._tasks:
                self._refresh_levels(cid)

    def _task_weight(self, task: dict[str, Any]) -> float:
        w = task.get("weight", 0.0)
        if w and w > 0:
            return float(w)
        return level_default_weight(task.get("level", 0))

    # ── 进度计算（加权） ──────────────────────────────────

    @staticmethod
    def _leaf_progress(task: dict[str, Any]) -> int:
        status = task.get("status")
        if status == TASK_STATUS_DONE:
            return 100
        if status == TASK_STATUS_IN_PROGRESS:
            return 50
        return 0

    def _task_progress(self, task_id: str) -> int:
        """递归加权进度：显式完成→100%；叶子→状态映射；父任务→子任务加权平均。"""
        task = self._tasks.get(task_id)
        if not task:
            return 0
        # 显式完成的任务（无论是否有子任务）进度为 100%
        if task.get("status") == TASK_STATUS_DONE:
            return 100
        children = [c for c in task.get("subtasks", []) if c in self._tasks]
        if not children:
            return self._leaf_progress(task)
        total_w = 0.0
        weighted = 0.0
        for cid in children:
            w = self._task_weight(self._tasks[cid])
            weighted += w * self._task_progress(cid)
            total_w += w
        if total_w <= 0:
            return self._leaf_progress(task)
        return int(round(weighted / total_w))

    def _root_tasks(self) -> list[dict[str, Any]]:
        roots = [
            t for t in self._tasks.values()
            if not t.get("parent_id") or t.get("parent_id") not in self._tasks
        ]
        priority_order = {"高": 0, "中": 1, "低": 2}
        roots.sort(key=lambda t: (priority_order.get(t.get("priority", "中"), 99), t.get("id", "")))
        return roots

    def _overall_progress(self) -> int:
        roots = self._root_tasks()
        if not roots:
            return 0
        total_w = 0.0
        weighted = 0.0
        for t in roots:
            w = self._task_weight(t)
            weighted += w * self._task_progress(t["id"])
            total_w += w
        if total_w <= 0:
            return 0
        return int(round(weighted / total_w))

    # ── 环检测 ────────────────────────────────────────────

    def _would_create_cycle(self, task_id: str, new_parent_id: str) -> bool:
        if task_id == new_parent_id:
            return True
        cur = new_parent_id
        seen: set[str] = set()
        while cur and cur in self._tasks:
            if cur == task_id:
                return True
            if cur in seen:
                return True  # 数据异常：已有环
            seen.add(cur)
            cur = self._tasks[cur].get("parent_id", "")
        return False

    def _collect_subtree(self, task_id: str) -> list[str]:
        result: list[str] = []
        stack = [task_id]
        while stack:
            cur = stack.pop()
            if cur not in self._tasks or cur in result:
                continue
            result.append(cur)
            stack.extend(self._tasks[cur].get("subtasks", []))
        return result

    # ── 核心操作 ─────────────────────────────────────────

    def create(
        self,
        title: str,
        description: str = "",
        phase: str = "",
        priority: str = "中",
        parent_id: str = "",
        weight: float = 0.0,
        importance: str = "",
    ) -> str:
        """创建新任务，可指定父任务（作为子任务）与重视程度。"""
        if not title or not title.strip():
            raise TaskTrackerError("任务标题不能为空")
        if len(self._tasks) >= MAX_TASKS:
            raise TaskTrackerError(
                f"任务数已达上限 {MAX_TASKS}，请先清理已完成/污染任务再创建。"
            )
        if parent_id and parent_id not in self._tasks:
            raise TaskTrackerError(f"未找到父任务: {parent_id}")
        if priority not in ("高", "中", "低"):
            priority = "中"

        task_id = self._next_id()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        level = 0
        if parent_id:
            level = self._tasks[parent_id].get("level", 0) + 1

        if weight and weight > 0:
            final_weight = float(weight)
        elif importance and importance in IMPORTANCE_WEIGHT:
            final_weight = IMPORTANCE_WEIGHT[importance]
        else:
            final_weight = level_default_weight(level)

        self._tasks[task_id] = {
            "id": task_id,
            "title": title.strip(),
            "description": description.strip(),
            "phase": phase.strip() or "未分类",
            "priority": priority,
            "status": TASK_STATUS_TODO,
            "level": level,
            "weight": final_weight,
            "dependencies": [],
            "subtasks": [],
            "parent_id": parent_id,
            "created_at": now,
            "updated_at": now,
            "completed_at": "",
        }

        if parent_id:
            parent = self._tasks[parent_id]
            if task_id not in parent.get("subtasks", []):
                parent["subtasks"].append(task_id)
                parent["updated_at"] = now

        self._save()

        pi = _PRIORITY_ICON.get(priority, "")
        parent_str = f" | 父任务 [{parent_id}]" if parent_id else ""
        result = (
            f"📋 已创建任务 [{task_id}]: {title}\n"
            f"   层级 L{level} | 优先级 {pi} {priority} | "
            f"重视程度 ⚖️{_fmt_weight(final_weight)}{parent_str}"
        )
        # ★能力复用：建任务时主动提示相关的失效边界卡片。
        # 此前该能力只存在于 decision_engine.advise（边界卡片注入），
        # 而 advise 实际几乎不被调用 —— 知识库成了「只积不用」。
        # 挂到 create 这个高频入口，让经验在任务开始时就可见。
        warnings = _related_boundaries(title, description)
        if warnings:
            result += "\n\n⚠️ 相关失效边界（来自知识库，建议先读）:\n"
            for w in warnings:
                result += f"   • {w}\n"
        return result

    def complete(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        for dep_id in task.get("dependencies", []):
            dep = self._tasks.get(dep_id)
            if dep and dep["status"] != TASK_STATUS_DONE:
                return (
                    f"⛔ 无法完成 [{task_id}] {task['title']}\n"
                    f"   依赖任务 [{dep_id}] {dep['title']} 尚未完成"
                )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["status"] = TASK_STATUS_DONE
        task["updated_at"] = now
        task["completed_at"] = now
        self._save()
        progress = self._overall_progress()
        return (
            f"✅ 任务 [{task_id}] 已完成: {task['title']} 🎉\n"
            f"   整体加权进度: {progress}%"
        )

    def start(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        for dep_id in task.get("dependencies", []):
            dep = self._tasks.get(dep_id)
            if dep and dep["status"] != TASK_STATUS_DONE:
                return (
                    f"⚠️ 任务 [{task_id}] 的依赖 [{dep_id}] {dep['title']} 尚未完成\n"
                    f"   已标记为进行中，但建议先完成依赖任务。"
                )
        task["status"] = TASK_STATUS_IN_PROGRESS
        task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return f"🔄 任务 [{task_id}] 已开始: {task['title']}"

    def block(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        task["status"] = TASK_STATUS_BLOCKED
        task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return f"⛔ 任务 [{task_id}] 被阻塞: {task['title']}"

    def add_dependency(self, task_id: str, depends_on: str) -> str:
        if task_id not in self._tasks:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        if depends_on not in self._tasks:
            raise TaskTrackerError(f"未找到依赖任务: {depends_on}")
        if task_id == depends_on:
            raise TaskTrackerError("任务不能依赖自身")
        task = self._tasks[task_id]
        deps = task.get("dependencies", [])
        if depends_on not in deps:
            deps.append(depends_on)
            task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save()
        dep_title = self._tasks[depends_on]["title"]
        return (
            f"🔗 已添加依赖: [{task_id}] {task['title']}\n"
            f"   依赖 → [{depends_on}] {dep_title}"
        )

    def add_subtask(self, task_id: str, parent_id: str) -> str:
        """将任务设为另一个任务的子任务（支持任意层级，含环检测）。"""
        if task_id not in self._tasks:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        if parent_id not in self._tasks:
            raise TaskTrackerError(f"未找到父任务: {parent_id}")
        if task_id == parent_id:
            raise TaskTrackerError("任务不能是自己的子任务")
        if self._would_create_cycle(task_id, parent_id):
            raise TaskTrackerError("无法设置：会形成环状层级（任务不能成为自己后代的子任务）")

        task = self._tasks[task_id]
        parent = self._tasks[parent_id]

        old_parent_id = task.get("parent_id", "")
        if old_parent_id and old_parent_id in self._tasks and old_parent_id != parent_id:
            old = self._tasks[old_parent_id]
            if task_id in old.get("subtasks", []):
                old["subtasks"].remove(task_id)

        task["parent_id"] = parent_id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["updated_at"] = now

        if task_id not in parent.get("subtasks", []):
            parent["subtasks"].append(task_id)
        parent["updated_at"] = now

        self._refresh_levels(task_id)
        self._save()

        return (
            f"📂 已将 [{task_id}] {task['title']} 设为子任务\n"
            f"   父任务 → [{parent_id}] {parent['title']}（层级 L{task['level']}）"
        )

    def set_weight(self, task_id: str, weight: float = 0.0, importance: str = "") -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        if weight and weight > 0:
            final = float(weight)
        elif importance and importance in IMPORTANCE_WEIGHT:
            final = IMPORTANCE_WEIGHT[importance]
        else:
            raise TaskTrackerError(
                "请提供 weight(>0) 或 importance（关键/重要/普通/次要/低）"
            )
        task["weight"] = final
        task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return (
            f"⚖️ 已设置重视程度: [{task_id}] {task['title']}\n"
            f"   权重 → {_fmt_weight(final)}（层级 L{task.get('level', 0)}）"
        )

    def set_priority(self, task_id: str, priority: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise TaskTrackerError(f"未找到任务: {task_id}")
        if priority not in ("高", "中", "低"):
            raise TaskTrackerError("优先级必须为 高/中/低")
        task["priority"] = priority
        task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        pi = _PRIORITY_ICON.get(priority, "")
        return f"🎯 已设置优先级: [{task_id}] {task['title']} → {pi} {priority}"

    # ── 止损型元认知（v3.1）─────────────────────────────

    def propose(
        self,
        title: str,
        description: str = "",
        phase: str = "",
        priority: str = "中",
        parent_id: str = "",
        weight: float = 0.0,
        importance: str = "",
    ) -> str:
        """立项：先过 decision_engine 立项门禁 gate，命中负面先验则拦截。

        这是「止损型元认知」的硬门禁落点：立项动作天然包含负面先验核查。
        create 仍保留为「已知风险仍坚持」的显式绕过通道。
        """
        gate_report = ""
        try:
            from tools.decision_engine import _engine
            gate_report = _engine.gate(f"{title} {description}")
        except Exception as exc:
            gate_report = f"（门禁不可用，跳过核查）: {exc}"

        if "负面先验命中" in gate_report:
            return (
                "🚦 立项门禁拦截（负面先验命中，未创建任务）：\n\n"
                f"{gate_report}\n\n"
                "如确需强制立项（已知风险仍坚持），请用 action=create 并附理由。"
            )

        create_result = self.create(title, description, phase, priority, parent_id, weight, importance)
        return f"🚦 立项门禁通过，任务已创建：\n\n{create_result}"

    def stop_loss_quality(self) -> str:
        """止损质量度量：负面结果密度 + 提前止损率 + 负面先验沉淀量。

        度量「是否在死路上及时止损」，而非只度量「做了多少任务」。
        """
        neg_keywords = ("负面", "死路", "冻结", "证伪", "不可行", "REJECT", "止损", "负面结果")
        stop_keywords = ("失败判据", "止损", "预注册", "判据", "何时", "什么证据")

        negative_tasks = [
            t for t in self._tasks.values()
            if t.get("status") == TASK_STATUS_BLOCKED
            or any(k in (t.get("title", "") + t.get("description", "")) for k in neg_keywords)
        ]
        early_stop = [
            t for t in negative_tasks
            if any(k in t.get("description", "") for k in stop_keywords)
        ]

        total = len(self._tasks)
        neg_count = len(negative_tasks)
        early_count = len(early_stop)
        early_rate = (early_count / neg_count * 100) if neg_count else 0.0

        try:
            from tools.knowledge_store import _store
            boundary_count = sum(1 for e in _store._data.values() if e.get("kind") == "boundary")
        except Exception:
            boundary_count = -1

        lines = [
            "🛑 止损质量度量",
            "=" * 50,
            f"总任务数: {total}",
            f"负面结果任务数: {neg_count}（占比 {neg_count/total*100 if total else 0:.1f}%）",
            f"其中「提前预注册失败判据」的止损: {early_count}（提前止损率 {early_rate:.0f}%）",
            f"负面先验沉淀（boundary 卡片）: {boundary_count} 条",
            "",
            "解读:",
            "  · 提前止损率低 → 多数负面结果是「撞墙后才止损」，而非「立项前识破」；",
            "  · boundary 卡片数高 → 负面先验沉淀充分，可被 gate 复用；",
            "  · 建议: 立项走 propose(自动 gate)，把「撞墙后止损」前移为「立项前识破」。",
        ]
        if neg_count:
            lines.append("")
            lines.append("负面结果任务（前 10）:")
            for t in negative_tasks[:10]:
                si = _STATUS_ICON.get(t.get("status"), "❓")
                early = " [已预注册判据]" if t in early_stop else ""
                lines.append(f"  {si} [{t['id']}] {t['title'][:50]}{early}")

        return "\n".join(lines)

    # ── 树形渲染 ─────────────────────────────────────────

    def _render_tree(self, root_ids: list[str], id_filter: set[str] | None = None) -> list[str]:
        """渲染树形结构，返回行列表。id_filter 为可选的可见任务白名单。"""
        lines: list[str] = []

        def visible_children(task_id: str) -> list[str]:
            kids = [c for c in self._tasks[task_id].get("subtasks", []) if c in self._tasks]
            if id_filter is not None:
                kids = [c for c in kids if c in id_filter]
            priority_order = {"高": 0, "中": 1, "低": 2}
            kids.sort(key=lambda cid: (
                priority_order.get(self._tasks[cid].get("priority", "中"), 99), cid,
            ))
            return kids

        def render(task_id: str, prefix: str, is_last: bool) -> None:
            task = self._tasks[task_id]
            connector = "└─ " if is_last else "├─ "
            si = _STATUS_ICON.get(task["status"], "❓")
            pi = _PRIORITY_ICON.get(task.get("priority", "中"), "")
            lv = task.get("level", 0)
            w = self._task_weight(task)
            prog = self._task_progress(task_id)
            deps = task.get("dependencies", [])
            dep_str = f" [依赖:{','.join(deps)}]" if deps else ""
            lines.append(
                f"{prefix}{connector}{si}{pi} [{task_id}] {task['title']} "
                f"(L{lv} ⚖️{_fmt_weight(w)} {prog}%){dep_str}"
            )
            kids = visible_children(task_id)
            for i, cid in enumerate(kids):
                child_prefix = prefix + ("   " if is_last else "│  ")
                render(cid, child_prefix, i == len(kids) - 1)

        for i, rid in enumerate(root_ids):
            render(rid, "", i == len(root_ids) - 1)
        return lines

    # ── 查询与展示 ────────────────────────────────────────

    def _status_stats(self, tasks: list[dict[str, Any]]) -> str:
        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == TASK_STATUS_DONE)
        in_prog = sum(1 for t in tasks if t["status"] == TASK_STATUS_IN_PROGRESS)
        todo = sum(1 for t in tasks if t["status"] == TASK_STATUS_TODO)
        blocked = sum(1 for t in tasks if t["status"] == TASK_STATUS_BLOCKED)
        return (
            f"共 {total} 个 | ✅{done} 完成 | 🟡{in_prog} 进行中 | "
            f"⬜{todo} 待办 | ⛔{blocked} 阻塞"
        )

    def list_tasks(self, status: str = "") -> str:
        all_tasks = list(self._tasks.values())
        if not all_tasks:
            return "没有任务。"

        if status:
            filtered = [t for t in all_tasks if t["status"] == status]
            if not filtered:
                return f"没有状态为 '{status}' 的任务。"
            ids = {t["id"] for t in filtered}
            root_ids = [
                t["id"] for t in filtered
                if not t.get("parent_id") or t.get("parent_id") not in ids
            ]
            lines = [f"📋 任务列表（筛选 {status}）", self._status_stats(filtered), ""]
            lines += self._render_tree(root_ids, id_filter=ids)
            return "\n".join(lines)

        root_ids = [t["id"] for t in self._root_tasks()]
        lines = [
            f"📋 任务树（{self._status_stats(all_tasks)}）",
            f"   整体加权进度: {self._overall_progress()}%",
            "",
        ]
        lines += self._render_tree(root_ids)
        return "\n".join(lines)

    def tree(self) -> str:
        if not self._tasks:
            return "没有任务。"
        root_ids = [t["id"] for t in self._root_tasks()]
        lines = [f"🌳 任务树状图（{len(self._tasks)} 个任务）", ""]
        lines += self._render_tree(root_ids)
        return "\n".join(lines)

    def report(self) -> str:
        if not self._tasks:
            return "没有任务。请先创建任务。"

        total = len(self._tasks)
        done_count = sum(1 for t in self._tasks.values() if t["status"] == TASK_STATUS_DONE)
        progress = self._overall_progress()

        bar_len = 20
        filled = progress * bar_len // 100
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            "📊 Agent 1 任务进度报告（树状分级 + 加权）",
            "=" * 50,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"总进度: {done_count}/{total} 完成 ({progress}% 加权)",
            f"进度条: [{bar}] {progress}%",
            "=" * 50,
            "",
            "任务树：",
        ]
        root_ids = [t["id"] for t in self._root_tasks()]
        lines += self._render_tree(root_ids)
        return "\n".join(lines)

    def delete(self, task_id: str) -> str:
        if task_id not in self._tasks:
            raise TaskTrackerError(f"未找到任务: {task_id}")

        title = self._tasks[task_id]["title"]
        subtree = self._collect_subtree(task_id)

        parent_id = self._tasks[task_id].get("parent_id", "")
        if parent_id and parent_id in self._tasks:
            parent = self._tasks[parent_id]
            if task_id in parent.get("subtasks", []):
                parent["subtasks"].remove(task_id)

        for tid in subtree:
            del self._tasks[tid]

        # 清理所有任务对被删任务的依赖引用
        for t in self._tasks.values():
            t["dependencies"] = [d for d in t.get("dependencies", []) if d not in subtree]

        self._save()

        n = len(subtree)
        extra = f"（含 {n - 1} 个子任务）" if n > 1 else ""
        return f"🗑️ 已删除任务 [{task_id}]: {title}{extra}"


# ── 全局实例 ──────────────────────────────────────────────

_tracker = TaskTracker()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def execute_task_tracker_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")

    def _need_task_id() -> str:
        task_id = arguments.get("task_id", "")
        if not task_id:
            raise TaskTrackerError("请提供 task_id")
        return task_id

    try:
        if action == "create":
            return _tracker.create(
                title=arguments.get("title", ""),
                description=arguments.get("description", ""),
                phase=arguments.get("phase", ""),
                priority=arguments.get("priority", "中"),
                parent_id=arguments.get("parent_id", ""),
                weight=_as_float(arguments.get("weight", 0)),
                importance=arguments.get("importance", ""),
            )
        elif action == "complete":
            return _tracker.complete(_need_task_id())
        elif action == "start":
            return _tracker.start(_need_task_id())
        elif action == "block":
            return _tracker.block(_need_task_id())
        elif action == "list":
            return _tracker.list_tasks(arguments.get("status", ""))
        elif action == "report":
            return _tracker.report()
        elif action == "tree":
            return _tracker.tree()
        elif action == "delete":
            return _tracker.delete(_need_task_id())
        elif action == "add_dependency":
            task_id = arguments.get("task_id", "")
            depends_on = arguments.get("depends_on", "")
            if not task_id or not depends_on:
                raise TaskTrackerError("请提供 task_id 和 depends_on")
            return _tracker.add_dependency(task_id, depends_on)
        elif action == "add_subtask":
            task_id = arguments.get("task_id", "")
            parent_id = arguments.get("parent_id", "")
            if not task_id or not parent_id:
                raise TaskTrackerError("请提供 task_id 和 parent_id")
            return _tracker.add_subtask(task_id, parent_id)
        elif action == "set_weight":
            return _tracker.set_weight(
                _need_task_id(),
                weight=_as_float(arguments.get("weight", 0)),
                importance=arguments.get("importance", ""),
            )
        elif action == "set_priority":
            return _tracker.set_priority(
                _need_task_id(), arguments.get("priority", "中")
            )
        elif action == "propose":
            return _tracker.propose(
                title=arguments.get("title", ""),
                description=arguments.get("description", ""),
                phase=arguments.get("phase", ""),
                priority=arguments.get("priority", "中"),
                parent_id=arguments.get("parent_id", ""),
                weight=_as_float(arguments.get("weight", 0)),
                importance=arguments.get("importance", ""),
            )
        elif action == "stop_loss_quality":
            return _tracker.stop_loss_quality()
        else:
            return f"❌ 未知操作: {action}"

    except TaskTrackerError as exc:
        return f"❌ 任务追踪错误: {exc}"
