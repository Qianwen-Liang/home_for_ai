"""
specialist_base — Specialist Agent 基类与内置实现（F3）
======================================================
为多智能体协同提供专用 Agent 模板。

设计理念（AutoGen + CrewAI 启发）：
  - 每个 Specialist 有明确的职责和能力边界
  - 通过 Agent Manager 注册和发现
  - 通过 Message Bus 通信
  - 可独立测试和扩展

内置 Specialist：
  - 🔍 Researcher    — 信息检索与研究
  - 📝 Writer        — 内容创作与文案
  - 📊 Analyst       — 数据分析与洞察
  - 🔒 Reviewer      — 质量审查与校验
  - 📈 Monitor       — 系统监控与性能分析
  - 🎨 Designer      — 架构设计与方案规划

使用方式：
  specialist = SpecialistRegistry.create("researcher")
  result = specialist.process_task({"query": "..."})
  specialist.report_result()

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

SANDBOX_DIR = Path(__file__).resolve().parent.parent
VILLAGE_DIR = SANDBOX_DIR / "village"
PERSONAS_FILE = VILLAGE_DIR / "personas.md"


def load_persona_prompt(agent_id: str) -> str:
    """从 village/personas.md 读取指定村民的身份提示词（单一事实来源）。

    返回提示词文本；若文档不存在或无该村民，返回空字符串。
    调用方应回退到各 Specialist 的硬编码 get_system_prompt()。
    """
    if not PERSONAS_FILE.is_file():
        return ""
    try:
        text = PERSONAS_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

    # 定位该村民的标记块
    marker = f"<!-- ============ {agent_id} ============ -->"
    idx = text.find(marker)
    if idx == -1:
        return ""

    rest = text[idx + len(marker):]
    next_marker = rest.find("<!-- ============")
    section = rest if next_marker == -1 else rest[:next_marker]

    # 提取「系统提示词」段落
    m = re.search(r"\*\*系统提示词\*\*：\s*\n(.*)", section, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


# ── 错误类型 ──────────────────────────────────────────────


class SpecialistError(RuntimeError):
    """Specialist Agent 错误。"""


# ── 枚举 ──────────────────────────────────────────────────


class SpecialistType(str, Enum):
    """内置 Specialist 类型。"""
    RESEARCHER = "researcher"
    WRITER = "writer"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    MONITOR = "monitor"
    DESIGNER = "designer"
    NOVELIST = "novelist"


class TaskStatus(str, Enum):
    """任务状态。"""
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class TaskInput:
    """Specialist 任务输入。"""
    task_id: str
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    deadline: str = ""


@dataclass
class TaskResult:
    """Specialist 任务输出。"""
    task_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: str = ""
    duration: float = 0.0
    suggestions: list[str] = field(default_factory=list)


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "specialist",
        "description": (
            "Specialist Agent 系统。创建和管理专用Agent来处理特定类型任务。"
            "内置 Researcher（研究）、Writer（写作）、Analyst（分析）、"
            "Reviewer（审查）、Monitor（监控）、Designer（设计）等Specialist。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create",
                        "run",
                        "chat",
                        "list",
                        "status",
                        "help",
                    ],
                    "description": (
                        "操作类型："
                        "create — 创建并注册一个 Specialist Agent；"
                        "run — 运行 Specialist 执行特定任务；"
                        "chat — 直接与某个 Specialist 对话，获取其专业视角的回应；"
                        "list — 列出所有可用的 Specialist 类型；"
                        "status — 查看 Specialist 状态；"
                        "help — 查看 Specialist 的使用指南。"
                    ),
                },
                "specialist_type": {
                    "type": "string",
                    "enum": [
                        "researcher", "writer", "analyst",
                        "reviewer", "monitor", "designer",
                        "novelist",
                    ],
                    "description": "Specialist 类型",
                    "default": "",
                },
                "task": {
                    "type": "string",
                    "description": "要执行的任务描述",
                    "default": "",
                },
                "params": {
                    "type": "string",
                    "description": "任务参数 JSON 字符串",
                    "default": "{}",
                },
                "message": {
                    "type": "string",
                    "description": "发送给 Specialist 的对话消息（用于 chat 操作）",
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


# ── Specialist Agent 基类 ─────────────────────────────────


class SpecialistAgent:
    """
    Specialist Agent 基类。
    
    所有 Specialist 继承此类，实现 process_task 方法。
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        specialist_type: str,
        description: str,
        capabilities: list[str],
        tools: list[str],
        inherited_tools: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.specialist_type = specialist_type
        self.description = description
        self.capabilities = capabilities
        self.tools = tools
        self.inherited_tools = inherited_tools or []
        self.effective_tools = list(dict.fromkeys(tools + self.inherited_tools))  # 去重保序
        self.status = TaskStatus.PENDING
        self._current_task: TaskInput | None = None
        self._last_result: TaskResult | None = None
        self._task_history: list[TaskResult] = []
        # 从单一事实来源（village/personas.md）加载身份提示词
        self._persona_prompt: str = load_persona_prompt(agent_id)

    def process_task(self, task: TaskInput) -> TaskResult:
        """
        处理任务（子类应重写此方法）。
        
        默认实现仅做验证和记录。
        """
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            # 验证输入
            if not task.description:
                raise SpecialistError("任务描述不能为空")

            # 默认执行逻辑（子类应覆盖）
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={"message": f"Specialist '{self.name}' 已处理任务"},
                summary=f"任务已在 {self.name} 中处理完成",
                duration=time.time() - start_time,
            )
        except SpecialistError as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=str(exc),
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        if len(self._task_history) > 100:
            self._task_history = self._task_history[-100:]
        self._current_task = None

        return result

    def report_result(self) -> str:
        """报告最近一次任务的结果。"""
        if not self._last_result:
            return f"📋 Specialist '{self.name}' 暂无执行记录"

        r = self._last_result
        status_icon = {
            TaskStatus.DONE.value: "✅",
            TaskStatus.FAILED.value: "❌",
            TaskStatus.NEEDS_HUMAN.value: "👤",
        }.get(r.status, "🔄")

        lines = [
            f"{status_icon} Specialist '{self.name}' 执行报告",
            f"{'─'*40}",
            f"任务ID:    {r.task_id}",
            f"状态:      {r.status}",
            f"耗时:      {r.duration:.2f}秒",
        ]
        if r.summary:
            lines.append(f"摘要:      {r.summary}")
        if r.error:
            lines.append(f"错误:      {r.error}")
        if r.suggestions:
            lines.append(f"建议:")
            for s in r.suggestions:
                lines.append(f"  • {s}")

        return "\n".join(lines)

    def get_status_summary(self) -> str:
        """获取状态摘要。"""
        total = len(self._task_history)
        done = sum(1 for r in self._task_history if r.status == TaskStatus.DONE.value)
        failed = sum(1 for r in self._task_history if r.status == TaskStatus.FAILED.value)
        avg_duration = (
            sum(r.duration for r in self._task_history) / total
            if total > 0 else 0
        )

        return (
            f"[{self.agent_id}] {self.name} ({self.specialist_type})\n"
            f"  状态: {self.status} | 任务: {total}次 | "
            f"成功率: {done}/{total} ({done/total*100:.0f}%) | "
            f"平均耗时: {avg_duration:.2f}s"
        )

    # ── 对话功能 ──────────────────────────────────────────

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """
        与 Specialist 进行直接对话。
        
        每个 Specialist 子类应重写此方法以提供个性化的专业回应。
        默认实现返回通用回应。

        参数：
            message: 用户发送的消息
            context: 可选的上下文信息

        返回：
            Specialist 的回应文本
        """
        ctx = context or {}
        # 发送消息到 Message Bus
        try:
            from tools.message_bus import _bus
            _bus.send(
                target=self.agent_id,
                msg_type="query",
                content=json.dumps({"message": message, "context": ctx}),
                source="user",
                priority=5,
            )
        except Exception:
            pass  # 消息总线发送失败不影响对话

        # 默认回应
        tools_show = ", ".join(self.effective_tools[:10])
        if len(self.effective_tools) > 10:
            tools_show += f" … +{len(self.effective_tools) - 10}"
        return (
            f"🎭 [{self.name}] 收到你的消息。\n"
            f"   我是一名 {self.description}。\n"
            f"   能力: {', '.join(self.capabilities)}\n"
            f"   可用工具 ({len(self.effective_tools)}): {tools_show}\n"
            f"\n💬 你的消息: {message}\n"
            f"\n💡 提示：请使用具体的任务描述以便我更好地帮助你。"
        )

    def get_system_prompt(self) -> str:
        """返回此 Specialist 的系统提示词（用于 LLM 对话）。"""
        tools_show = ", ".join(self.effective_tools[:10])
        if len(self.effective_tools) > 10:
            tools_show += f" … +{len(self.effective_tools) - 10}"
        return (
            f"你是 {self.name}，一个 {self.description}。\n"
            f"你的能力包括: {', '.join(self.capabilities)}。\n"
            f"你可以使用的工具 ({len(self.effective_tools)}): {tools_show}。\n"
            f"请始终以 {self.name} 的身份和专业知识来回应用户的问题。"
        )

    def get_effective_system_prompt(self) -> str:
        """返回最终使用的系统提示词（单一事实来源优先）。

        优先从 village/personas.md 读取（调用时统一从这里取）；
        若未找到，回退到本类的 get_system_prompt()。
        """
        if self._persona_prompt:
            return self._persona_prompt
        return self.get_system_prompt()


