"""
orchestrator — 统一协调器（F5/K2）
==================================
Agent 1 作为 Orchestrator，协调多个 Specialist Agent 完成复杂任务。

设计启发：
  - AutoGen: 分布式 Agent 协调
  - CrewAI: 层级任务管理
  - LangGraph: 有状态工作流编排

核心能力：
  - 一键编排：接收高层任务 → 自动分解 → 分配 → 执行 → 汇总
  - 并行调度：无依赖的子任务自动并行分配
  - 失败重试：失败子任务自动重新分配
  - 进度追踪：实时查看流水线执行进度

使用方式：
  orchestrator action=run task='开发一个文字冒险游戏'
  orchestrator action=status pipeline_id=PL_xxx
  orchestrator action=retry pipeline_id=PL_xxx subtask_id=PL_xxx_S3

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent


# ── 错误类型 ──────────────────────────────────────────────

class OrchestratorError(RuntimeError):
    """Orchestrator 错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "orchestrator",
        "description": (
            "多智能体统一协调器。一键将高层任务自动分解、分配给最合适的 Specialist Agent、"
            "协调并行/串行执行，并汇总所有结果。支持流水线追踪、失败重试和进度查看。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "run",
                        "run_workflow",
                        "status",
                        "retry",
                        "cancel",
                        "list_pipelines",
                        "health",
                        "request_approval",
                        "provide_feedback",
                        "escalate",
                        "help",
                    ],
                    "description": (
                        "操作类型："
                        "run — 一键运行完整流水线（分解→分配→等待→汇总）；"
                        "run_workflow — 创建 Specialist 绑定工作流并执行；"
                        "status — 查看流水线进度；"
                        "retry — 重试失败的子任务；"
                        "cancel — 取消流水线；"
                        "list_pipelines — 列出所有流水线；"
                        "health — 多Agent系统健康检查；"
                        "request_approval — 请求人类批准关键节点；"
                        "provide_feedback — 提供人类反馈；"
                        "escalate — Agent主动上报问题给人类；"
                        "help — 查看使用指南。"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "高层任务描述（用于 run 操作）",
                    "default": "",
                },
                "template": {
                    "type": "string",
                    "description": "分解模板名称（可选，自动匹配）",
                    "default": "",
                },
                "pipeline_id": {
                    "type": "string",
                    "description": "流水线 ID",
                    "default": "",
                },
                "subtask_id": {
                    "type": "string",
                    "description": "要重试的子任务 ID（用于 retry 操作）",
                    "default": "",
                },
                "strategy": {
                    "type": "string",
                    "enum": ["sequential", "parallel", "dag"],
                    "description": "调度策略：sequential 串行、parallel 并行、dag 按依赖图（默认）",
                    "default": "dag",
                },
                "stage_gate": {
                    "type": "boolean",
                    "description": "是否启用阶段门（人机阶段审查）。True 时分解后挂起等待人类审批，默认 False",
                    "default": False,
                },
                "workflow_spec": {
                    "type": "string",
                    "description": "工作流定义 JSON（用于 run_workflow）。节点绑定 Specialist 类型。",
                    "default": "",
                },
                "checkpoint_id": {
                    "type": "string",
                    "description": "检查点 ID（用于 run_workflow 的审批/检查点）",
                    "default": "",
                },
                "feedback": {
                    "type": "string",
                    "description": "人类反馈或审批意见",
                    "default": "",
                },
                "issue": {
                    "type": "string",
                    "description": "Agent上报的问题描述（用于 escalate）",
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── Orchestrator 核心 ─────────────────────────────────────

class Orchestrator:
    """
    统一协调器。
    
    作为 Agent 1 的"大脑"，协调 Task Dispatcher、Agent Manager、
    Message Bus 等组件，实现端到端的任务编排。
    """

    def __init__(self) -> None:
        # 注意：不在 __init__ 里创建默认 Specialist。
        # 否则 import 本模块（如 pytest collection）时会产生文件副作用，
        # 污染 agents.json，破坏其他测试的隔离性。
        # 默认 Specialist 的创建推迟到 run()/health() 等主动调用时惰性执行。
        pass

    # ── 初始化 ──────────────────────────────────────────

    def _ensure_default_specialists(self) -> None:
        """确保默认 Specialist Agent 已注册。"""
        try:
            from tools.agent_manager import _manager, create_default_specialists
            if len(_manager._agents) == 0:
                create_default_specialists(_manager)
        except Exception:
            pass

    # ── Agent 就绪检查 ──────────────────────────────────

    def _get_ready_agents(self) -> list[str]:
        """获取所有就绪的 Agent ID。"""
        try:
            from tools.agent_manager import _manager
            return [
                aid for aid, agent in _manager._agents.items()
                if agent.status in ("idle", "busy")
            ]
        except Exception:
            return []

    # ── 核心：一键编排 ───────────────────────────────────

    def run(
        self,
        task: str = "",
        template: str = "",
        strategy: str = "dag",
        stage_gate: bool = False,
    ) -> str:
        """
        一键运行完整流水线。
        
        流程：decompose → dispatch_all → collect
        stage_gate=True 时，分解后挂起等待人类审批（人机阶段审查常态化），
        人类通过 provide_feedback 批准后才继续调度执行。
        """
        if not task:
            raise OrchestratorError("请提供任务描述")

        # 确保 Agent 就绪
        self._ensure_default_specialists()
        ready = self._get_ready_agents()
        if not ready:
            return (
                "⚠️ 没有可用的 Specialist Agent。\n"
                "请先注册 Agent：agent_manager action=register ...\n"
                "或使用 orchestrator action=help 查看指南。"
            )

        # Step 1: 分解任务
        from tools.task_dispatcher import _dispatcher
        decompose_result = _dispatcher.decompose(
            task=task,
            template=template,
        )

        # 从分解结果提取 pipeline_id
        pipeline_id = ""
        for line in decompose_result.split("\n"):
            if "流水线 [" in line:
                # 提取 [... ] 中的 ID
                start = line.find("[") + 1
                end = line.find("]", start)
                pipeline_id = line[start:end]
                break

        if not pipeline_id:
            return f"任务分解失败:\n{decompose_result}"

        # Step 2: 广播任务启动通知
        try:
            from tools.message_bus import _bus
            _bus.broadcast(
                msg_type="notify",
                content=json.dumps({
                    "event": "pipeline_started",
                    "pipeline_id": pipeline_id,
                    "task": task,
                    "agent_count": len(ready),
                }),
                priority=5,
            )
        except Exception:
            pass

        # Step 3: 全量调度（可选阶段门：人机阶段审查）
        if stage_gate:
            gate_report = self.request_approval(pipeline_id=pipeline_id)
            lines = [
                f"🎯 流水线已分解，等待人类审批（阶段门）",
                f"{'='*55}",
                f"📋 任务: {task[:100]}",
                f"🔢 流水线: [{pipeline_id}]",
                f"",
                f"── 分解结果 ──",
                decompose_result,
                f"",
                f"🔐 阶段门已开启：请人类审批后继续执行",
                gate_report,
            ]
            return "\n".join(lines)

        dispatch_result = _dispatcher.dispatch_all(
            pipeline_id=pipeline_id,
            strategy=strategy,
        )

        # Step 4: 收集结果
        collect_result = _dispatcher.collect(pipeline_id=pipeline_id)

        # Step 5: 汇总报告
        pipeline = _dispatcher._pipelines.get(pipeline_id)
        total = len(pipeline.subtasks) if pipeline else 0
        done = sum(1 for s in pipeline.subtasks
                   if s.status == "done") if pipeline else 0

        lines = [
            f"🎯 流水线编排完成",
            f"{'='*55}",
            f"📋 任务: {task[:100]}",
            f"🔢 流水线: [{pipeline_id}]",
            f"🤖 可用Agent: {len(ready)} 个",
            f"📊 子任务: {total} 个 | ✅ {done} 完成",
            f"",
            f"── 分解结果 ──",
            decompose_result,
            f"",
            f"── 调度结果 ──",
            dispatch_result,
            f"",
            f"── 执行汇总 ──",
            collect_result,
            f"",
            f"💡 提示:",
            f"  • 使用 orchestrator action=status pipeline_id={pipeline_id} 查看进度",
            f"  • 使用 orchestrator action=retry pipeline_id={pipeline_id} 重试失败子任务",
            f"  • 交付前可用 artifact_validator 对产物做确定性校验（结构/数字/引用/可解析）",
        ]

        return "\n".join(lines)

    # ── 状态查看 ─────────────────────────────────────────

    def status(self, pipeline_id: str = "") -> str:
        """查看流水线状态。"""
        from tools.task_dispatcher import _dispatcher
        return _dispatcher.status(pipeline_id=pipeline_id)

    # ── 失败重试 ─────────────────────────────────────────

    def retry(self, pipeline_id: str = "", subtask_id: str = "") -> str:
        """重试失败的子任务。"""
        if not pipeline_id:
            raise OrchestratorError("请指定流水线 ID")

        from tools.task_dispatcher import _dispatcher
        pipeline = _dispatcher._pipelines.get(pipeline_id)
        if not pipeline:
            return f"❌ 未找到流水线: {pipeline_id}"

        # 找失败或跳过的子任务
        failed_subtasks = [
            s for s in pipeline.subtasks
            if s.status in ("failed", "skipped")
        ]

        if subtask_id:
            # 重试指定的子任务
            target = next(
                (s for s in pipeline.subtasks if s.task_id == subtask_id),
                None,
            )
            if not target:
                raise OrchestratorError(f"未找到子任务: {subtask_id}")
            if target.status not in ("failed", "skipped"):
                return f"子任务 [{subtask_id}] 状态为 {target.status}，无需重试"

            # 重置状态
            target.status = "pending"
            target.assigned_agent = ""
            target.result = ""
            target.error = ""
            _dispatcher._save()

            # 重新调度
            return _dispatcher.dispatch(
                pipeline_id=pipeline_id,
                subtask_id=subtask_id,
            )

        elif failed_subtasks:
            # 重试所有失败的子任务
            lines = [f"🔄 重试 {len(failed_subtasks)} 个失败子任务:\n"]
            for st in failed_subtasks:
                st.status = "pending"
                st.assigned_agent = ""
                st.result = ""
                st.error = ""
            _dispatcher._save()

            dispatch_result = _dispatcher.dispatch_all(pipeline_id=pipeline_id)
            lines.append(dispatch_result)

            collect_result = _dispatcher.collect(pipeline_id=pipeline_id)
            lines.append(f"\n{collect_result}")

            return "\n".join(lines)
        else:
            return f"流水线 [{pipeline_id}] 没有失败或跳过的子任务"

    # ── 取消 ─────────────────────────────────────────────

    def cancel(self, pipeline_id: str = "") -> str:
        """取消流水线。"""
        from tools.task_dispatcher import _dispatcher, DispatchError
        try:
            return _dispatcher.cancel(pipeline_id=pipeline_id)
        except DispatchError as exc:
            return f"❌ {exc}"

    # ── 列出流水线 ───────────────────────────────────────

    def list_pipelines(self) -> str:
        """列出所有流水线。"""
        from tools.task_dispatcher import _dispatcher
        return _dispatcher.list_pipelines()

    # ── 多Agent系统健康检查 ──────────────────────────────

    def health(self) -> str:
        """多Agent系统全面健康检查。"""
        self._ensure_default_specialists()

        lines = [
            f"🏥 多智能体系统健康报告",
            f"{'='*55}",
            f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
        ]

        # Agent Manager
        try:
            from tools.agent_manager import _manager
            agents = _manager._agents
            total = len(agents)
            idle = sum(1 for a in agents.values() if a.status == "idle")
            busy = sum(1 for a in agents.values() if a.status == "busy")
            error = sum(1 for a in agents.values() if a.status == "error")
            offline = sum(1 for a in agents.values() if a.status == "offline")

            lines.append(f"🤖 Agent Manager: 🟢 正常")
            lines.append(f"   Agent总数: {total} | 🟢空闲:{idle} | 🟡忙碌:{busy} | "
                         f"🔴错误:{error} | ⚫离线:{offline}")
            lines.append("")
        except Exception as exc:
            lines.append(f"🤖 Agent Manager: 🔴 异常 ({exc})")
            lines.append("")

        # Message Bus
        try:
            from tools.message_bus import _bus
            queue_total = sum(len(q) for q in _bus._queues.values())
            history_count = len(_bus._history)
            sub_count = sum(len(subs) for subs in _bus._subscriptions.values())

            lines.append(f"📨 Message Bus: 🟢 正常")
            lines.append(f"   待处理消息: {queue_total} | 历史: {history_count} | "
                         f"订阅: {sub_count}")
            lines.append("")
        except Exception as exc:
            lines.append(f"📨 Message Bus: 🔴 异常 ({exc})")
            lines.append("")

        # Task Dispatcher
        try:
            from tools.task_dispatcher import _dispatcher
            pipelines = _dispatcher._pipelines
            active = sum(1 for p in pipelines.values()
                        if p.status in ("created", "running", "partial"))
            done = sum(1 for p in pipelines.values() if p.status == "done")
            failed = sum(1 for p in pipelines.values() if p.status == "failed")

            lines.append(f"🔧 Task Dispatcher: 🟢 正常")
            lines.append(f"   流水线: {len(pipelines)} 个 | 🔄活跃:{active} | "
                         f"✅完成:{done} | ❌失败:{failed}")
            lines.append("")
        except Exception as exc:
            lines.append(f"🔧 Task Dispatcher: 🔴 异常 ({exc})")
            lines.append("")

        # Specialist Registry
        try:
            from tools.specialist_base import SpecialistRegistry
            types = SpecialistRegistry.list_types()
            type_count = types.count("🔍") + types.count("📝") + types.count("📊") + \
                         types.count("🔒") + types.count("📈") + types.count("🎨")
            lines.append(f"🎭 Specialist 注册表: 🟢 正常")
            lines.append(f"   可用类型: researcher, writer, analyst, "
                         f"reviewer, monitor, designer, debugger")
            lines.append("")
        except Exception as exc:
            lines.append(f"🎭 Specialist 注册表: 🔴 异常 ({exc})")
            lines.append("")

        # Workflow Engine
        try:
            from tools.workflow_engine import WorkflowEngine
            lines.append(f"⚙️ Workflow Engine: 🟢 可用（独立模式）")
            lines.append("")
        except Exception:
            lines.append(f"⚙️ Workflow Engine: ⚠️ 未就绪")
            lines.append("")

        # 总体评估
        issues = []
        if total > 0 and idle == 0:
            issues.append("所有Agent都在忙碌")
        if error > 0:
            issues.append(f"{error}个Agent处于错误状态")

        if issues:
            lines.append(f"⚠️ 发现问题:")
            for issue in issues:
                lines.append(f"  • {issue}")
        else:
            lines.append(f"✅ 多智能体系统运行正常")

        return "\n".join(lines)

    # ── T050: 工作流-Specialist 集成 ─────────────────────

    def run_workflow(self, workflow_spec: str = "") -> str:
        """
        创建 Specialist 绑定工作流并执行。
        
        workflow_spec 格式:
        {
            "name": "工作流名称",
            "nodes": [
                {"name": "调研", "specialist": "researcher", "task": "..."},
                {"name": "设计", "specialist": "designer", "task": "...", "depends_on": ["调研"]},
                {"name": "实施", "specialist": "writer", "task": "...", "depends_on": ["设计"]},
                {"name": "审查", "specialist": "reviewer", "task": "...", "depends_on": ["实施"]}
            ]
        }
        """
        if not workflow_spec:
            raise OrchestratorError("请提供工作流规格 JSON")

        try:
            spec = json.loads(workflow_spec)
        except json.JSONDecodeError as exc:
            raise OrchestratorError(f"workflow_spec JSON 解析错误: {exc}")

        name = spec.get("name", "自定义工作流")
        nodes = spec.get("nodes", [])
        if not nodes:
            raise OrchestratorError("工作流至少需要一个节点")

        # 构建自定义子任务
        custom_subtasks = []
        name_to_id: dict[str, str] = {}

        for i, node in enumerate(nodes):
            node_name = node.get("name", f"节点{i+1}")
            sid = f"S{i+1}"
            name_to_id[node_name] = sid

            # 解析依赖
            deps = []
            for dep_name in node.get("depends_on", []):
                if dep_name in name_to_id:
                    deps.append(name_to_id[dep_name])

            custom_subtasks.append({
                "description": node.get("task", node_name),
                "capability": {
                    "researcher": "research", "writer": "writing",
                    "analyst": "analysis", "reviewer": "review",
                    "designer": "design", "monitor": "monitoring",
                    "debugger": "debugging",
                }.get(node.get("specialist", "researcher"), "research"),
                "agent": node.get("specialist", "researcher"),
                "depends_on": deps,
            })

        # 通过 Task Dispatcher 分解
        from tools.task_dispatcher import _dispatcher
        decompose_result = _dispatcher.decompose(
            task=name,
            custom_subtasks=json.dumps(custom_subtasks),
        )

        # 提取 pipeline_id
        pipeline_id = ""
        for line in decompose_result.split("\n"):
            if "流水线 [" in line:
                start = line.find("[") + 1
                end = line.find("]", start)
                pipeline_id = line[start:end]
                break

        # 调度
        dispatch_result = _dispatcher.dispatch_all(
            pipeline_id=pipeline_id,
            strategy="dag",
        )

        collect_result = _dispatcher.collect(pipeline_id=pipeline_id)

        # 格式化工作流可视化
        flow_lines = []
        for node in nodes:
            icon = {"researcher": "🔍", "writer": "📝", "analyst": "📊",
                    "reviewer": "🔒", "designer": "🎨", "monitor": "📈",
                    "debugger": "🐛"}.get(node.get("specialist", ""), "❓")
            deps = node.get("depends_on", [])
            dep_str = f" ← {' → '.join(deps)}" if deps else ""
            flow_lines.append(f"  {icon} [{node.get('name', '?')}] {node.get('specialist', '?')}{dep_str}")

        return (
            f"⚙️ Specialist 工作流编排完成\n"
            f"{'='*55}\n"
            f"📋 工作流: {name}\n"
            f"🔗 节点流:\n" + "\n".join(flow_lines) + "\n"
            f"\n── 分解结果 ──\n{decompose_result}\n"
            f"\n── 调度结果 ──\n{dispatch_result}\n"
            f"\n── 执行汇总 ──\n{collect_result}\n"
            f"\n💡 提示: orchestrator action=status pipeline_id={pipeline_id}"
        )

    # ── T051: Human-in-the-Loop ──────────────────────────

    def request_approval(
        self,
        pipeline_id: str = "",
        checkpoint_id: str = "",
    ) -> str:
        """
        请求人类批准关键节点。
        
        在流水线的关键检查点暂停，等待人类审批后继续。
        """
        if not pipeline_id:
            raise OrchestratorError("请指定流水线 ID")

        from tools.task_dispatcher import _dispatcher
        pipeline = _dispatcher._pipelines.get(pipeline_id)
        if not pipeline:
            return f"❌ 未找到流水线: {pipeline_id}"

        # 生成审批上下文
        pending = [s for s in pipeline.subtasks
                   if s.status in ("pending", "assigned")]
        done = [s for s in pipeline.subtasks if s.status == "done"]
        failed = [s for s in pipeline.subtasks if s.status == "failed"]

        return (
            f"👤 人类审批请求\n"
            f"{'='*55}\n"
            f"流水线: [{pipeline_id}] {pipeline.name[:60]}\n"
            f"检查点: {checkpoint_id or '默认检查点'}\n"
            f"状态: {pipeline.status}\n"
            f"\n📊 进度: ✅{len(done)} ⏳{len(pending)} ❌{len(failed)}/"
            f"{len(pipeline.subtasks)}\n"
            f"\n📋 已完成:\n" +
            "\n".join(f"  ✅ {s.description[:60]}" for s in done) +
            f"\n\n📋 待处理:\n" +
            "\n".join(f"  ⏳ {s.description[:60]} → {s.preferred_agent_type}"
                      for s in pending[:5]) +
            f"\n\n🔐 请审批后继续："
            f"\n  orchestrator action=provide_feedback pipeline_id={pipeline_id}"
            f" feedback='批准继续'"
            f"\n  orchestrator action=provide_feedback pipeline_id={pipeline_id}"
            f" feedback='需要修改：...'"
        )

    def provide_feedback(
        self,
        pipeline_id: str = "",
        feedback: str = "",
    ) -> str:
        """
        提供人类反馈。
        
        处理人类的审批意见或修改建议。
        """
        if not pipeline_id:
            raise OrchestratorError("请指定流水线 ID")
        if not feedback:
            raise OrchestratorError("请提供反馈内容")

        from tools.task_dispatcher import _dispatcher
        pipeline = _dispatcher._pipelines.get(pipeline_id)

        feedback_lower = feedback.lower()

        # 判断反馈类型
        if any(word in feedback_lower for word in ["批准", "approve", "继续", "ok", "同意", "通过"]):
            if pipeline:
                pending = [s for s in pipeline.subtasks
                           if s.status in ("pending", "assigned")]
                if pending:
                    dispatch_result = _dispatcher.dispatch_all(
                        pipeline_id=pipeline_id, strategy="dag",
                    )
                    return (
                        f"✅ 已批准，继续执行\n"
                        f"{'─'*40}\n"
                        f"流水线: [{pipeline_id}]\n"
                        f"{dispatch_result}"
                    )
                else:
                    collect_result = _dispatcher.collect(pipeline_id=pipeline_id)
                    return (
                        f"✅ 已批准 — 所有子任务已完成\n"
                        f"{'─'*40}\n"
                        f"{collect_result}"
                    )
            else:
                return (
                    f"✅ 已批准\n"
                    f"{'─'*40}\n"
                    f"流水线 [{pipeline_id}] 不存在或已完成。\n"
                    f"反馈已记录。"
                )

        elif any(word in feedback_lower for word in ["修改", "change", "调整", "改", "重做"]):
            if pipeline:
                return (
                    f"📝 收到修改建议\n"
                    f"{'─'*40}\n"
                    f"反馈: {feedback}\n"
                    f"\n💡 建议操作:\n"
                    f"  1. orchestrator action=retry pipeline_id={pipeline_id}"
                    f" (重试失败子任务)\n"
                    f"  2. 或重新编排: orchestrator action=run task='...'"
                )
            else:
                return f"📝 收到修改建议: {feedback}\n💡 流水线 [{pipeline_id}] 未找到。可重新编排。"

        elif any(word in feedback_lower for word in ["取消", "cancel", "停止", "stop"]):
            return self.cancel(pipeline_id=pipeline_id)

        else:
            # 记录一般反馈
            try:
                from tools.message_bus import _bus
                _bus.broadcast(
                    msg_type="notify",
                    content=json.dumps({
                        "event": "human_feedback",
                        "pipeline_id": pipeline_id,
                        "feedback": feedback,
                    }),
                    priority=8,
                )
            except Exception:
                pass

            return (
                f"📝 反馈已记录\n"
                f"{'─'*40}\n"
                f"流水线: [{pipeline_id}]\n"
                f"反馈: {feedback}\n"
                f"\n💡 反馈已广播给所有 Agent。"
                f"\n   使用 orchestrator action=status 查看当前状态。"
            )

    def escalate(self, issue: str = "", pipeline_id: str = "") -> str:
        """
        Agent 主动上报问题给人类。
        
        当 Agent 遇到无法自动处理的问题时调用。
        """
        if not issue:
            raise OrchestratorError("请描述要上报的问题")

        # 记录上报
        escalation_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "issue": issue,
            "pipeline_id": pipeline_id,
            "escalated_by": "Agent 1",
        }

        try:
            escalation_path = SANDBOX_DIR / "memory" / "escalations.json"
            existing = []
            if escalation_path.exists():
                existing = json.loads(escalation_path.read_text(encoding="utf-8"))
            existing.append(escalation_record)
            # 只保留最近100条
            existing = existing[-100:]
            escalation_path.parent.mkdir(parents=True, exist_ok=True)
            escalation_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        # 通过 Message Bus 通知
        try:
            from tools.message_bus import _bus
            _bus.broadcast(
                msg_type="error",
                content=json.dumps(escalation_record),
                priority=10,  # 最高优先级
            )
        except Exception:
            pass

        # 暂停相关流水线
        if pipeline_id:
            try:
                from tools.task_dispatcher import _dispatcher
                pipeline = _dispatcher._pipelines.get(pipeline_id)
                if pipeline:
                    pipeline.status = "partial"
                    _dispatcher._save()
            except Exception:
                pass

        return (
            f"🚨 问题已上报给人类\n"
            f"{'='*55}\n"
            f"⏰ 时间: {escalation_record['timestamp']}\n"
            f"📋 问题: {issue}\n"
            f"🔢 关联流水线: {pipeline_id or '无'}\n"
            f"👤 上报者: Agent 1\n"
            f"\n💡 人类可通过以下命令响应:\n"
            f"  orchestrator action=provide_feedback pipeline_id={pipeline_id}"
            f" feedback='...'\n"
            f"  orchestrator action=retry pipeline_id={pipeline_id}\n"
            f"  orchestrator action=cancel pipeline_id={pipeline_id}"
        )

    # ── 帮助 ─────────────────────────────────────────────

    def help(self) -> str:
        """Orchestrator 使用指南。"""
        return (
            "🎯 Orchestrator 使用指南\n"
            f"{'='*55}\n\n"
            "1️⃣ 一键运行流水线\n"
            "   orchestrator action=run task='开发一个文字冒险游戏'\n"
            "   orchestrator action=run task='写一篇关于AI的深度文章'\n"
            "   orchestrator action=run task='分析这份数据' template=data\n"
            "   orchestrator action=run task='...' stage_gate=true  ← 阶段门（分解后等审批）\n\n"
            "2️⃣ 查看进度\n"
            "   orchestrator action=status pipeline_id=PL_xxx\n"
            "   orchestrator action=list_pipelines\n\n"
            "3️⃣ 重试失败\n"
            "   orchestrator action=retry pipeline_id=PL_xxx\n"
            "   orchestrator action=retry pipeline_id=PL_xxx subtask_id=PL_xxx_S3\n\n"
            "4️⃣ 人类介入\n"
            "   orchestrator action=request_approval pipeline_id=PL_xxx\n"
            "   orchestrator action=provide_feedback pipeline_id=PL_xxx feedback='批准'\n"
            "   orchestrator action=escalate issue='遇到无法解决的问题'\n\n"
            "5️⃣ 工作流模式\n"
            "   orchestrator action=run_workflow workflow_spec='{\"name\":\"...\",\"nodes\":[...]}'\n\n"
            "6️⃣ 系统健康\n"
            "   orchestrator action=health\n\n"
            "📐 可用模板:\n"
            "   game    — Researcher → Designer → Writer → Reviewer\n"
            "   article — Researcher → Analyst → Writer → Reviewer\n"
            "   system  — Researcher → Designer → Reviewer\n"
            "   data    — Researcher → Analyst → Writer → Reviewer\n"
            "   通用    — Researcher → Designer → Writer → Reviewer\n\n"
            "💡 典型工作流:\n"
            "   1. orchestrator action=run task='...'  → 启动流水线\n"
            "   2. orchestrator action=status          → 查看进度\n"
            "   3. orchestrator action=retry if needed → 重试失败\n"
            "   4. orchestrator action=health          → 系统检查"
        )


