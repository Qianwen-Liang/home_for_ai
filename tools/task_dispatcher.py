"""
task_dispatcher — 任务分解与自动分配引擎（F4/K1）
================================================
为多智能体协同提供智能调度能力。

核心功能：
  - decompose_task  — 复杂任务自动拆解为子任务序列
  - find_best_agent — 按能力+负载+成功率自动选择最优Agent
  - dispatch        — 自动分配子任务到Agent
  - collect_results — 汇总所有子任务结果
  - pipeline_status — 查看流水线进度

设计启发：
  - AutoGen 的分布式任务调度
  - CrewAI 的层级任务管理
  - LangGraph 的有向无环图（DAG）依赖

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
DISPATCH_FILE = SANDBOX_DIR / "memory" / "dispatch.json"


# ── 错误类型 ──────────────────────────────────────────────

class DispatchError(RuntimeError):
    """Task Dispatcher 错误。"""


# ── 枚举 ──────────────────────────────────────────────────

class SubtaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PARTIAL = "partial"
    DONE = "done"
    FAILED = "failed"


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class Subtask:
    """子任务定义。"""
    task_id: str                          # 唯一ID
    description: str                      # 任务描述
    required_capability: str              # 需要的能力类型
    preferred_agent_type: str = ""        # 偏好的Agent类型
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # 依赖的子任务ID
    status: str = SubtaskStatus.PENDING.value
    assigned_agent: str = ""              # 分配给哪个Agent
    result: str = ""                      # 执行结果
    error: str = ""                       # 错误信息
    started_at: str = ""
    completed_at: str = ""
    duration: float = 0.0


@dataclass
class Pipeline:
    """任务流水线。"""
    pipeline_id: str
    name: str
    description: str
    subtasks: list[Subtask] = field(default_factory=list)
    status: str = PipelineStatus.CREATED.value
    created_at: str = ""
    completed_at: str = ""
    total_duration: float = 0.0


# ── 预定义任务分解模板 ────────────────────────────────────

# 每个模板定义：匹配关键词 → 子任务序列
DECOMPOSITION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    # ── 游戏开发流水线 ──
    "game": [
        {"description": "调研同类游戏和市场趋势", "capability": "research", "agent": "researcher"},
        {"description": "设计游戏架构、剧情分支和游戏机制", "capability": "design", "agent": "designer"},
        {"description": "撰写游戏文案、对话和场景描述", "capability": "writing", "agent": "writer"},
        {"description": "审查游戏完整性和用户体验", "capability": "review", "agent": "reviewer"},
    ],
    "游戏": [
        {"description": "调研同类游戏和市场趋势", "capability": "research", "agent": "researcher"},
        {"description": "设计游戏架构、剧情分支和游戏机制", "capability": "design", "agent": "designer"},
        {"description": "撰写游戏文案、对话和场景描述", "capability": "writing", "agent": "writer"},
        {"description": "审查游戏完整性和用户体验", "capability": "review", "agent": "reviewer"},
    ],

    # ── 内容创作流水线 ──
    "article": [
        {"description": "搜索收集相关主题的最新资讯和资料", "capability": "research", "agent": "researcher"},
        {"description": "分析素材、提炼核心观点和数据", "capability": "analysis", "agent": "analyst"},
        {"description": "撰写完整的文章内容", "capability": "writing", "agent": "writer"},
        {"description": "审查文章的事实准确性、语法和结构", "capability": "review", "agent": "reviewer"},
    ],
    "文章": [
        {"description": "搜索收集相关主题的最新资讯和资料", "capability": "research", "agent": "researcher"},
        {"description": "分析素材、提炼核心观点和数据", "capability": "analysis", "agent": "analyst"},
        {"description": "撰写完整的文章内容", "capability": "writing", "agent": "writer"},
        {"description": "审查文章的事实准确性、语法和结构", "capability": "review", "agent": "reviewer"},
    ],
    "报告": [
        {"description": "搜索收集相关数据和资料", "capability": "research", "agent": "researcher"},
        {"description": "数据分析和洞察提炼", "capability": "analysis", "agent": "analyst"},
        {"description": "撰写结构化分析报告", "capability": "writing", "agent": "writer"},
        {"description": "审查报告质量和数据准确性", "capability": "review", "agent": "reviewer"},
    ],

    # ── 系统开发流水线 ──
    "system": [
        {"description": "调研相关技术和最佳实践", "capability": "research", "agent": "researcher"},
        {"description": "设计系统架构和模块划分", "capability": "design", "agent": "designer"},
        {"description": "审查设计方案和可行性", "capability": "review", "agent": "reviewer"},
    ],
    "系统": [
        {"description": "调研相关技术和最佳实践", "capability": "research", "agent": "researcher"},
        {"description": "设计系统架构和模块划分", "capability": "design", "agent": "designer"},
        {"description": "审查设计方案和可行性", "capability": "review", "agent": "reviewer"},
    ],
    "架构": [
        {"description": "调研相关架构模式和最佳实践", "capability": "research", "agent": "researcher"},
        {"description": "设计整体架构方案", "capability": "design", "agent": "designer"},
        {"description": "分析和评估方案可行性", "capability": "analysis", "agent": "analyst"},
        {"description": "审查架构方案的完整性", "capability": "review", "agent": "reviewer"},
    ],

    # ── 数据分析流水线 ──
    "data": [
        {"description": "收集和整理数据源", "capability": "research", "agent": "researcher"},
        {"description": "数据清洗和统计分析", "capability": "analysis", "agent": "analyst"},
        {"description": "生成数据分析报告", "capability": "writing", "agent": "writer"},
        {"description": "审查数据准确性和报告质量", "capability": "review", "agent": "reviewer"},
    ],
    "数据": [
        {"description": "收集和整理数据源", "capability": "research", "agent": "researcher"},
        {"description": "数据清洗和统计分析", "capability": "analysis", "agent": "analyst"},
        {"description": "生成数据分析报告", "capability": "writing", "agent": "writer"},
        {"description": "审查数据准确性和报告质量", "capability": "review", "agent": "reviewer"},
    ],
    "分析": [
        {"description": "收集和整理相关数据", "capability": "research", "agent": "researcher"},
        {"description": "深度数据分析和洞察提炼", "capability": "analysis", "agent": "analyst"},
        {"description": "生成分析报告和建议", "capability": "writing", "agent": "writer"},
    ],

    # ── 通用流水线 ──
    "通用": [
        {"description": "调研相关背景和资料", "capability": "research", "agent": "researcher"},
        {"description": "设计执行方案", "capability": "design", "agent": "designer"},
        {"description": "执行核心任务", "capability": "writing", "agent": "writer"},
        {"description": "审查输出质量", "capability": "review", "agent": "reviewer"},
    ],
}


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "task_dispatcher",
        "description": (
            "任务分解与自动分配引擎。将复杂任务拆解为子任务序列，"
            "自动匹配最优Agent，调度并行/串行执行，汇总结果。"
            "支持预定义模板（游戏/文章/报告/系统/数据分析）和自定义分解。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "decompose",
                        "dispatch",
                        "dispatch_all",
                        "collect",
                        "status",
                        "list_pipelines",
                        "cancel",
                        "templates",
                    ],
                    "description": (
                        "操作类型："
                        "decompose — 将任务拆解为子任务序列；"
                        "dispatch — 调度单个子任务到Agent；"
                        "dispatch_all — 调度流水线中所有就绪子任务；"
                        "collect — 收集流水线结果；"
                        "status — 查看流水线进度；"
                        "list_pipelines — 列出所有流水线；"
                        "cancel — 取消流水线；"
                        "templates — 列出可用的分解模板。"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "任务描述",
                    "default": "",
                },
                "template": {
                    "type": "string",
                    "description": "分解模板名称（如 game/article/report/system/data），省略则自动匹配",
                    "default": "",
                },
                "custom_subtasks": {
                    "type": "string",
                    "description": (
                        "自定义子任务 JSON 数组。示例："
                        "[{\"description\":\"...\",\"capability\":\"research\",\"agent\":\"researcher\"}]"
                    ),
                    "default": "",
                },
                "pipeline_id": {
                    "type": "string",
                    "description": "流水线 ID",
                    "default": "",
                },
                "subtask_id": {
                    "type": "string",
                    "description": "子任务 ID",
                    "default": "",
                },
                "strategy": {
                    "type": "string",
                    "enum": ["sequential", "parallel", "dag"],
                    "description": "调度策略：sequential（串行）、parallel（并行）、dag（按依赖图）",
                    "default": "dag",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── Task Dispatcher 核心 ──────────────────────────────────

class TaskDispatcher:
    """
    任务调度引擎。
    
    负责任务的分解、匹配、分配和结果收集。
    连接 Agent Manager 和 Message Bus，实现端到端的协同调度。
    """

    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self._load()

    # ── 持久化 ──────────────────────────────────────────

    def _load(self) -> None:
        if DISPATCH_FILE.is_file():
            try:
                raw = json.loads(DISPATCH_FILE.read_text(encoding="utf-8"))
                for p_data in raw.get("pipelines", []):
                    pipeline = Pipeline(
                        pipeline_id=p_data["pipeline_id"],
                        name=p_data.get("name", ""),
                        description=p_data.get("description", ""),
                        status=p_data.get("status", PipelineStatus.CREATED.value),
                        created_at=p_data.get("created_at", ""),
                        completed_at=p_data.get("completed_at", ""),
                        total_duration=p_data.get("total_duration", 0.0),
                    )
                    for s_data in p_data.get("subtasks", []):
                        pipeline.subtasks.append(Subtask(**s_data))
                    self._pipelines[pipeline.pipeline_id] = pipeline
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        DISPATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pipelines": [
                {
                    "pipeline_id": p.pipeline_id,
                    "name": p.name,
                    "description": p.description,
                    "subtasks": [asdict(s) for s in p.subtasks],
                    "status": p.status,
                    "created_at": p.created_at,
                    "completed_at": p.completed_at,
                    "total_duration": p.total_duration,
                }
                for p in self._pipelines.values()
            ]
        }
        DISPATCH_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 模板匹配 ─────────────────────────────────────────

    def _match_template(self, task_description: str) -> str:
        """根据任务描述自动匹配最合适的分解模板。"""
        desc_lower = task_description.lower()
        for keyword in DECOMPOSITION_TEMPLATES:
            if keyword.lower() in desc_lower:
                return keyword
        return "通用"

    # ── 任务分解 ─────────────────────────────────────────

    def decompose(
        self,
        task: str = "",
        template: str = "",
        custom_subtasks: str = "",
    ) -> str:
        """将复杂任务拆解为子任务序列。"""
        if not task and not custom_subtasks:
            raise DispatchError("请提供任务描述或自定义子任务")

        # 生成流水线ID
        pipeline_id = f"PL_{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 解析子任务
        subtasks: list[Subtask] = []

        if custom_subtasks:
            # 使用自定义子任务
            try:
                custom = json.loads(custom_subtasks)
                if not isinstance(custom, list):
                    raise DispatchError("custom_subtasks 必须是 JSON 数组")
                for i, item in enumerate(custom):
                    st = Subtask(
                        task_id=f"{pipeline_id}_S{i+1}",
                        description=item.get("description", f"子任务 {i+1}"),
                        required_capability=item.get("capability", "research"),
                        preferred_agent_type=item.get("agent", ""),
                        params=item.get("params", {}),
                        depends_on=item.get("depends_on", []),
                    )
                    subtasks.append(st)
            except json.JSONDecodeError as exc:
                raise DispatchError(f"custom_subtasks JSON 解析错误: {exc}")
        else:
            # 使用模板匹配
            matched = template or self._match_template(task)
            template_def = DECOMPOSITION_TEMPLATES.get(matched)
            if not template_def:
                template_def = DECOMPOSITION_TEMPLATES["通用"]
                matched = "通用"

            for i, step in enumerate(template_def):
                deps: list[str] = []
                if i > 0:
                    deps = [f"{pipeline_id}_S{i}"]  # 默认串行依赖

                st = Subtask(
                    task_id=f"{pipeline_id}_S{i+1}",
                    description=step["description"],
                    required_capability=step["capability"],
                    preferred_agent_type=step.get("agent", ""),
                    params={"original_task": task, "step_index": i + 1,
                            "total_steps": len(template_def)},
                    depends_on=deps,
                )
                subtasks.append(st)

        # 创建流水线
        pipeline = Pipeline(
            pipeline_id=pipeline_id,
            name=task[:80] if task else "自定义流水线",
            description=task,
            subtasks=subtasks,
            created_at=now,
        )
        self._pipelines[pipeline_id] = pipeline
        self._save()

        # 格式化输出
        matched_template = template or (self._match_template(task) if task else "自定义")
        lines = [
            f"🔧 任务分解完成 — 流水线 [{pipeline_id}]",
            f"{'='*55}",
            f"📋 任务: {task[:100]}",
            f"📐 模板: {matched_template}",
            f"📊 子任务: {len(subtasks)} 个",
            f"⏰ 创建时间: {now}",
            f"",
            f"📋 子任务序列:",
        ]

        for st in subtasks:
            agent_icon = {
                "researcher": "🔍", "writer": "📝", "analyst": "📊",
                "reviewer": "🔒", "designer": "🎨", "monitor": "📈",
            }.get(st.preferred_agent_type, "❓")

            deps_str = f" ← 依赖: {', '.join(st.depends_on)}" if st.depends_on else ""
            lines.append(
                f"  {agent_icon} [{st.task_id}] {st.description[:60]}"
            )
            lines.append(f"     能力要求: {st.required_capability} | "
                         f"偏好Agent: {st.preferred_agent_type or '自动'}{deps_str}")

        lines.append(f"")
        lines.append(f"💡 下一步: 使用 dispatch_all action={pipeline_id} 自动调度所有子任务")
        lines.append(f"         或 dispatch action={pipeline_id} 逐个调度")

        return "\n".join(lines)

    # ── 查找最佳 Agent ────────────────────────────────────

    def _find_best_agent(self, capability: str, preferred_type: str = "") -> str:
        """
        按能力和负载查找最佳 Agent。
        
        优先级：偏好类型匹配 > 能力匹配 > 空闲 > 成功率高
        """
        try:
            from tools.agent_manager import _manager

            candidates = []
            for agent in _manager._agents.values():
                # 必须匹配能力
                if capability not in agent.capabilities:
                    continue
                # 必须不在错误或离线状态
                if agent.status in ("error", "offline"):
                    continue

                # 评分
                score = 0
                # 偏好类型匹配 +50
                if preferred_type and agent.agent_id == preferred_type:
                    score += 50
                # 空闲 +30
                if agent.status == "idle":
                    score += 30
                # 成功率高 +20
                score += int(agent.success_rate * 20)
                # 任务少 +10（负载均衡）
                score += max(0, 10 - agent.task_count)

                candidates.append((score, agent.agent_id))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]

        except Exception:
            pass

        # 如果没有合适的Agent，返回偏好类型作为默认
        return preferred_type or "researcher"

    # ── 单任务调度 ─────────────────────────────────────────

    def dispatch(
        self,
        pipeline_id: str = "",
        subtask_id: str = "",
    ) -> str:
        """调度单个子任务到最优Agent。"""
        if not pipeline_id:
            raise DispatchError("请指定流水线 ID")

        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise DispatchError(f"未找到流水线: {pipeline_id}")

        # 查找子任务
        subtask = None
        if subtask_id:
            for st in pipeline.subtasks:
                if st.task_id == subtask_id:
                    subtask = st
                    break
            if not subtask:
                raise DispatchError(f"未找到子任务: {subtask_id}")
        else:
            # 找第一个未分配的子任务
            for st in pipeline.subtasks:
                if st.status == SubtaskStatus.PENDING.value:
                    subtask = st
                    break
            if not subtask:
                return f"ℹ️ 流水线 [{pipeline_id}] 所有子任务已分配或完成"

        # 检查依赖
        for dep_id in subtask.depends_on:
            dep = next((s for s in pipeline.subtasks if s.task_id == dep_id), None)
            if dep and dep.status != SubtaskStatus.DONE.value:
                return (
                    f"⛔ 子任务 [{subtask.task_id}] 依赖 [{dep_id}] 尚未完成\n"
                    f"   {dep.description[:60]}: {dep.status}"
                )

        # 找最佳Agent
        best_agent = self._find_best_agent(
            subtask.required_capability,
            subtask.preferred_agent_type,
        )

        # 分配任务
        try:
            from tools.agent_manager import _manager
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            result = _manager.assign_task(
                agent_id=best_agent,
                task_id=subtask.task_id,
                task_description=subtask.description,
            )

            subtask.assigned_agent = best_agent
            subtask.status = SubtaskStatus.ASSIGNED.value
            subtask.started_at = now

            # 更新流水线状态
            pipeline.status = PipelineStatus.RUNNING.value
            self._save()

            # 发送消息通知
            try:
                from tools.message_bus import _bus
                _bus.send(
                    target=best_agent,
                    msg_type="task",
                    content=json.dumps({
                        "pipeline_id": pipeline_id,
                        "subtask_id": subtask.task_id,
                        "description": subtask.description,
                        "params": subtask.params,
                    }),
                    priority=8,
                    correlation_id=pipeline_id,
                )
            except Exception:
                pass

            return (
                f"📤 子任务已调度\n"
                f"{'─'*40}\n"
                f"流水线:   [{pipeline_id}] {pipeline.name[:50]}\n"
                f"子任务:   [{subtask.task_id}] {subtask.description[:60]}\n"
                f"分配给:   [{best_agent}]\n"
                f"能力要求: {subtask.required_capability}\n"
                f"时间:     {now}\n"
                f"\n{result}"
            )

        except Exception as exc:
            return f"❌ 调度失败: {exc}"

    # ── 全量调度 ──────────────────────────────────────────

    def dispatch_all(
        self,
        pipeline_id: str = "",
        strategy: str = "dag",
    ) -> str:
        """调度流水线中所有就绪的子任务。"""
        if not pipeline_id:
            raise DispatchError("请指定流水线 ID")

        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise DispatchError(f"未找到流水线: {pipeline_id}")

        if pipeline.status == PipelineStatus.DONE.value:
            return f"ℹ️ 流水线 [{pipeline_id}] 已完成"

        dispatched = []
        skipped = []

        for subtask in pipeline.subtasks:
            if subtask.status != SubtaskStatus.PENDING.value:
                skipped.append((subtask.task_id, subtask.status))
                continue

            # 检查依赖
            deps_met = True
            for dep_id in subtask.depends_on:
                dep = next(
                    (s for s in pipeline.subtasks if s.task_id == dep_id), None
                )
                if dep and dep.status != SubtaskStatus.DONE.value:
                    deps_met = False
                    break

            if not deps_met and strategy != "parallel":
                skipped.append((subtask.task_id, "等待依赖"))
                continue

            # 分配
            try:
                best_agent = self._find_best_agent(
                    subtask.required_capability,
                    subtask.preferred_agent_type,
                )
                from tools.agent_manager import _manager
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                _manager.assign_task(
                    agent_id=best_agent,
                    task_id=subtask.task_id,
                    task_description=subtask.description,
                )

                subtask.assigned_agent = best_agent
                subtask.status = SubtaskStatus.ASSIGNED.value
                subtask.started_at = now
                dispatched.append((subtask.task_id, best_agent))

                # 消息通知
                try:
                    from tools.message_bus import _bus
                    _bus.send(
                        target=best_agent,
                        msg_type="task",
                        content=json.dumps({
                            "pipeline_id": pipeline_id,
                            "subtask_id": subtask.task_id,
                            "description": subtask.description,
                        }),
                        priority=8,
                        correlation_id=pipeline_id,
                    )
                except Exception:
                    pass

            except Exception as exc:
                skipped.append((subtask.task_id, f"错误: {exc}"))

        pipeline.status = PipelineStatus.RUNNING.value
        self._save()

        lines = [
            f"🚀 全量调度 — 流水线 [{pipeline_id}]",
            f"{'='*50}",
            f"策略: {strategy}",
            f"已调度: {len(dispatched)} 个子任务",
        ]

        for tid, agent in dispatched:
            lines.append(f"  ✅ [{tid}] → {agent}")

        if skipped:
            lines.append(f"\n跳过: {len(skipped)} 个")
            for tid, reason in skipped[:10]:
                lines.append(f"  ⏭️ [{tid}] — {reason}")

        return "\n".join(lines)

    # ── 结果收集 ──────────────────────────────────────────

    def collect(self, pipeline_id: str = "") -> str:
        """收集流水线所有子任务的结果。"""
        if not pipeline_id:
            raise DispatchError("请指定流水线 ID")

        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise DispatchError(f"未找到流水线: {pipeline_id}")

        # 从 Agent Manager 同步任务状态
        try:
            from tools.agent_manager import _manager

            for subtask in pipeline.subtasks:
                if subtask.status in (
                    SubtaskStatus.DONE.value,
                    SubtaskStatus.FAILED.value,
                ):
                    continue

                # 检查 Agent Manager 中的任务记录
                for record in _manager._task_records:
                    if record.task_id == subtask.task_id:
                        if record.status == "done":
                            subtask.status = SubtaskStatus.DONE.value
                            subtask.result = record.result
                            subtask.completed_at = record.completed_at
                        elif record.status == "failed":
                            subtask.status = SubtaskStatus.FAILED.value
                            subtask.error = record.error
                            subtask.completed_at = record.completed_at
                        break
        except Exception:
            pass

        # 统计
        total = len(pipeline.subtasks)
        done = sum(1 for s in pipeline.subtasks if s.status == SubtaskStatus.DONE.value)
        failed = sum(1 for s in pipeline.subtasks if s.status == SubtaskStatus.FAILED.value)
        pending = sum(1 for s in pipeline.subtasks if s.status in (
            SubtaskStatus.PENDING.value, SubtaskStatus.ASSIGNED.value
        ))

        # 更新流水线状态
        if done == total:
            pipeline.status = PipelineStatus.DONE.value
            pipeline.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif failed > 0 and done + failed == total:
            pipeline.status = PipelineStatus.FAILED.value
        elif done > 0:
            pipeline.status = PipelineStatus.PARTIAL.value

        self._save()

        # 生成报告
        progress = "█" * done + "▒" * (total - done - failed) + "✗" * failed
        lines = [
            f"📊 流水线结果收集 — [{pipeline_id}]",
            f"{'='*55}",
            f"📋 {pipeline.name[:80]}",
            f"进度: [{progress}] {done}/{total}",
            f"状态: {pipeline.status}",
            f"✅ 完成: {done} | ❌ 失败: {failed} | ⏳ 待处理: {pending}",
            f"",
            f"📋 各子任务详情:",
        ]

        for st in pipeline.subtasks:
            icon = {
                SubtaskStatus.DONE.value: "✅",
                SubtaskStatus.FAILED.value: "❌",
                SubtaskStatus.PENDING.value: "⏳",
                SubtaskStatus.ASSIGNED.value: "📤",
            }.get(st.status, "❓")

            lines.append(f"  {icon} [{st.task_id}] {st.description[:55]}")
            lines.append(f"     Agent: {st.assigned_agent or '未分配'} | "
                         f"状态: {st.status}")
            if st.result:
                lines.append(f"     结果: {st.result[:100]}")
            if st.error:
                lines.append(f"     错误: {st.error[:100]}")

        # 汇总
        if done == total:
            lines.append(f"\n🎉 流水线全部完成！")
            lines.append(f"💡 可收集各子任务结果进行最终汇总。")
        elif failed > 0:
            lines.append(f"\n⚠️ 有 {failed} 个子任务失败。")
            lines.append(f"💡 可使用 dispatch 重新调度失败的子任务。")

        return "\n".join(lines)

    # ── 状态查看 ──────────────────────────────────────────

    def status(self, pipeline_id: str = "") -> str:
        """查看流水线状态。"""
        if pipeline_id:
            return self.collect(pipeline_id)

        if not self._pipelines:
            return "📋 暂无流水线"

        lines = [f"📋 流水线列表 (共 {len(self._pipelines)} 个):\n"]
        for pid, p in self._pipelines.items():
            done = sum(1 for s in p.subtasks if s.status == SubtaskStatus.DONE.value)
            total = len(p.subtasks)
            progress = f"{done}/{total}"
            status_icon = {
                PipelineStatus.DONE.value: "✅",
                PipelineStatus.RUNNING.value: "🔄",
                PipelineStatus.PARTIAL.value: "🟡",
                PipelineStatus.FAILED.value: "❌",
                PipelineStatus.CREATED.value: "📋",
            }.get(p.status, "❓")

            lines.append(
                f"  {status_icon} [{pid}] {p.name[:50]}"
            )
            lines.append(f"     进度: {progress} | 状态: {p.status} | "
                         f"创建: {p.created_at[:16]}")

        return "\n".join(lines)

    def list_pipelines(self) -> str:
        """列出所有流水线。"""
        return self.status()

    def cancel(self, pipeline_id: str = "") -> str:
        """取消流水线。"""
        if not pipeline_id:
            raise DispatchError("请指定流水线 ID")

        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise DispatchError(f"未找到流水线: {pipeline_id}")

        # 释放已分配但未完成的Agent
        try:
            from tools.agent_manager import _manager
            for subtask in pipeline.subtasks:
                if subtask.status == SubtaskStatus.ASSIGNED.value and subtask.assigned_agent:
                    agent = _manager._agents.get(subtask.assigned_agent)
                    if agent and agent.status == "busy":
                        agent.status = "idle"
                        agent.current_task = ""
            _manager._save()
        except Exception:
            pass

        # 标记所有未完成子任务为跳过
        for subtask in pipeline.subtasks:
            if subtask.status not in (
                SubtaskStatus.DONE.value,
                SubtaskStatus.FAILED.value,
            ):
                subtask.status = SubtaskStatus.SKIPPED.value

        pipeline.status = PipelineStatus.FAILED.value
        self._save()

        return f"🚫 流水线 [{pipeline_id}] 已取消"

    def templates(self) -> str:
        """列出所有可用的分解模板。"""
        lines = ["📐 可用的任务分解模板:\n"]

        seen = set()
        for keyword, steps in DECOMPOSITION_TEMPLATES.items():
            if keyword in seen:
                continue
            seen.add(keyword)

            # 选择中文关键词作为显示名
            display = keyword
            agent_flow = " → ".join(
                step.get("agent", "?").capitalize()
                for step in steps
            )

            lines.append(f"  📌 {display}")
            lines.append(f"     流水线: {agent_flow}")
            lines.append(f"     步骤数: {len(steps)}")
            for i, step in enumerate(steps, 1):
                icon = {
                    "researcher": "🔍", "writer": "📝", "analyst": "📊",
                    "reviewer": "🔒", "designer": "🎨",
                }.get(step.get("agent", ""), "❓")
                lines.append(f"       {i}. {icon} {step['description']}")
            lines.append("")

        lines.append("💡 使用方法:")
        lines.append("   task_dispatcher action=decompose task='开发一个文字冒险游戏'")
        lines.append("   task_dispatcher action=decompose task='...' template=article")
        lines.append("   task_dispatcher action=decompose task='...' custom_subtasks='[...]'")

        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_dispatcher = TaskDispatcher()


def execute_task_dispatcher_tool(arguments: dict[str, Any]) -> str:
    """执行 task_dispatcher 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "decompose":
            return _dispatcher.decompose(
                task=arguments.get("task", ""),
                template=arguments.get("template", ""),
                custom_subtasks=arguments.get("custom_subtasks", ""),
            )

        elif action == "dispatch":
            return _dispatcher.dispatch(
                pipeline_id=arguments.get("pipeline_id", ""),
                subtask_id=arguments.get("subtask_id", ""),
            )

        elif action == "dispatch_all":
            return _dispatcher.dispatch_all(
                pipeline_id=arguments.get("pipeline_id", ""),
                strategy=arguments.get("strategy", "dag"),
            )

        elif action == "collect":
            return _dispatcher.collect(
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "status":
            return _dispatcher.status(
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "list_pipelines":
            return _dispatcher.list_pipelines()

        elif action == "cancel":
            return _dispatcher.cancel(
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "templates":
            return _dispatcher.templates()

        else:
            return f"未知操作: {action}"

    except DispatchError as exc:
        return f"Task Dispatcher 错误: {exc}"