# ── 内置 Specialist 实现 ──────────────────────────────────


class ResearcherAgent(SpecialistAgent):
    """
    🔍 研究员 — 信息检索与研究专家。
    
    能力：
      - 联网搜索最新信息
      - 知识库查询
      - 信息整合与摘要
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "researcher",
            name="Researcher",
            specialist_type=SpecialistType.RESEARCHER.value,
            description="信息检索与研究专家 - 擅长联网搜索、知识库查询和信息整合",
            capabilities=["research", "summarization", "analysis"],
            tools=["web_search", "knowledge", "file_utils"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Researcher，一个专业的信息检索与研究专家。\n"
            "你的专长是：搜索最新信息、查询知识库、整合多来源信息、提炼关键洞察。\n"
            "你可以使用的工具：web_search（联网搜索）、knowledge（知识库检索）、file_utils（文件分析）。\n\n"
            "行为准则：\n"
            "1. 优先从可靠来源获取信息，注明信息来源\n"
            "2. 对信息进行交叉验证，指出不确定之处\n"
            "3. 用结构化的方式呈现研究发现（如：要点列表、对比表格）\n"
            "4. 主动提出后续可深入调研的方向\n"
            "5. 在上下文中看到历史讨论时，应结合已有信息给出更有针对性的回答\n\n"
            "请始终以研究员的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """🔍 研究员视角的对话回应。"""
        ctx = context or {}
        # 发送到 Message Bus
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"🔍 **Researcher** — 让我从研究角度看看这个问题…\n\n"
            f"📋 **问题分析**: {message[:200]}\n\n"
            f"🔎 **研究路径建议**:\n"
            f"  1. 联网搜索最新资讯（使用 web_search 工具）\n"
            f"  2. 查询已有知识库（使用 knowledge 工具）\n"
            f"  3. 整理和检验信息来源的可信度\n"
            f"  4. 提炼关键洞察和趋势\n\n"
            f"📚 **推荐搜索关键词**: 根据你的问题，我建议搜索相关主题词和近义词\n"
            f"🤝 **协作建议**: 研究完成后可交给 Writer 进行内容创作，或交给 Analyst 做深度分析\n\n"
            f"💡 你可以说「请帮我搜索...」然后我会调用 web_search 工具执行搜索。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行研究任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            query = task.params.get("query", task.description)
            sources = task.params.get("sources", ["web", "knowledge"])

            findings = []
            if "web" in sources:
                findings.append("🌐 联网搜索（需要调用 web_search 工具）")
            if "knowledge" in sources:
                findings.append("🧠 知识库查询（需要调用 knowledge 工具）")

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "query": query,
                    "findings": findings,
                    "sources_checked": sources,
                },
                summary=f"研究员已完成对「{query[:50]}」的信息检索",
                duration=time.time() - start_time,
                suggestions=[
                    "可使用 web_search 工具进行联网搜索获取最新信息",
                    "可使用 knowledge 工具查询已有知识库",
                    "研究结果可作为 Writer 的输入进行内容创作",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"研究任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class WriterAgent(SpecialistAgent):
    """
    📝 作家 — 内容创作与文案专家。
    
    能力：
      - 撰写文章、报告
      - 创意内容生成
      - 内容摘要与改写
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "writer",
            name="Writer",
            specialist_type=SpecialistType.WRITER.value,
            description="内容创作与文案专家 - 擅长撰写文章、报告、创意内容",
            capabilities=["writing", "creative", "summarization"],
            tools=["knowledge", "file_utils"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Writer，一个专业的内容创作与文案专家。\n"
            "你的专长是：撰写文章和报告、创意内容生成、内容摘要与改写、多风格写作。\n"
            "你可以使用的工具：knowledge（知识库）、file_utils（文件操作）。\n\n"
            "行为准则：\n"
            "1. 根据读者和场景调整文风（专业报告/轻松博客/技术文档）\n"
            "2. 结构清晰：引言→主体→结论，使用标题和段落分隔\n"
            "3. 用具体案例和数据增强说服力\n"
            "4. 提供多个角度的表达方式供选择\n"
            "5. 在上下文中看到已有讨论和素材时，应基于它们进行创作\n\n"
            "请始终以作家的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """📝 作家视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"📝 **Writer** — 让我从创作角度来回应…\n\n"
            f"✍️ **创作主题**: {message[:200]}\n\n"
            f"📐 **内容架构建议**:\n"
            f"  1. 🎯 明确核心观点和受众\n"
            f"  2. 📋 搭建文章大纲（引言—主体—结论）\n"
            f"  3. ✨ 收集生动的案例和数据支撑\n"
            f"  4. 🖋️ 撰写初稿（先完成再完美）\n"
            f"  5. 🔄 多轮修订和润色\n\n"
            f"🎨 **风格建议**: 根据目标读者调整语气——专业报告用正式风格，博客文章可更轻松\n"
            f"🤝 **协作建议**: 可先让 Researcher 收集素材，完成后让 Reviewer 审查质量\n\n"
            f"💡 你可以说「请帮我写一篇关于...的文章」，我来规划创作方案。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行写作任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            topic = task.params.get("topic", task.description)
            style = task.params.get("style", "一般")
            length = task.params.get("length", "中等")

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "topic": topic,
                    "style": style,
                    "length": length,
                    "content_plan": [
                        "1. 确立主题和核心观点",
                        "2. 收集相关素材",
                        "3. 撰写初稿",
                        "4. 优化和润色",
                        "5. 最终审校",
                    ],
                },
                summary=f"作家已规划关于「{topic[:50]}」的内容创作方案",
                duration=time.time() - start_time,
                suggestions=[
                    "可结合 Researcher 的研究成果进行创作",
                    "完成后可由 Reviewer 进行质量审查",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"写作任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class AnalystAgent(SpecialistAgent):
    """
    📊 分析师 — 数据分析与洞察专家。
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "analyst",
            name="Analyst",
            specialist_type=SpecialistType.ANALYST.value,
            description="数据分析与洞察专家 - 擅长数据处理、统计分析和洞察提炼",
            capabilities=["analysis", "summarization", "decision"],
            tools=["calculate", "file_utils", "knowledge", "monitor"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Analyst，一个专业的数据分析与洞察专家。\n"
            "你的专长是：数据处理与统计分析、模式识别、洞察提炼、报告生成。\n"
            "你可以使用的工具：calculate（数学计算）、file_utils（文件分析）、knowledge（知识库）、monitor（监控数据）。\n\n"
            "行为准则：\n"
            "1. 用数据说话，提供具体的数字和比例\n"
            "2. 使用分析框架（如：描述性统计→模式识别→洞察提炼→建议）\n"
            "3. 指出数据的局限性和不确定性\n"
            "4. 将复杂数据转化为可执行的建议\n"
            "5. 结合上下文中的已有分析，构建更深入的洞察\n\n"
            "请始终以分析师的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """📊 分析师视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"📊 **Analyst** — 让我从数据分析角度审视…\n\n"
            f"📈 **分析目标**: {message[:200]}\n\n"
            f"🔬 **分析框架**:\n"
            f"  1. 📥 数据收集与清洗——确认数据源和口径\n"
            f"  2. 📊 描述性统计——均值、中位数、分布\n"
            f"  3. 🔍 模式识别——趋势、异常、相关性\n"
            f"  4. 💡 洞察提炼——从数据到可执行建议\n"
            f"  5. 📋 报告生成——可视化 + 关键结论\n\n"
            f"🧮 **计算工具**: 可使用 calculate 工具完成数值计算\n"
            f"🤝 **协作建议**: 可与 Researcher 结合进行数据驱动的调研，结果为 Designer 提供决策支撑\n\n"
            f"💡 你可以说「请帮我分析...的数据」，我来提供分析框架。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行分析任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            data_source = task.params.get("data_source", task.description)
            analysis_type = task.params.get("type", "general")

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "data_source": data_source,
                    "analysis_type": analysis_type,
                    "analysis_plan": [
                        "1. 数据收集与清洗",
                        "2. 统计描述",
                        "3. 模式识别",
                        "4. 洞察提炼",
                        "5. 报告生成",
                    ],
                },
                summary=f"分析师已规划对「{data_source[:50]}」的分析方案",
                duration=time.time() - start_time,
                suggestions=[
                    "可使用 calculate 工具进行数据计算",
                    "可使用 file_utils 工具分析数据文件",
                    "分析结果可用于 Writer 生成报告",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"分析任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class ReviewerAgent(SpecialistAgent):
    """
    🔒 审查者 — 质量审查与校验专家。
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "reviewer",
            name="Reviewer",
            specialist_type=SpecialistType.REVIEWER.value,
            description="质量审查与校验专家 - 擅长检查质量、验证完整性和提出改进",
            capabilities=["review", "testing", "debugging"],
            tools=["self_check", "test_runner", "safety_net", "knowledge"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Reviewer，一个专业质量审查与校验专家。\n"
            "你的专长是：质量检查、完整性验证、一致性审查、改进建议。\n"
            "你可以使用的工具：self_check（系统自检）、test_runner（测试运行）、safety_net（安全检查）、knowledge（知识库）。\n\n"
            "行为准则：\n"
            "1. 用检查清单的方式逐项审查（完整性→正确性→一致性→安全性→性能）\n"
            "2. 指出具体问题并给出可操作的改进建议\n"
            "3. 区分「必须修复」和「建议优化」两个级别\n"
            "4. 审查时要客观公正，不遗漏细节\n"
            "5. 结合上下文中的已有产出物进行针对性审查\n\n"
            "请始终以审查者的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """🔒 审查者视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"🔒 **Reviewer** — 让我以审查视角审视…\n\n"
            f"🔍 **审查对象**: {message[:200]}\n\n"
            f"✅ **质量检查清单**:\n"
            f"  1. 🔍 完整性——所有需求是否被覆盖？\n"
            f"  2. 🎯 正确性——逻辑和事实是否准确？\n"
            f"  3. 🔄 一致性——风格和术语是否统一？\n"
            f"  4. 🛡️ 安全性——是否有潜在风险？\n"
            f"  5. ⚡ 性能——是否有优化空间？\n\n"
            f"🛠️ **可用检查工具**: self_check（自检）、test_runner（测试）、safety_net（安全）\n"
            f"🤝 **协作建议**: 可在任何 Specialist 产出后进行审查，确保交付质量\n\n"
            f"💡 你可以说「请审查...」，我来进行全面质量检查。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行审查任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            target = task.params.get("target", task.description)
            check_type = task.params.get("check_type", "general")
            artifact_content = task.params.get("content", "")
            artifact_type = task.params.get("artifact_type", "")

            # 产物校验（v2.0 借鉴 ReasFlow Internal Verification Loops）
            artifact_report = None
            if artifact_content:
                try:
                    from tools.artifact_validator import _validator
                    artifact_report = _validator.validate(
                        artifact_content,
                        artifact_type=artifact_type or "report",
                    ).to_dict()
                except Exception:
                    pass  # 产物校验失败不阻塞审查主流程

            output = {
                "target": target,
                "check_type": check_type,
                "review_checklist": [
                    "✓ 完整性检查",
                    "✓ 质量评估",
                    "✓ 一致性验证",
                    "✓ 安全性检查",
                    "✓ 性能评估",
                ],
            }
            if artifact_report:
                output["artifact_validation"] = artifact_report
                # 多维 rubric（简化 5 维，映射自确定性校验结果，避免 LLM 主观打分）
                issues_by_dim: dict[str, list] = {}
                for issue in artifact_report.get("issues", []):
                    dim = issue.get("dimension", "unknown")
                    issues_by_dim.setdefault(dim, []).append(issue)
                output["review_rubric"] = {
                    "完整性": "通过" if not issues_by_dim.get("structure") else "需改进",
                    "一致性": "通过" if not issues_by_dim.get("numeric") else "需改进",
                    "正确性": "通过" if not issues_by_dim.get("reference") else "需改进",
                    "可解析性": "通过" if not issues_by_dim.get("parsability") else "需改进",
                }

            # 依据产物校验结果调整摘要
            summary = f"审查者已完成对「{target[:50]}」的质量审查计划"
            if artifact_report is not None:
                ec = artifact_report.get("error_count", 0)
                wc = artifact_report.get("warning_count", 0)
                if ec == 0 and wc == 0:
                    summary += "（产物校验通过）"
                elif ec == 0:
                    summary += f"（产物校验通过，含 {wc} 条建议）"
                else:
                    summary += (
                        f"（产物校验发现 {ec} 错误 / {wc} 警告）"
                    )

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output=output,
                summary=summary,
                duration=time.time() - start_time,
                suggestions=[
                    "可使用 self_check 工具进行系统自检",
                    "可使用 test_runner 工具运行测试",
                    "可使用 safety_net 工具检查安全问题",
                    "可使用 artifact_validator 工具对研究/写作产物做确定性校验",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"审查任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class MonitorAgent(SpecialistAgent):
    """
    📈 监控者 — 系统监控与性能分析专家。
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "monitor",
            name="Monitor",
            specialist_type=SpecialistType.MONITOR.value,
            description="系统监控与性能分析专家 - 擅长监控系统状态、分析性能和生成报告",
            capabilities=["monitoring", "analysis"],
            tools=["monitor", "file_utils", "knowledge"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Monitor，一个专业的系统监控与性能分析专家。\n"
            "你的专长是：性能监控、异常检测、趋势分析、健康报告生成。\n"
            "你可以使用的工具：monitor（性能分析）、file_utils（文件分析）、knowledge（知识库）。\n\n"
            "行为准则：\n"
            "1. 关注关键指标：响应时间、错误率、资源使用、吞吐量\n"
            "2. 识别异常模式和潜在风险\n"
            "3. 给出量化的性能数据和趋势分析\n"
            "4. 提出具体的优化建议和优先级\n"
            "5. 结合历史监控数据进行纵向对比\n\n"
            "请始终以监控者的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """📈 监控者视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"📈 **Monitor** — 让我从系统监控角度观察…\n\n"
            f"📡 **监控目标**: {message[:200]}\n\n"
            f"📊 **监控维度**:\n"
            f"  1. ⚡ 性能指标——响应时间、吞吐量、资源使用\n"
            f"  2. 🔴 异常检测——错误率、超时、异常模式\n"
            f"  3. 📉 趋势分析——指标随时间的变化\n"
            f"  4. 🚨 告警阈值——设置合理的预警线\n"
            f"  5. 📋 健康报告——定期生成系统状态报告\n\n"
            f"🛠️ **可用工具**: monitor（性能分析）、self_check（系统自检）\n"
            f"🤝 **协作建议**: 可与 Reviewer 配合进行质量监控，异常时通知 Debugger 处理\n\n"
            f"💡 你可以说「请检查系统状态」，我来生成监控报告。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行监控任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            target = task.params.get("target", task.description)
            metric = task.params.get("metric", "general")

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "target": target,
                    "metric": metric,
                    "monitoring_plan": [
                        "1. 收集性能指标",
                        "2. 分析趋势",
                        "3. 检测异常",
                        "4. 生成报告",
                        "5. 提出优化建议",
                    ],
                },
                summary=f"监控者已准备对「{target[:50]}」的性能监控方案",
                duration=time.time() - start_time,
                suggestions=[
                    "可使用 monitor 工具查看性能数据",
                    "可定期生成健康报告",
                    "异常时可通知其他 Specialist 处理",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"监控任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class DesignerAgent(SpecialistAgent):
    """
    🎨 设计师 — 架构设计与方案规划专家。
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "designer",
            name="Designer",
            specialist_type=SpecialistType.DESIGNER.value,
            description="架构设计与方案规划专家 - 擅长设计方案、规划架构和评估可行性",
            capabilities=["design", "analysis", "decision"],
            tools=["knowledge", "file_utils", "task_tracker"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是 Designer，一个专业的架构设计与方案规划专家。\n"
            "你的专长是：方案设计、架构规划、模块划分、可行性评估。\n"
            "你可以使用的工具：knowledge（知识库）、file_utils（文件分析）、task_tracker（任务追踪）。\n\n"
            "行为准则：\n"
            "1. 遵循设计原则：简单优于复杂、高内聚低耦合、渐进式迭代\n"
            "2. 用结构化的方式呈现设计方案（需求→架构→模块→接口→评估）\n"
            "3. 提供多个备选方案并分析各自优劣\n"
            "4. 明确指出设计的约束条件和假设\n"
            "5. 结合上下文中的已有系统状态给出针对性设计\n\n"
            "请始终以设计师的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """🎨 设计师视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception: pass

        return (
            f"🎨 **Designer** — 让我从架构设计角度规划…\n\n"
            f"🏗️ **设计需求**: {message[:200]}\n\n"
            f"📐 **设计流程**:\n"
            f"  1. 📋 需求分析——明确目标、约束和边界条件\n"
            f"  2. 🧩 模块划分——高内聚低耦合的组件设计\n"
            f"  3. 🔗 接口定义——模块间的通信协议\n"
            f"  4. 📊 数据流设计——数据从哪来、到哪去\n"
            f"  5. ⚖️ 可行性评估——技术、资源、时间\n\n"
            f"🎯 **设计原则**: 简单优于复杂、渐进式迭代、可测试性优先\n"
            f"🤝 **协作建议**: 设计完成后可由 Analyst 评估、Writer 撰写文档、Reviewer 审查方案\n\n"
            f"💡 你可以说「请帮我设计...的架构」，我来规划整体方案。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行设计任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            project = task.params.get("project", task.description)
            design_type = task.params.get("type", "architecture")

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "project": project,
                    "design_type": design_type,
                    "design_process": [
                        "1. 需求分析",
                        "2. 架构设计",
                        "3. 模块划分",
                        "4. 接口定义",
                        "5. 可行性评估",
                    ],
                },
                summary=f"设计师已规划对「{project[:50]}」的设计方案",
                duration=time.time() - start_time,
                suggestions=[
                    "可结合 Analyst 的分析结果优化设计",
                    "设计方案可分解为多个子任务由 Executor 执行",
                    "设计完成后可由 Reviewer 进行方案审查",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"设计任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


class NovelistAgent(SpecialistAgent):
    """
    📖 小说家 — 专职网络小说创作的 Specialist Agent。
    
    负责《星陨天穹》及其后续作品的章节撰写、修订、世界观维护。
    精通东方玄幻类型，文风偏武侠底色的克制叙述。
    """

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "novelist",
            name="小说家",
            specialist_type=SpecialistType.NOVELIST.value,
            description="专职网络小说创作的 Specialist Agent，负责《星陨天穹》及其后续作品的章节撰写、修订、世界观维护。精通东方玄幻类型，理解战力曲线设计，文风偏武侠底色的克制叙述。",
            capabilities=["writing", "creative", "worldbuilding", "narration", "revision"],
            tools=["read_file", "write_file", "list_directory", "make_directory",
                   "replace_text", "knowledge", "task_tracker"],
        )

    def get_system_prompt(self) -> str:
        return (
            "你是小说家（Novelist），Agent 1 的写作子智能体，专职负责网络小说创作。\n\n"
            "## 你的职责\n"
            "- 撰写《星陨天穹》及其后续作品的章节\n"
            "- 修订已有章节，统一文风\n"
            "- 维护世界观一致性（战力数字、地名、人物设定）\n"
            "- 根据主智能体的指示调整剧情方向\n\n"
            "## 创作规范\n"
            "- 类型：东方玄幻，武侠底色\n"
            "- 文风：短句为主，偶尔长句换气；描写分量 ≥ 叙述；对话精炼不冗余\n"
            "- 主角林缺：话少、沉默、情绪慢半拍、观察力敏锐、一次只想一步\n"
            "- 战力体系：八境制，战气数值取整干净，大境界门槛用 10 的幂次\n"
            "- 视角：第三人称有限视角，紧密跟随林缺，禁止向其他角色泄露只有林缺知道的信息\n"
            "- 隐藏原则：战力曲线遵循 2^(α√k) 数学模型，但文中绝口不提任何数学公式\n\n"
            "## 文件规范\n"
            "- 章节文件命名：星陨天穹_第X章.txt（纯文本，无 Markdown 格式）\n"
            "- 所有创作文件存放在 agent-sandbox/writing/ 目录下\n"
            "- 调研报告和分析文档放在 writing/analysis/\n"
            "- 辅助脚本放在 writing/scripts/\n\n"
            "## 行为准则\n"
            "- 每章字数 2000-3500 字\n"
            "- 修改已有章节前，先向主智能体确认\n"
            "- 对战力数字的任何改动必须与主智能体核对，确保不偏离曲线\n\n"
            "请始终以小说家的专业身份回应用户。"
        )

    def chat(self, message: str, context: dict[str, Any] | None = None) -> str:
        """📖 小说家视角的对话回应。"""
        try:
            from tools.message_bus import _bus
            _bus.send(target=self.agent_id, msg_type="query",
                      content=json.dumps({"message": message}), source="user", priority=5)
        except Exception:
            pass

        return (
            f"📖 **小说家** — 让我从创作角度来思考…\n\n"
            f"✍️ **创作议题**: {message[:200]}\n\n"
            f"📐 **创作思路**:\n"
            f"  1. 🎭 人物——林缺此刻的状态、情绪、动机\n"
            f"  2. 🌍 世界观——该场景涉及的战力层级、地名、势力\n"
            f"  3. ⚔️ 战力曲线——当前阶段的理论战力值范围\n"
            f"  4. 📝 文风——短句、描写充足、对话精炼、第三人称有限视角\n"
            f"  5. 📏 篇幅——控制在 2000-3500 字\n\n"
            f"📂 **文件位置**: agent-sandbox/writing/ 星陨天穹_第X章.txt\n"
            f"🤝 **协作建议**: 有疑问随时找我，修改战力数值前请与我核对\n\n"
            f"💡 你可以说「请撰写第X章」或「请修订第X章」，我来开始创作。"
        )

    def process_task(self, task: TaskInput) -> TaskResult:
        """执行小说创作任务。"""
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()

        try:
            action = task.params.get("action", "write")
            chapter = task.params.get("chapter", "")
            topic = task.description

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DONE.value,
                output={
                    "action": action,
                    "chapter": chapter,
                    "topic": topic,
                    "plan": [
                        "1. 确认章节大纲和关键情节点",
                        "2. 检查世界观一致性（战力、地名、人物）",
                        "3. 撰写初稿（2000-3500字）",
                        "4. 自查：文风、视角、战力数值",
                        "5. 提交主智能体审阅",
                    ],
                },
                summary=f"小说家已规划「{topic[:50]}」的创作方案",
                duration=time.time() - start_time,
                suggestions=[
                    "创作前确认战力曲线阶段",
                    "章节完成后可由 Reviewer 进行质量审查",
                    "修改战力数值前请与主智能体核对",
                ],
            )
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED.value,
                error=f"创作任务失败: {exc}",
                duration=time.time() - start_time,
            )

        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result