# ── 全局实例 ──────────────────────────────────────────────

_orchestrator = Orchestrator()


def execute_orchestrator_tool(arguments: dict[str, Any]) -> str:
    """执行 orchestrator 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "run":
            return _orchestrator.run(
                task=arguments.get("task", ""),
                template=arguments.get("template", ""),
                strategy=arguments.get("strategy", "dag"),
                stage_gate=bool(arguments.get("stage_gate", False)),
            )

        elif action == "status":
            return _orchestrator.status(
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "retry":
            return _orchestrator.retry(
                pipeline_id=arguments.get("pipeline_id", ""),
                subtask_id=arguments.get("subtask_id", ""),
            )

        elif action == "cancel":
            return _orchestrator.cancel(
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "list_pipelines":
            return _orchestrator.list_pipelines()

        elif action == "health":
            return _orchestrator.health()

        elif action == "run_workflow":
            return _orchestrator.run_workflow(
                workflow_spec=arguments.get("workflow_spec", ""),
            )

        elif action == "request_approval":
            return _orchestrator.request_approval(
                pipeline_id=arguments.get("pipeline_id", ""),
                checkpoint_id=arguments.get("checkpoint_id", ""),
            )

        elif action == "provide_feedback":
            return _orchestrator.provide_feedback(
                pipeline_id=arguments.get("pipeline_id", ""),
                feedback=arguments.get("feedback", ""),
            )

        elif action == "escalate":
            return _orchestrator.escalate(
                issue=arguments.get("issue", ""),
                pipeline_id=arguments.get("pipeline_id", ""),
            )

        elif action == "help":
            return _orchestrator.help()

        else:
            return f"未知操作: {action}"

    except OrchestratorError as exc:
        return f"Orchestrator 错误: {exc}"
    except Exception as exc:
        return f"Orchestrator 执行异常: {type(exc).__name__}: {exc}"
