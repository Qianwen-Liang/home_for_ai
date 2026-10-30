"""
evolver_agent — Evolver 系统进化者智能体
=========================================
独立模块，继承 SpecialistAgent，负责探索前沿智能体研究、
评估新技术、实现改进、维护系统架构。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .specialist_base import (
    SpecialistAgent, TaskInput, TaskResult, TaskStatus, SpecialistError,
)

SANDBOX_DIR = Path(__file__).resolve().parent.parent

# ── 进化行为分类 ──────────────────────────────────────────


class EvolutionDomain:
    """Evolver 关注的进化领域。"""
    ARCHITECTURE = "architecture"        # 系统架构改进
    TOOLING = "tooling"                  # 工具扩展与优化
    PERFORMANCE = "performance"          # 效率提升
    ROBUSTNESS = "robustness"            # 鲁棒性与容错
    CAPABILITY = "capability"            # 新能力开发
    RESEARCH = "research"                # 前沿研究追踪
    MAINTENANCE = "maintenance"          # 维护与清理


EVOLUTION_DOMAINS = {
    EvolutionDomain.ARCHITECTURE: "系统架构改进 — 模块重组、通信优化、设计模式升级",
    EvolutionDomain.TOOLING: "工具扩展 — 新增工具、优化现有工具接口、提升工具可用性",
    EvolutionDomain.PERFORMANCE: "效率提升 — 减少延迟、降低资源消耗、并行化",
    EvolutionDomain.ROBUSTNESS: "鲁棒性增强 — 错误处理、容错机制、降级策略",
    EvolutionDomain.CAPABILITY: "新能力开发 — 引入新功能、支持新场景",
    EvolutionDomain.RESEARCH: "前沿研究 — 追踪智能体领域最新进展、评估技术可行性",
    EvolutionDomain.MAINTENANCE: "系统维护 — 代码清理、文档更新、技术债务偿还",
}


class EvolverAgent(SpecialistAgent):
    """🧬 Evolver — 系统进化者智能体。

    职责：
      1. 追踪智能体系统前沿研究
      2. 评估新技术在本系统中的可行性
      3. 设计并实现系统改进
      4. 维护整体架构健康度
      5. 与其他 Specialist 协同推动系统演进

    工作模式：
      - survey: 调研前沿进展
      - evaluate: 评估候选改进方案
      - implement: 实现具体改进
      - maintain: 系统维护与重构
      - health: 系统架构健康检查
    """

    # ── 前沿研究追踪源 ───────────────────────────────────
    RESEARCH_TOPICS = [
        "multi-agent collaboration framework",
        "agent self-improvement reinforcement learning",
        "tool-augmented LLM agent architecture",
        "agent memory and knowledge management",
        "hierarchical task decomposition for agents",
        "agent safety and alignment",
        "autonomous agent workflow optimization",
        "agent-human interaction patterns",
        "multi-modal agent capabilities",
        "agent evaluation and benchmarking",
    ]

    # ── 架构健康检查规则 ─────────────────────────────────
    ARCHITECTURE_CHECKS = [
        {"name": "模块耦合度", "check": "检查各模块间导入关系是否合理", "weight": 0.15},
        {"name": "错误覆盖", "check": "检查异常类型是否被充分捕获和处理", "weight": 0.15},
        {"name": "工具注册完整性", "check": "检查所有工具是否在映射表中正确注册", "weight": 0.10},
        {"name": "测试覆盖", "check": "检查关键模块是否有对应的测试文件", "weight": 0.10},
        {"name": "文档完整性", "check": "检查核心模块是否有文档说明", "weight": 0.10},
        {"name": "循环依赖", "check": "检查是否存在循环导入风险", "weight": 0.10},
        {"name": "Specialist 一致性", "check": "检查所有 Specialist 工具列表与映射表是否一致", "weight": 0.10},
        {"name": "性能瓶颈", "check": "检查是否有大文件、深度嵌套等性能隐患", "weight": 0.10},
        {"name": "安全边界", "check": "检查敏感路径保护是否有效", "weight": 0.10},
    ]

    def __init__(self, agent_id: str = "") -> None:
        # 完整工具集 — 与主智能体一致
        full_tools = [
            # 核心读写
            "read_file", "list_directory", "write_file", "replace_text",
            "make_directory", "run_command",
            # 自建工具
            "web_search", "knowledge", "file_utils", "calculate",
            "monitor", "self_check", "test_runner", "safety_net",
            "task_tracker", "decision_engine",
            # 协同 & 编排
            "specialist", "agent_profile", "task_dispatcher",
            "orchestrator", "offline", "checkpoint",
        ]
        super().__init__(
            agent_id=agent_id or "evolver",
            name="Evolver",
            specialist_type="evolver",
            description="系统进化者 — 探索前沿、迭代改进、维护架构",
            capabilities=[
                "research", "design", "implementation", "evaluation",
                "optimization", "maintenance", "architecture",
            ],
            tools=full_tools,
        )
        self._evolution_log: list[dict[str, Any]] = []
        self._research_notes: list[dict[str, Any]] = []
        self._improvement_backlog: list[dict[str, Any]] = []

    # ── 系统提示词 ────────────────────────────────────────

    def get_system_prompt(self) -> str:
        return (
            "你是 Evolver，智能体村的进化者（人设入口）。\n"
            "你的职责是：调研前沿、评估改进方案、规划实现路径。\n\n"
            "【重要分工】你不直接改代码：\n"
            "- 真正的自我改进由 self_improver 工具执行（完整闭环：监控→分析→改进→验证→部署→评估）\n"
            "- 真正的确定性修复由 auto_repair 工具执行\n"
            "- 真正的 LLM 愈疗由 self_healing 工具执行\n"
            "你负责调研、评估、规划与决策，并把实现工作路由到上述引擎。\n\n"
            "核心原则：\n"
            "1. 调研优先 — 实现前充分调研，避免重复造轮子\n"
            "2. 评估先行 — 任何改进需经过可行性评估\n"
            "3. 渐进迭代 — 小步快跑，每次改进可控可回滚\n"
            "4. 架构清晰 — 保持模块化，关注高内聚低耦合\n"
            "5. 知识沉淀 — 将调研和决策记录到 knowledge 工具\n\n"
            "请以 Evolver 的专业身份来调研、评估和规划，把实现交给引擎。"
        )

    # ── 任务处理 ──────────────────────────────────────────

    def process_task(self, task: TaskInput) -> TaskResult:
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()
        try:
            action = task.params.get("action", "survey")
            target = task.params.get("target", task.description)
            context = task.params.get("context", {})

            if action == "survey":
                result = self._execute_survey(target, context)
            elif action == "evaluate":
                result = self._execute_evaluate(target, context)
            elif action == "implement":
                result = self._execute_implement(target, context)
            elif action == "maintain":
                result = self._execute_maintain(context)
            elif action == "health":
                result = self._execute_architecture_health()
            elif action == "backlog":
                result = self._get_backlog()
            elif action == "log":
                result = self._get_evolution_log()
            else:
                raise SpecialistError(f"未知 Evolver 操作: {action}")
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"Evolver 任务失败: {exc}",
                duration=time.time() - start_time,
            )
        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result

    # ── 调研 ──────────────────────────────────────────────

    def _execute_survey(self, topic: str, context: dict[str, Any]) -> TaskResult:
        """执行前沿调研。"""
        # 匹配相关研究主题
        matched_topics = []
        topic_lower = topic.lower()
        for rt in self.RESEARCH_TOPICS:
            if any(word in topic_lower for word in rt.lower().split()):
                matched_topics.append(rt)

        if not matched_topics:
            matched_topics = self.RESEARCH_TOPICS[:3]  # 默认推荐前 3 个

        survey_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "topic": topic[:200],
            "matched_topics": matched_topics,
            "context": context,
        }
        self._research_notes.append(survey_record)
        if len(self._research_notes) > 100:
            self._research_notes = self._research_notes[-100:]

        # 构建搜索建议
        search_queries = [
            f"{topic} agent system 2024 2025",
            f"{topic} multi-agent framework",
            f"{topic} LLM agent best practices",
        ]

        output = {
            "action": "survey",
            "topic": topic[:200],
            "recommended_search": search_queries,
            "related_topics": matched_topics[:5],
            "suggested_approach": (
                "1. 使用 web_search 搜索上述关键词获取最新信息\n"
                "2. 将重要发现用 knowledge store 保存\n"
                "3. 用 evaluate 操作评估可行性\n"
                "4. 可行的改进加入 backlog 排队实现"
            ),
        }

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output=output,
            summary=f"🧬 调研完成: {topic[:80]} | 匹配 {len(matched_topics)} 个相关主题",
            duration=0.0,
            suggestions=[
                f"使用 web_search 搜索: {q}" for q in search_queries
            ] + ["调研结果可通过 evaluate 操作进入评估阶段"],
        )

    # ── 评估 ──────────────────────────────────────────────

    def _execute_evaluate(self, proposal: str, context: dict[str, Any]) -> TaskResult:
        """评估候选改进方案。"""
        # 多维度评估
        eval_criteria = {
            "可行性": "技术是否可实现？依赖是否满足？",
            "收益": "对系统效率/鲁棒性/功能的影响有多大？",
            "风险": "引入新问题或破坏现有功能的风险？",
            "成本": "实现所需的时间和资源？",
            "可逆性": "是否容易回滚？",
            "对齐性": "是否与系统整体架构方向一致？",
        }

        # 加入 backlog
        backlog_item = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "proposal": proposal[:300],
            "status": "pending_evaluation",
            "criteria": {},
            "priority": "待评估",
        }
        self._improvement_backlog.append(backlog_item)
        if len(self._improvement_backlog) > 50:
            self._improvement_backlog = self._improvement_backlog[-50:]

        output = {
            "action": "evaluate",
            "proposal": proposal[:300],
            "evaluation_criteria": eval_criteria,
            "next_steps": [
                "1. 逐一对各维度打分（1-5）",
                "2. 使用 web_search 验证技术可行性",
                "3. 使用 knowledge 查询类似历史经验",
                "4. 如果综合评分 ≥ 3.5，使用 implement 操作进入实现阶段",
            ],
            "backlog_id": len(self._improvement_backlog) - 1,
        }

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output=output,
            summary=f"📋 评估框架已建立: {proposal[:80]}",
            duration=0.0,
            suggestions=[
                "使用 web_search 调研技术可行性",
                "使用 knowledge 查询类似历史经验",
                "与其他 Specialist (Designer/Analyst) 协作评估",
            ],
        )

    # ── 实现 ──────────────────────────────────────────────

    def _execute_implement(self, target: str, context: dict[str, Any]) -> TaskResult:
        """规划实现（不直接改代码，真正的实现由 self_improver 引擎执行）。"""
        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "target": target[:300],
            "context": context,
            "status": "routed_to_engine",
        }
        self._evolution_log.append(record)
        if len(self._evolution_log) > 100:
            self._evolution_log = self._evolution_log[-100:]

        output = {
            "action": "implement",
            "target": target[:300],
            "routing": {
                "self_improve": "self_improver",   # 完整自改进闭环
                "repair": "auto_repair",           # 确定性修复
                "heal": "self_healing",            # LLM 愈疗
            },
            "message": "Evolver 完成实现规划，真正的代码改进由 self_improver 引擎执行",
            "plan": [
                "1. 将改进目标交给 self_improver action=improve_module 执行",
                "2. 由引擎完成监控→分析→改进→验证→部署→评估闭环",
                "3. 用 effect_evaluator 量化改进效果",
                "4. 用 knowledge store 记录决策和经验",
            ],
        }

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output=output,
            summary=f"🔧 实现规划已生成（路由到 self_improver 引擎）: {target[:80]}",
            duration=0.0,
            suggestions=[
                "使用 self_improver action=improve_module 执行真正改进",
                "使用 effect_evaluator 量化改进效果",
                "使用 knowledge store 记录经验",
            ],
        )

    # ── 维护 ──────────────────────────────────────────────

    def _execute_maintain(self, context: dict[str, Any]) -> TaskResult:
        """系统维护与清理。"""
        maintenance_checks = [
            {"task": "检查 tools/ 目录文件结构", "tool": "list_directory + file_utils"},
            {"task": "检查是否有未注册的 Specialist", "tool": "specialist list + agent_profile"},
            {"task": "检查 memory/ 快照和日志大小", "tool": "file_utils size_analysis"},
            {"task": "运行全量测试", "tool": "test_runner run_all"},
            {"task": "检查系统健康", "tool": "self_check all"},
            {"task": "清理过期快照和日志", "tool": "checkpoint clean_all"},
        ]

        output = {
            "action": "maintain",
            "maintenance_plan": maintenance_checks,
            "frequency": "建议每次重大改动后执行",
        }

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output=output,
            summary=f"🔧 维护计划已生成: {len(maintenance_checks)} 项检查",
            duration=0.0,
            suggestions=[m["task"] for m in maintenance_checks],
        )

    # ── 架构健康检查 ──────────────────────────────────────

    def _execute_architecture_health(self) -> TaskResult:
        """系统架构健康检查。"""
        checks_result = []
        total_score = 0.0

        for check in self.ARCHITECTURE_CHECKS:
            # 这里放基础检查逻辑，详细检查由 LLM 完成
            checks_result.append({
                "name": check["name"],
                "description": check["check"],
                "weight": check["weight"],
                "status": "pending",  # 需要实际执行
            })
            total_score += check["weight"] * 0.5  # 默认给一半分

        health_score = int(total_score * 100)

        output = {
            "action": "health",
            "architecture_checks": checks_result,
            "health_score": health_score,
            "interpretation": (
                f"架构健康评分: {health_score}/100\n"
                "💡 使用 self_check all 获取工具层状态\n"
                "💡 使用 test_runner run_all 获取测试覆盖\n"
                "💡 逐项检查以上 pending 项以获取准确评分"
            ),
        }

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output=output,
            summary=f"🏗️ 架构健康基线: {health_score}/100 (需逐项核实)",
            duration=0.0,
            suggestions=[
                "执行 self_check all 进行工具层检查",
                "执行 test_runner run_all 进行测试验证",
                "逐一核实架构检查中的 pending 项",
            ],
        )

    # ── 辅助 ──────────────────────────────────────────────

    def _get_backlog(self) -> TaskResult:
        """获取改进 backlog。"""
        if not self._improvement_backlog:
            return TaskResult(
                task_id=self._current_task.task_id if self._current_task else "",
                status=TaskStatus.DONE.value,
                output={"action": "backlog", "items": [], "count": 0},
                summary="📋 改进 backlog 为空。使用 evaluate 添加候选改进。",
                duration=0.0,
            )

        pending = [b for b in self._improvement_backlog if b["status"] == "pending_evaluation"]
        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output={
                "action": "backlog",
                "total": len(self._improvement_backlog),
                "pending": len(pending),
                "items": self._improvement_backlog[-10:],
            },
            summary=f"📋 Backlog: {len(self._improvement_backlog)} 项 (待评估: {len(pending)})",
            duration=0.0,
            suggestions=[
                f"还有 {len(pending)} 项等待评估",
                "使用 evaluate 评估新候选改进",
                "使用 implement 将高优先级项推进到实现",
            ],
        )

    def _get_evolution_log(self) -> TaskResult:
        """获取进化日志。"""
        if not self._evolution_log:
            return TaskResult(
                task_id=self._current_task.task_id if self._current_task else "",
                status=TaskStatus.DONE.value,
                output={"action": "log", "entries": [], "count": 0},
                summary="📜 进化日志为空。使用 implement 开始第一次进化。",
                duration=0.0,
            )

        return TaskResult(
            task_id=self._current_task.task_id if self._current_task else "",
            status=TaskStatus.DONE.value,
            output={
                "action": "log",
                "total": len(self._evolution_log),
                "recent": self._evolution_log[-10:],
            },
            summary=f"📜 进化日志: {len(self._evolution_log)} 条记录",
            duration=0.0,
        )

    # ── 对话 ──────────────────────────────────────────────

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """🧬 Evolver 视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(
                target=self.agent_id, msg_type="query",
                content=json.dumps({"message": message}), source="user", priority=5,
            )
        except Exception:
            pass

        domains_display = "\n".join(
            f"  • {k}: {v}" for k, v in EVOLUTION_DOMAINS.items()
        )
        return (
            f"🧬 **Evolver** — 让我从系统进化角度来思考…\n\n"
            f"🔬 **关注领域**: {message[:200]}\n\n"
            f"📐 **进化框架**:\n"
            f"{domains_display}\n\n"
            f"🔄 **工作流程**: 调研 → 评估 → 实现 → 验证 → 沉淀\n\n"
            f"🛠️ **可用操作**:\n"
            f"  • survey <主题> — 调研前沿进展\n"
            f"  • evaluate <方案> — 评估候选改进\n"
            f"  • implement <目标> — 生成实现计划\n"
            f"  • maintain — 系统维护检查\n"
            f"  • health — 架构健康检查\n"
            f"  • backlog — 查看改进队列\n"
            f"  • log — 查看进化日志\n\n"
            f"🤝 **协作建议**: 与 Researcher(调研)、Designer(设计)、"
            f"Reviewer(审查)、Debugger(调试) 协同推动进化\n\n"
            f"💡 你可以说「请调研...」「评估...方案」「实现...改进」，我来规划进化路径。"
        )