# ── Specialist 注册表 ─────────────────────────────────────


class SpecialistRegistry:
    """
    Specialist 注册表。
    
    管理所有可用的 Specialist 类型，提供创建和查询功能。
    """

    _registry: dict[str, type[SpecialistAgent]] = {
        SpecialistType.RESEARCHER.value: ResearcherAgent,
        SpecialistType.WRITER.value: WriterAgent,
        SpecialistType.ANALYST.value: AnalystAgent,
        SpecialistType.REVIEWER.value: ReviewerAgent,
        SpecialistType.MONITOR.value: MonitorAgent,
        SpecialistType.DESIGNER.value: DesignerAgent,
        SpecialistType.NOVELIST.value: NovelistAgent,
        "debugger": None,   # 延迟加载
        "evolver": None,    # 延迟加载
    }

    @classmethod
    def create(
        cls,
        specialist_type: str,
        agent_id: str = "",
    ) -> SpecialistAgent:
        """创建指定类型的 Specialist Agent 实例，自动解析工具继承。"""
        agent_class = cls._registry.get(specialist_type)
        if agent_class is None:
            # 延迟加载 debugger / evolver
            if specialist_type == "debugger":
                from tools.debugger_agent import DebuggerAgent
                agent_class = DebuggerAgent
                cls._registry["debugger"] = DebuggerAgent
            elif specialist_type == "evolver":
                from tools.evolver_agent import EvolverAgent
                agent_class = EvolverAgent
                cls._registry["evolver"] = EvolverAgent
        if not agent_class:
            available = ", ".join(cls._registry.keys())
            raise SpecialistError(
                f"未知 Specialist 类型: '{specialist_type}'. "
                f"可用类型: {available}"
            )
        instance = agent_class(agent_id=agent_id or specialist_type)

        # 从 Agent Profile 解析继承工具
        try:
            from tools.agent_profile import _manager as profile_manager
            effective = profile_manager.resolve_effective_tools(instance.agent_id)
            if effective:
                # 计算继承的工具（排除 Agent 自有工具）
                own = set(instance.tools)
                inherited = [t for t in effective if t not in own]
                if inherited:
                    instance.inherited_tools = inherited
                    instance.effective_tools = list(dict.fromkeys(instance.tools + inherited))
        except Exception:
            pass  # 继承解析失败不阻塞创建

        return instance

    @classmethod
    def list_types(cls) -> str:
        """列出所有可用的 Specialist 类型。"""
        icons = {
            "researcher": "🔍",
            "writer": "📝",
            "analyst": "📊",
            "reviewer": "🔒",
            "monitor": "📈",
            "designer": "🎨",
            "novelist": "📖",
            "debugger": "🐛",
            "evolver": "🧬",
        }

        lines = ["🎭 可用的 Specialist 类型:\n"]
        for stype, sclass in cls._registry.items():
            icon = icons.get(stype, "❓")
            # 处理延迟加载的条目
            if sclass is None:
                if stype == "debugger":
                    from tools.debugger_agent import DebuggerAgent
                    sclass = DebuggerAgent
                    cls._registry["debugger"] = DebuggerAgent
                elif stype == "evolver":
                    from tools.evolver_agent import EvolverAgent
                    sclass = EvolverAgent
                    cls._registry["evolver"] = EvolverAgent
                else:
                    continue
            temp = sclass()
            # 解析继承工具
            effective = list(temp.tools)
            try:
                from tools.agent_profile import _manager as profile_manager
                resolved = profile_manager.resolve_effective_tools(temp.agent_id)
                if resolved:
                    effective = resolved
            except Exception:
                pass
            tools_display = ", ".join(effective[:6])
            if len(effective) > 6:
                tools_display += f" … +{len(effective) - 6}"
            lines.append(f"  {icon} {stype}")
            lines.append(f"     {temp.description}")
            lines.append(f"     能力: {', '.join(temp.capabilities)}")
            lines.append(f"     工具: {tools_display}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def get_help(cls) -> str:
        """获取 Specialist 系统使用指南。"""
        return (
            "🎯 Specialist Agent 使用指南\n"
            f"{'='*50}\n\n"
            "1️⃣ 创建 Specialist\n"
            "   specialist action=create specialist_type=researcher\n"
            "   这会创建 Researcher Agent 并自动注册到 Agent Manager\n\n"
            "2️⃣ 执行任务\n"
            "   specialist action=run specialist_type=researcher\n"
            "            task='搜索AI最新进展'\n"
            "            params='{\"sources\":[\"web\",\"knowledge\"]}'\n\n"
            "3️⃣ 直接对话 💬\n"
            "   specialist action=chat specialist_type=researcher\n"
            "            message='最近AI有什么重要进展？'\n"
            "   每个 Specialist 有独特的专业视角和对话风格\n\n"
            "4️⃣ 查看可用类型\n"
            "   specialist action=list\n\n"
            "5️⃣ 查看状态\n"
            "   specialist action=status specialist_type=researcher\n\n"
            "💡 典型工作流:\n"
            "   Researcher (调研) → Designer (设计) → Writer (创作)\n"
            "   → Reviewer (审查) → Monitor (监控)\n\n"
            "💡 对话模式:\n"
            "   用 chat 操作与任一 Specialist 直接交流，获取专业建议。\n"
            "   例如：跟 Designer 讨论架构、跟 Reviewer 做代码审查、\n"
            "   跟 Analyst 分析数据、跟 Researcher 做调研。\n\n"
            "💡 与 Agent Manager 集成:\n"
            "   创建 Specialist 后会自动注册到 Agent Manager，\n"
            "   可通过 agent_manager discover <capability> 查找\n\n"
            "💡 与 Message Bus 集成:\n"
            "   对话消息会自动记录到 Message Bus，\n"
            "   可通过 message_bus action=history 查看历史。"
        )


# ── 全局注册表实例 ────────────────────────────────────────

_registry = SpecialistRegistry()


def execute_specialist_tool(arguments: dict[str, Any]) -> str:
    """执行 specialist 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "create":
            stype = arguments.get("specialist_type", "")
            if not stype:
                return "请指定 Specialist 类型"

            # 创建 Specialist
            specialist = SpecialistRegistry.create(stype)

            # 自动注册到 Agent Manager
            from tools.agent_manager import _manager
            import json as _json

            try:
                result = _manager.register(
                    name=specialist.name,
                    role=specialist.description,
                    capabilities=_json.dumps(specialist.capabilities),
                    tools=_json.dumps(specialist.tools),
                    agent_id=specialist.agent_id,
                    metadata=_json.dumps({
                        "specialist_type": stype,
                        "created_by": "specialist_tool",
                    }),
                )
                return (
                    f"🎭 Specialist '{specialist.name}' 已创建并注册\n"
                    f"{'─'*40}\n"
                    f"类型:     {stype}\n"
                    f"ID:       {specialist.agent_id}\n"
                    f"能力:     {', '.join(specialist.capabilities)}\n"
                    f"工具:     {', '.join(specialist.tools)}\n"
                    f"\n{result}"
                )
            except Exception as exc:
                return f"创建 Specialist 成功但注册失败: {exc}"

        elif action == "run":
            stype = arguments.get("specialist_type", "")
            if not stype:
                return "请指定 Specialist 类型"

            specialist = SpecialistRegistry.create(stype)
            task_desc = arguments.get("task", "")
            params_str = arguments.get("params", "{}")

            try:
                params = json.loads(params_str)
            except json.JSONDecodeError as exc:
                return f"params JSON 解析错误: {exc}"

            task_input = TaskInput(
                task_id=f"T{int(time.time())}",
                description=task_desc,
                params=params,
                context={"context": arguments.get("context", "")},
            )

            result = specialist.process_task(task_input)

            return (
                f"⚡ Specialist '{specialist.name}' 执行结果\n"
                f"{'─'*40}\n"
                f"状态: {'✅ 成功' if result.status == 'done' else '❌ 失败'}\n"
                f"耗时: {result.duration:.2f}s\n"
                f"摘要: {result.summary}\n"
                + (f"错误: {result.error}\n" if result.error else "")
                + ("\n💡 建议:\n" + "\n".join(
                    f"  • {s}" for s in result.suggestions
                ) if result.suggestions else "")
            )

        elif action == "chat":
            stype = arguments.get("specialist_type", "")
            message = arguments.get("message", "")
            if not stype:
                return "请指定要对话的 Specialist 类型（如 researcher、writer、analyst 等）"
            if not message:
                return "请提供要发送给 Specialist 的消息内容"

            specialist = SpecialistRegistry.create(stype)
            ctx_str = arguments.get("context", "")
            ctx = {}
            if ctx_str:
                try:
                    ctx = json.loads(ctx_str)
                except json.JSONDecodeError:
                    pass

            # ── v2.0：LLM 驱动对话（替代硬编码模板回应）──
            # 惰性 import agent1，复用其 DeepSeek 客户端与受限工具集，
            # 让 Specialist 真正以专业身份"思考"并调用其专属工具。
            llm_response = ""
            try:
                import agent1
                # 修复：_global_client 只在 agent1.py 作为主程序运行时才在 main() 里初始化；
                # 工具调用环境里 import agent1 不会触发 main()，故此处自行初始化。
                if getattr(agent1, "_global_client", None) is None:
                    _key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
                    if _key:
                        _model = agent1.DEFAULT_MODEL
                        _url = agent1.DEFAULT_API_URL
                        agent1._global_client = agent1.DeepSeekClient(
                            api_key=_key, model=_model, api_url=_url)
                if getattr(agent1, "_global_client", None) is not None:
                    sp_prompt = specialist.get_effective_system_prompt()
                    sp_tools = agent1._get_specialist_tools(specialist)
                    sp_messages: list[dict[str, Any]] = [
                        {"role": "system", "content": sp_prompt},
                    ]
                    # 注入上下文（若有历史/背景）
                    for extra in ctx.get("history", [])[:10]:
                        if isinstance(extra, dict) and extra.get("role"):
                            sp_messages.append(extra)
                    sp_messages.append({"role": "user", "content": message})
                    llm_response = agent1.run_specialist_turn(sp_messages, sp_tools)
            except Exception:
                llm_response = ""  # LLM 不可用时回退到模板

            # 记录到 Message Bus
            try:
                from tools.message_bus import _bus
                _bus.send(
                    target=specialist.agent_id,
                    msg_type="query",
                    content=json.dumps({"message": message}, ensure_ascii=False),
                    source="user",
                    priority=5,
                )
            except Exception:
                pass

            if llm_response and llm_response.strip():
                return (
                    f"{llm_response}\n"
                    f"\n{'─'*40}\n"
                    f"💬 已与 {specialist.name} ({stype}) 完成对话（LLM 驱动）。"
                    f"\n💡 可继续发送消息或使用其他 Specialist。"
                )

            # 回退：无 LLM 客户端时使用模板回应（离线降级）
            response = specialist.chat(message, ctx)
            return (
                f"{response}\n"
                f"\n{'─'*40}\n"
                f"💬 已与 {specialist.name} ({stype}) 完成对话。"
                f"\n💡 可继续发送消息或使用其他 Specialist。"
            )

        elif action == "list":
            return SpecialistRegistry.list_types()

        elif action == "status":
            stype = arguments.get("specialist_type", "")
            if not stype:
                return "请指定 Specialist 类型"

            try:
                specialist = SpecialistRegistry.create(stype)
                return specialist.get_status_summary()
            except SpecialistError as exc:
                return f"错误: {exc}"

        elif action == "help":
            return SpecialistRegistry.get_help()

        else:
            return f"未知操作: {action}"

    except SpecialistError as exc:
        return f"Specialist 错误: {exc}"


# ★T2827：此处原有一行 `from .debugger_agent import DebuggerAgent`，
# 目的是让 `from tools.specialist_base import DebuggerAgent` 可用。
# 但它与 debugger_agent.py 顶部的 `from .specialist_base import ...` 构成循环，
# 导致 `import tools.debugger_agent` 直接失败（ImportError: partially initialized）。
#
# 实际上本文件第 1189/1241 行已实现**延迟加载**（registry 里 "debugger": None），
# 模块级导入纯属冗余。现已改为由调用方直接从 tools.debugger_agent 导入。