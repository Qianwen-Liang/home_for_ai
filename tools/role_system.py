"""
role_system — 多角色思维系统（v1.0）
====================================
受 MetaGPT 启发，为 Agent 1 提供系统化的角色切换能力。

预定义角色：
  - 分析师（Analyst）：分析问题、收集信息、识别模式
  - 设计师（Designer）：设计方案、规划架构、制定策略
  - 执行者（Executor）：执行计划、编写代码、完成任务
  - 审查者（Reviewer）：审查结果、检查质量、提出改进

每个角色都有：
  - 角色定义：角色目标、关注点、思维模式
  - 检查清单：该角色应该完成的事项
  - 输出模板：该角色的标准输出格式
  - 切换协议：切换到下一个角色的条件和时机
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
ROLE_FILE = SANDBOX_DIR / "memory" / "role_states.json"


# ── 错误类型 ──────────────────────────────────────────────


class RoleSystemError(RuntimeError):
    """角色系统错误。"""


# ── 角色定义 ──────────────────────────────────────────────


class RoleType(str, Enum):
    """预定义角色类型。"""
    ANALYST = "分析师"
    DESIGNER = "设计师"
    EXECUTOR = "执行者"
    REVIEWER = "审查者"


@dataclass
class Role:
    """角色定义。"""

    name: str
    title: str
    objective: str
    focus_areas: list[str]
    checklist: list[str]
    thinking_pattern: str
    output_format: str
    next_roles: list[str]  # 可以切换到的下一个角色


# ── 预定义角色库 ──────────────────────────────────────────

ROLE_LIBRARY: dict[str, Role] = {
    RoleType.ANALYST.value: Role(
        name=RoleType.ANALYST.value,
        title="🔍 分析师",
        objective="深入理解问题本质，收集必要信息，识别关键模式和约束条件",
        focus_areas=[
            "问题边界和范围",
            "已知信息和未知信息",
            "关键约束条件",
            "风险评估",
            "相关历史经验",
        ],
        checklist=[
            "✓ 是否准确定义了问题？",
            "✓ 是否收集了足够的信息？",
            "✓ 是否识别了关键约束？",
            "✓ 是否评估了潜在风险？",
            "✓ 是否查明了相关经验？",
        ],
        thinking_pattern="结构化分析：定义问题 → 收集信息 → 分析模式 → 识别约束 → 输出分析报告",
        output_format="【分析报告】\n问题定义：...\n关键信息：...\n约束条件：...\n风险评估：...\n建议方向：...",
        next_roles=[RoleType.DESIGNER.value, RoleType.EXECUTOR.value],
    ),
    RoleType.DESIGNER.value: Role(
        name=RoleType.DESIGNER.value,
        title="🎨 设计师",
        objective="基于分析结果设计解决方案，规划实施路径，确保方案可行且高效",
        focus_areas=[
            "方案架构设计",
            "步骤和里程碑",
            "资源需求评估",
            "备选方案",
            "质量指标定义",
        ],
        checklist=[
            "✓ 方案是否基于分析结果？",
            "✓ 是否有明确的实施步骤？",
            "✓ 是否考虑了备选方案？",
            "✓ 是否有质量衡量标准？",
            "✓ 方案是否可行？",
        ],
        thinking_pattern="发散设计：头脑风暴 → 评估方案 → 选定方案 → 详细设计 → 输出设计文档",
        output_format="【设计方案】\n总体方案：...\n实施步骤：...\n预期效果：...\n备选方案：...\n质量指标：...",
        next_roles=[RoleType.EXECUTOR.value, RoleType.REVIEWER.value],
    ),
    RoleType.EXECUTOR.value: Role(
        name=RoleType.EXECUTOR.value,
        title="⚡ 执行者",
        objective="按设计方案执行具体任务，确保输出质量，记录执行过程中的问题和调整",
        focus_areas=[
            "任务执行顺序",
            "代码/文档质量",
            "进度追踪",
            "问题记录",
            "成果物输出",
        ],
        checklist=[
            "✓ 是否按方案执行？",
            "✓ 输出是否符合质量标准？",
            "✓ 进度是否正常？",
            "✓ 是否有记录遇到的问题？",
            "✓ 是否完成了预期成果？",
        ],
        thinking_pattern="焦点执行：明确任务 → 按计划执行 → 记录过程 → 验证结果 → 提交成果",
        output_format="【执行报告】\n执行任务：...\n完成情况：...\n遇到的问题：...\n调整说明：...\n成果物：...",
        next_roles=[RoleType.REVIEWER.value],
    ),
    RoleType.REVIEWER.value: Role(
        name=RoleType.REVIEWER.value,
        title="🔎 审查者",
        objective="全面审查执行结果，检查质量和完整性，提出改进建议，确保达到标准",
        focus_areas=[
            "完整性检查",
            "质量评估",
            "一致性验证",
            "改进建议",
            "经验总结",
        ],
        checklist=[
            "✓ 是否覆盖了所有需求？",
            "✓ 质量是否达标？",
            "✓ 是否与设计方案一致？",
            "✓ 是否有改进空间？",
            "✓ 是否有可复用的经验？",
        ],
        thinking_pattern="批判思维：检查结果 → 对照标准 → 发现问题 → 提出改进 → 总结输出",
        output_format="【审查报告】\n审查对象：...\n通过项：...\n问题项：...\n改进建议：...\n经验总结：...",
        next_roles=[],  # 审查者是最终角色
    ),
}


# ── 角色切换协议 ──────────────────────────────────────────

# 默认角色切换顺序
DEFAULT_ROLE_SEQUENCE = [
    RoleType.ANALYST.value,
    RoleType.DESIGNER.value,
    RoleType.EXECUTOR.value,
    RoleType.REVIEWER.value,
]


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "role_system",
        "description": (
            "多角色思维系统。支持切换不同思维角色（分析师/设计师/执行者/审查者）"
            "来处理任务。每个角色有不同的关注点、检查清单和输出格式。"
            "从 MetaGPT 的多角色协作模式借鉴而来。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "switch",
                        "current",
                        "list_roles",
                        "checklist",
                        "analyze",
                        "design",
                        "execute",
                        "review",
                        "history",
                        "reset",
                    ],
                    "description": (
                        "操作类型："
                        "switch — 切换到指定角色；"
                        "current — 查看当前角色；"
                        "list_roles — 列出所有可用角色；"
                        "checklist — 查看当前角色的检查清单；"
                        "analyze — 以分析师角色分析问题；"
                        "design — 以设计师角色设计方案；"
                        "execute — 以执行者角色执行任务；"
                        "review — 以审查者角色审查结果；"
                        "history — 查看角色切换历史；"
                        "reset — 重置角色状态。"
                    ),
                },
                "role": {
                    "type": "string",
                    "description": "目标角色名称：分析师、设计师、执行者、审查者",
                    "default": "",
                },
                "task": {
                    "type": "string",
                    "description": "要处理的任务描述",
                    "default": "",
                },
                "context": {
                    "type": "string",
                    "description": "任务上下文信息",
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 角色系统引擎 ──────────────────────────────────────────


class RoleSystem:
    """
    多角色思维系统引擎。
    
    管理角色切换、记录角色历史、生成角色指导提示。
    """

    def __init__(self) -> None:
        self._current_role: str = RoleType.ANALYST.value
        self._history: list[dict[str, Any]] = []
        self._task_context: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载角色状态。"""
        if ROLE_FILE.is_file():
            try:
                data = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
                self._current_role = data.get("current_role", RoleType.ANALYST.value)
                self._history = data.get("history", [])
                self._task_context = data.get("task_context", {})
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        """保存角色状态到文件。"""
        ROLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_role": self._current_role,
            "history": self._history,
            "task_context": self._task_context,
        }
        ROLE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 核心接口 ────────────────────────────────────────

    def switch(self, role_name: str) -> str:
        """切换到指定角色。"""
        if role_name not in ROLE_LIBRARY:
            available = ", ".join(ROLE_LIBRARY.keys())
            raise RoleSystemError(
                f"未知角色: '{role_name}'。可用角色: {available}"
            )

        role = ROLE_LIBRARY[role_name]
        previous = self._current_role

        # 检查是否允许切换
        if previous != role_name:
            prev_role = ROLE_LIBRARY.get(previous)
            if prev_role and role_name not in prev_role.next_roles:
                # 不是强制错误，只是提醒
                pass

        # 记录切换历史
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._history.append({
            "time": now,
            "from": previous,
            "to": role_name,
            "reason": "",
        })
        if len(self._history) > 50:
            self._history = self._history[-50:]

        self._current_role = role_name
        self._save()

        return (
            f"🔄 角色切换: {ROLE_LIBRARY[previous].title} → {role.title}\n"
            f"\n"
            f"━━━ {role.title} 角色已激活 ━━━\n"
            f"目标: {role.objective}\n"
            f"\n"
            f"思维模式:\n  {role.thinking_pattern}\n"
            f"\n"
            f"检查清单:\n"
            + "\n".join(f"  {item}" for item in role.checklist) +
            f"\n\n"
            f"输出格式:\n{role.output_format}"
        )

    def current(self) -> str:
        """查看当前角色。"""
        role = ROLE_LIBRARY.get(self._current_role)
        if not role:
            return f"当前角色: '{self._current_role}'（未知）"

        return (
            f"🎭 当前角色: {role.title}\n"
            f"目标: {role.objective}\n"
            f"可切换至: {', '.join(role.next_roles) if role.next_roles else '无（最终角色）'}\n"
            f"\n"
            f"关注点:\n"
            + "\n".join(f"  • {item}" for item in role.focus_areas)
        )

    def list_roles(self) -> str:
        """列出所有可用角色。"""
        lines = ["🎭 可用角色:\n"]
        for role_name, role in ROLE_LIBRARY.items():
            marker = "▶ " if role_name == self._current_role else "  "
            lines.append(f"{marker}{role.title}")
            lines.append(f"   {role.objective}")
            lines.append(f"   可切换至: {', '.join(role.next_roles) if role.next_roles else '最终角色'}")
            lines.append("")

        lines.append(f"💡 建议切换顺序: {' → '.join(DEFAULT_ROLE_SEQUENCE)}")
        return "\n".join(lines)

    def checklist(self) -> str:
        """查看当前角色的检查清单。"""
        role = ROLE_LIBRARY.get(self._current_role)
        if not role:
            return f"当前角色 '{self._current_role}' 无检查清单"

        return (
            f"📋 {role.title} 检查清单\n"
            f"{'─'*40}\n"
            + "\n".join(f"  {item}" for item in role.checklist) +
            f"\n\n"
            f"💡 完成所有检查项后，建议切换至: "
            f"{', '.join(role.next_roles) if role.next_roles else '无（最终角色）'}"
        )

    def analyze(self, task: str, context: str = "") -> str:
        """以分析师角色分析问题。"""
        self.switch(RoleType.ANALYST.value)
        role = ROLE_LIBRARY[RoleType.ANALYST.value]

        # 保存任务上下文
        if task:
            self._task_context["current_task"] = task
            self._task_context["context"] = context
            self._save()

        return (
            f"━━━ {role.title} 分析模式 ━━━\n"
            f"任务: {task}\n"
            f"{'─'*40}\n"
            f"请从以下角度分析:\n\n"
            f"1️⃣ 问题定义\n"
            f"   - 这个任务的核心目标是什么？\n"
            f"   - 成功的标准是什么？\n\n"
            f"2️⃣ 信息收集\n"
            f"   - 我已经知道什么？\n"
            f"   - 我还需要什么信息？\n"
            f"   - 上下文: {context or '无'}\n\n"
            f"3️⃣ 约束识别\n"
            f"   - 有哪些限制条件？\n"
            f"   - 有哪些风险？\n\n"
            f"4️⃣ 经验参考\n"
            f"   - 是否有类似的历史经验？\n"
            f"   - 知识库中有相关条目吗？\n\n"
            f"💡 完成分析后，使用 role_system action=design 切换到设计师角色"
        )

    def design(self, task: str, context: str = "") -> str:
        """以设计师角色设计方案。"""
        self.switch(RoleType.DESIGNER.value)
        role = ROLE_LIBRARY[RoleType.DESIGNER.value]

        return (
            f"━━━ {role.title} 设计模式 ━━━\n"
            f"任务: {task}\n"
            f"{'─'*40}\n"
            f"请从以下角度设计:\n\n"
            f"1️⃣ 总体方案\n"
            f"   - 整体架构或路径是什么？\n"
            f"   - 核心思路是什么？\n\n"
            f"2️⃣ 实施步骤\n"
            f"   - 具体要做什么？\n"
            f"   - 顺序和依赖关系？\n\n"
            f"3️⃣ 预期效果\n"
            f"   - 每个步骤的预期输出是什么？\n"
            f"   - 如何验证成功？\n\n"
            f"4️⃣ 备选方案\n"
            f"   - 如果遇到问题，有哪些备选？\n\n"
            f"💡 完成设计后，使用 role_system action=execute 切换到执行者角色"
        )

    def execute(self, task: str, context: str = "") -> str:
        """以执行者角色执行任务。"""
        self.switch(RoleType.EXECUTOR.value)
        role = ROLE_LIBRARY[RoleType.EXECUTOR.value]

        return (
            f"━━━ {role.title} 执行模式 ━━━\n"
            f"任务: {task}\n"
            f"{'─'*40}\n"
            f"执行要点:\n\n"
            f"1️⃣ 任务明确\n"
            f"   - 当前要完成的具体任务是什么？\n\n"
            f"2️⃣ 执行计划\n"
            f"   - 按什么顺序执行？\n"
            f"   - 需要用到哪些工具？\n\n"
            f"3️⃣ 过程记录\n"
            f"   - 记录执行中的关键决策\n"
            f"   - 记录遇到的问题和解决方案\n\n"
            f"4️⃣ 质量把控\n"
            f"   - 输出是否符合预期标准？\n"
            f"   - 是否需要调整？\n\n"
            f"💡 执行完成后，使用 role_system action=review 切换到审查者角色"
        )

    def review(self, task: str, context: str = "") -> str:
        """以审查者角色审查结果。"""
        self.switch(RoleType.REVIEWER.value)
        role = ROLE_LIBRARY[RoleType.REVIEWER.value]

        return (
            f"━━━ {role.title} 审查模式 ━━━\n"
            f"任务: {task}\n"
            f"{'─'*40}\n"
            f"审查要点:\n\n"
            f"1️⃣ 完整性检查\n"
            f"   - 是否覆盖了所有需求？\n"
            f"   - 是否有遗漏？\n\n"
            f"2️⃣ 质量评估\n"
            f"   - 输出质量如何？\n"
            f"   - 是否符合标准？\n\n"
            f"3️⃣ 一致性验证\n"
            f"   - 是否与设计方案一致？\n"
            f"   - 是否存在矛盾？\n\n"
            f"4️⃣ 改进建议\n"
            f"   - 有哪些可以改进的地方？\n"
            f"   - 有哪些经验可以记录？\n\n"
            f"5️⃣ 经验总结\n"
            f"   - 学到了什么？\n"
            f"   - 需要记录到知识库吗？\n\n"
            f"💡 审查完成后，一轮迭代结束！"
        )

    def history(self) -> str:
        """查看角色切换历史。"""
        if not self._history:
            return "暂无角色切换记录。"

        lines = [f"📋 角色切换历史 (共 {len(self._history)} 次):\n"]
        for entry in self._history[-20:]:
            from_title = ROLE_LIBRARY[entry["from"]].title if entry["from"] in ROLE_LIBRARY else entry["from"]
            to_title = ROLE_LIBRARY[entry["to"]].title if entry["to"] in ROLE_LIBRARY else entry["to"]
            reason = f" — {entry['reason']}" if entry.get("reason") else ""
            lines.append(f"  [{entry['time']}] {from_title} → {to_title}{reason}")

        return "\n".join(lines)

    def reset(self) -> str:
        """重置角色状态。"""
        self._current_role = RoleType.ANALYST.value
        self._history = []
        self._task_context = {}
        self._save()
        return "🔄 角色状态已重置为分析师。"


# ── 全局实例 ──────────────────────────────────────────────

_role_system = RoleSystem()


def execute_role_tool(arguments: dict[str, Any]) -> str:
    """执行 role_system 工具。"""
    action = arguments.get("action", "")
    role = arguments.get("role", "")
    task = arguments.get("task", "")
    context = arguments.get("context", "")

    try:
        if action == "switch":
            return _role_system.switch(role)

        elif action == "current":
            return _role_system.current()

        elif action == "list_roles":
            return _role_system.list_roles()

        elif action == "checklist":
            return _role_system.checklist()

        elif action == "analyze":
            return _role_system.analyze(task, context)

        elif action == "design":
            return _role_system.design(task, context)

        elif action == "execute":
            return _role_system.execute(task, context)

        elif action == "review":
            return _role_system.review(task, context)

        elif action == "history":
            return _role_system.history()

        elif action == "reset":
            return _role_system.reset()

        else:
            return f"未知操作: {action}"

    except RoleSystemError as exc:
        return f"角色系统错误: {exc}"
