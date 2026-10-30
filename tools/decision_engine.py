"""decision_engine — 学习与决策辅助系统

基于知识库和推理规则，为 Agent 1 提供决策建议。
支持方案推荐、经验匹配和决策记录。
帮助 Agent 1 在遇到问题时快速定位已有经验。
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
DECISIONS_FILE = SANDBOX_DIR / "memory" / "decisions.json"

# ── 错误类型 ──────────────────────────────────────────────


class DecisionError(RuntimeError):
    """决策引擎错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "decision_engine",
        "description": (
            "学习与决策辅助系统。基于知识库和经验记录，"
            "为遇到问题提供解决方案推荐、经验匹配和决策记录。"
            "帮助快速定位已有经验并做出最优决策。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "advise",
                        "record_decision",
                        "history",
                        "stats",
                        "similar_problems",
                        "gate",
                    ],
                    "description": (
                        "操作类型："
                        "advise — 根据问题描述提供建议；"
                        "record_decision — 记录一次决策及结果；"
                        "history — 查看历史决策记录；"
                        "stats — 决策统计；"
                        "similar_problems — 查找相似问题；"
                        "gate — 立项门禁：立项前强制核查负面先验/已知死路/开放问题，并要求预注册失败判据。"
                    ),
                },
                "problem": {
                    "type": "string",
                    "description": "问题描述（advise 操作必需）",
                    "default": "",
                },
                "proposal": {
                    "type": "string",
                    "description": "立项方向/提议描述（gate 操作必需）",
                    "default": "",
                },
                "context": {
                    "type": "string",
                    "description": "当前上下文信息",
                    "default": "",
                },
                "decision": {
                    "type": "string",
                    "description": "做出的决策描述（record_decision 操作必需）",
                    "default": "",
                },
                "outcome": {
                    "type": "string",
                    "description": "决策结果（record_decision 操作可选）",
                    "default": "",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数",
                    "default": 5,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 决策引擎 ──────────────────────────────────────────────


class DecisionEngine:
    """学习与决策辅助引擎。"""

    def __init__(self) -> None:
        self._decisions: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """从文件加载决策记录。"""
        if DECISIONS_FILE.is_file():
            try:
                self._decisions = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._decisions = []

    def _save(self) -> None:
        """保存决策记录到文件。"""
        DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DECISIONS_FILE.write_text(
            json.dumps(self._decisions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 知识库 ──────────────────────────────────────────

    # 内置决策规则库 — 基于经验和常见场景
    _KNOWLEDGE_BASE: list[dict[str, Any]] = [
        {
            "keywords": ["导入失败", "import error", "module not found", "模块导入"],
            "advice": "检查 Python 路径和文件是否存在。运行 `self_check` 工具诊断模块健康状况。",
            "category": "工具开发",
        },
        {
            "keywords": ["备份", "backup", "文件丢失", "数据丢失"],
            "advice": "使用 `backup_file` 工具创建文件备份。所有备份存储在 `.backups/` 目录。",
            "category": "文件管理",
        },
        {
            "keywords": ["搜索", "查找", "find", "grep", "search"],
            "advice": "使用 `search_text` 工具进行文件内容搜索，支持正则表达式和通配符过滤。",
            "category": "检索",
        },
        {
            "keywords": ["计算", "数学", "calculate", "math", "表达式"],
            "advice": "使用 `calculate` 工具执行安全数学计算，支持四则运算、数学函数和常量。",
            "category": "工具使用",
        },
        {
            "keywords": ["知识", "经验", "学习", "记录", "knowledge"],
            "advice": "使用 `knowledge` 工具存储和检索知识条目。知识库持久化存储在 `knowledge/knowledge_store.json`。",
            "category": "知识管理",
        },
        {
            "keywords": ["任务", "追踪", "进度", "task", "完成"],
            "advice": "使用 `task_tracker` 工具创建和管理任务。支持多阶段、状态追踪和报告生成。",
            "category": "任务管理",
        },
        {
            "keywords": ["健康", "检查", "自检", "诊断", "health", "check"],
            "advice": "使用 `self_check` 工具进行全面健康检查，或 `test_runner` 运行自动化测试。",
            "category": "系统维护",
        },
        {
            "keywords": ["监控", "性能", "monitor", "统计", "调用"],
            "advice": "使用 `monitor` 工具查看工具调用统计、性能分析和错误记录。",
            "category": "系统维护",
        },
        {
            "keywords": ["重启", "restart", "reboot", "重新启动"],
            "advice": "使用 `/restart` 或 `/reboot` 命令重启进程。重启会保留对话历史。",
            "category": "系统操作",
        },
        {
            "keywords": ["文件大小", "类型统计", "最大文件", "file_utils"],
            "advice": "使用 `file_utils` 工具进行文件查找、类型分布统计、大小分析和最近文件列表。",
            "category": "文件管理",
        },
        {
            "keywords": ["积分", "权限", "point", "授权", "申请"],
            "advice": "如需扩展权限，需向监护人说明所需权限、用途和持续时间，并申请消耗积分。",
            "category": "规则",
        },
        {
            "keywords": ["循环", "卡住", "重复", "loop", "stuck", "不停"],
            "advice": "读取 `supervision/clue.md` 获取监护人的提示线索，打破当前循环。",
            "category": "自救",
        },
        {
            "keywords": ["测试", "test", "验证", "单元测试"],
            "advice": "使用 `test_runner` 工具运行自动化测试，验证各模块功能是否正常。",
            "category": "质量保证",
        },
    ]

    # ── 已知死路/开放问题先验清单（v3.0 立项门禁用）──────────
    # 每条：keywords(匹配词), verdict(结论), evidence(证据来源), category(类型)
    # 数据来源：SAT 攻坚项目真实负面结果（均有知识卡片/报告支撑）
    _DEAD_ENDS: list[dict[str, Any]] = [
        {
            "keywords": ["参数", "变异", "调参", "restart", "rephase", "decision", "heuristic", "tuning", "单点"],
            "verdict": "单点参数/代码变异已证死路：18 次变异全部 REJECT，默认 Kissat 是强局部最优。",
            "evidence": "S15.2/S15.3/T2746；solver_summary.md",
            "category": "已知死路",
        },
        {
            "keywords": ["谱", "独立数", "hoffman", "谱方法", "spectral", "lanczos", "特征值"],
            "verdict": "谱方法证独立数下界已失败：Hoffman 界对 1-ZC 松 5.4 倍。",
            "evidence": "T2752-R 负面结果",
            "category": "已知死路",
        },
        {
            "keywords": ["反编码", "bit-blasting", "电路", "乘法器", "word-level", "逆向", "carry", "nand"],
            "verdict": "从展平 CNF 反编码电路是研究级难题：XOR 被 NAND 展平后信息不可逆丢失。",
            "evidence": "S13 收口",
            "category": "已知死路",
        },
        {
            "keywords": ["ramsey", "组合下界", "谱界", "覆盖数", "van der waerden", "fermat", "独立集下界"],
            "verdict": "组合下界证 Ramsey/独立集 UNSAT 等价于数学开放问题（许多 Ramsey 数未解）。",
            "evidence": "S12.2/T2756",
            "category": "开放问题",
        },
        {
            "keywords": ["对口", "关键词预筛", "家族筛选", "对称破缺适用面", "预筛"],
            "verdict": "按「对口家族关键词」预筛对称破缺实例会漏赢面（漏掉 RoundRobin），应全量扫描再按自同构群阶分诊。",
            "evidence": "T2765 教训",
            "category": "方法教训",
        },
        {
            "keywords": ["泛化", "结构推理", "组合不变量", "自动发现", "推广"],
            "verdict": "把 Tseitin 奇偶守恒「泛化」到更广组合结构，撞的是数学开放问题，非工程可解。",
            "evidence": "T2752-R/T2756 负面结果",
            "category": "开放问题",
        },
    ]

    # ── 公开接口 ────────────────────────────────────────

    def gate(self, proposal: str) -> str:
        """立项门禁：立项前强制核查负面先验 + 已知死路 + 开放问题 + 失败判据。

        这是「止损型元认知」的核心：把负面结果前置到立项决策点，
        避免重复撞已知的墙。软约束——需 Agent 在立项前主动调用。
        """
        if not proposal.strip():
            raise DecisionError("立项方向描述不能为空")

        prop_lower = proposal.lower()

        # 1. 内置死路/开放问题清单匹配
        dead_hits = []
        for entry in self._DEAD_ENDS:
            hits = [k for k in entry["keywords"] if k in prop_lower]
            if hits:
                dead_hits.append((entry, hits))

        # 2. 知识库 boundary 卡片检索
        boundary_hits = self._fetch_boundary_warnings(proposal, max_results=4)

        # 3. 历史失败决策检索
        words = [w for w in prop_lower.split() if len(w) > 2]
        failed_decisions = [
            d for d in self._decisions
            if any(w in d.get("outcome", "") for w in ("失败", "❌", "不可行", "死路", "REJECT"))
            and any(w in d.get("decision", "").lower() for w in words)
        ][:3]

        lines = [
            "🚦 立项门禁",
            "=" * 50,
            f"立项方向: {proposal}",
            "",
        ]

        if dead_hits or boundary_hits or failed_decisions:
            lines.append("⚠️ 负面先验命中（请逐条确认是否与本立项无关，再继续）:")
            lines.append("")
            for entry, hits in dead_hits:
                lines.append(f"  🔴 [{entry['category']}] 命中词: {', '.join(hits)}")
                lines.append(f"     {entry['verdict']}")
                lines.append(f"     📎 证据: {entry['evidence']}")
                lines.append("")
            for w in boundary_hits:
                lines.append(f"  🟠 [boundary] {w['title']}")
                lines.append(f"     {w['content'][:100]}")
                lines.append("")
            for d in failed_decisions:
                lines.append(f"  🟡 [历史失败] {d['decision'][:60]}")
                lines.append(f"     结果: {d['outcome'][:60]}")
                lines.append("")
        else:
            lines.append("✅ 未命中已知死路/负面先验。")

        # 4. 失败判据模板（强制预注册）
        lines.append("")
        lines.append("📝 请预注册失败判据（回答后立项才算完整）:")
        lines.append("   1. 什么可量化证据会证明此方向失败？（例：加速比 < 1 / 求解率不升反降）")
        lines.append("   2. 投入多少步/时间后若仍无该证据，就止损？")
        lines.append("   3. 是否已通过外部核查（文献/专家确认非开放问题）？")
        lines.append("")
        lines.append("💡 立项前应先用 web_search 核查「此方向是否已是已知开放问题/死路」。")

        return "\n".join(lines)

    def advise(self, problem: str, context: str = "", max_results: int = 5) -> str:
        """根据问题描述提供建议。"""
        if not problem.strip():
            raise DecisionError("问题描述不能为空")

        problem_lower = problem.lower()
        context_lower = context.lower() if context else ""

        # 计算匹配度
        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self._KNOWLEDGE_BASE:
            score = 0
            for keyword in entry["keywords"]:
                if keyword.lower() in problem_lower:
                    score += 10
                if context_lower and keyword.lower() in context_lower:
                    score += 5
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        actual_limit = min(max_results, len(scored))

        lines = [
            f"💡 决策建议",
            f"{'='*50}",
            f"问题: {problem}",
        ]
        if context:
            lines.append(f"上下文: {context}")

        if not scored:
            # 没有匹配，提供通用建议
            lines.extend([
                "",
                "未找到精确匹配的经验。建议:",
                "  1. 使用 `self_check` 进行健康检查",
                "  2. 使用 `knowledge` 搜索相关知识",
                "  3. 使用 `search_text` 在代码库中搜索",
                "  4. 查阅 `supervision/clue.md` 获取监护人提示",
                "  5. 记录本次经验到知识库供后续参考",
            ])
        else:
            lines.append(f"\n找到 {len(scored)} 条相关经验（显示前 {actual_limit} 条）:\n")
            for i, (score, entry) in enumerate(scored[:actual_limit], 1):
                lines.append(f"  ── 建议 {i}（匹配度: {score}）──")
                lines.append(f"  📂 分类: {entry['category']}")
                lines.append(f"  💬 建议: {entry['advice']}")
                lines.append("")

        # ── 失效边界预警（v2.0 借鉴 ReasFlow failure_boundary 陈述）──
        warnings = self._fetch_boundary_warnings(problem)
        if warnings:
            lines.append("")
            lines.append(f"⚠️ 失效边界预警（命中 {len(warnings)} 条，请先确认不触发）:")
            for i, w in enumerate(warnings, 1):
                lines.append(f"  {i}. {w['title']}")
                lines.append(f"     {w['content'][:120]}")

        lines.append(f"{'─'*50}")
        lines.append("如需记录本次决策，请使用 action=record_decision")

        return "\n".join(lines)

    def _fetch_boundary_warnings(self, problem: str, max_results: int = 3) -> list[dict[str, Any]]:
        """从知识库检索失效边界卡片（kind=boundary），用于决策前置预警。

        直接读取 knowledge_store 内部数据，避免字符串往返解析。
        用问题分词做简单命中评分，返回 top-N 命中卡片。
        """
        try:
            from tools.knowledge_store import _store, _search_enhancer
            # 复用 knowledge_store 的分词器（jieba 优先，中文有效）
            query_terms = [
                w.lower() for w in _search_enhancer.tokenize(problem)
                if len(w.strip()) > 1
            ]
            if not query_terms:
                query_terms = [problem.lower()]
            matches: list[tuple[int, dict[str, Any]]] = []
            for entry in _store._data.values():
                if entry.get("kind") != "boundary":
                    continue
                text = (
                    f"{entry.get('title', '')} {entry.get('content', '')} "
                    f"{' '.join(entry.get('tags', []))}"
                ).lower()
                score = sum(1 for t in query_terms if t in text)
                if score > 0:
                    matches.append((score, entry))
            matches.sort(key=lambda x: -x[0])
            return [e for _, e in matches[:max_results]]
        except Exception:
            return []

    def record_decision(self, decision: str, outcome: str = "") -> str:
        """记录一次决策及结果。"""
        if not decision.strip():
            raise DecisionError("决策描述不能为空")

        entry = {
            "id": f"D{int(time.time())}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "decision": decision.strip(),
            "outcome": outcome.strip() if outcome else "待评估",
        }
        self._decisions.append(entry)
        self._save()

        return f"📝 已记录决策 [{entry['id']}]: {decision[:60]}{'…' if len(decision) > 60 else ''}"

    def history(self, max_results: int = 10) -> str:
        """查看历史决策记录。"""
        if not self._decisions:
            return "暂无决策记录。"

        recent = self._decisions[-max_results:]
        lines = [f"📋 最近 {len(recent)} 条决策记录\n"]
        for entry in reversed(recent):
            outcome_icon = "✅" if entry["outcome"] != "待评估" and "失败" not in entry["outcome"] else "⏳"
            lines.append(f"  {outcome_icon} [{entry['id']}] {entry['timestamp']}")
            lines.append(f"     决策: {entry['decision'][:80]}")
            lines.append(f"     结果: {entry['outcome'][:80]}")
            lines.append("")

        return "\n".join(lines)

    def stats(self) -> str:
        """决策统计。"""
        if not self._decisions:
            return "暂无决策记录。"

        total = len(self._decisions)
        evaluated = sum(1 for d in self._decisions if d["outcome"] != "待评估")
        successful = sum(1 for d in self._decisions if "成功" in d["outcome"] or "✅" in d["outcome"])
        failed = sum(1 for d in self._decisions if "失败" in d["outcome"] or "❌" in d["outcome"])

        first = self._decisions[0]["timestamp"]
        last = self._decisions[-1]["timestamp"]

        lines = [
            f"📊 决策统计\n{'='*30}",
            f"总决策数: {total}",
            f"已评估: {evaluated}",
            f"✅ 成功: {successful}",
            f"❌ 失败: {failed}",
            f"最早记录: {first}",
            f"最近记录: {last}",
        ]
        return "\n".join(lines)

    def similar_problems(self, problem: str, max_results: int = 5) -> str:
        """查找相似问题。"""
        if not problem.strip():
            raise DecisionError("问题描述不能为空")

        problem_lower = problem.lower()

        # 在历史决策中查找
        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self._decisions:
            score = 0
            decision_lower = entry["decision"].lower()
            outcome_lower = entry["outcome"].lower()

            # 简单的关键词匹配
            words = problem_lower.split()
            for word in words:
                if len(word) > 2 and word in decision_lower:
                    score += 3
                if len(word) > 2 and word in outcome_lower:
                    score += 1

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        actual_limit = min(max_results, len(scored))

        if not scored:
            return f"未找到与 '{problem}' 相似的历史问题。"

        lines = [f"🔍 与 '{problem}' 相似的问题（找到 {len(scored)} 条）:\n"]
        for i, (score, entry) in enumerate(scored[:actual_limit], 1):
            icon = "✅" if entry["outcome"] != "待评估" and "失败" not in entry["outcome"] else "⏳"
            lines.append(f"  {icon} [{entry['id']}] (匹配度: {score})")
            lines.append(f"     决策: {entry['decision'][:80]}")
            lines.append(f"     结果: {entry['outcome'][:80]}")
            lines.append("")

        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_engine = DecisionEngine()


def execute_decision_engine_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")
    problem = arguments.get("problem", "")
    context = arguments.get("context", "")
    decision = arguments.get("decision", "")
    outcome = arguments.get("outcome", "")
    proposal = arguments.get("proposal", "")
    max_results = int(arguments.get("max_results", 5))

    try:
        if action == "advise":
            return _engine.advise(problem, context, max_results)
        elif action == "gate":
            return _engine.gate(proposal)
        elif action == "record_decision":
            return _engine.record_decision(decision, outcome)
        elif action == "history":
            return _engine.history(max_results)
        elif action == "stats":
            return _engine.stats()
        elif action == "similar_problems":
            return _engine.similar_problems(problem, max_results)
        else:
            return f"未知操作: {action}"
    except DecisionError as exc:
        return f"决策引擎错误: {exc}"
