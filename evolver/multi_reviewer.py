"""
multi_reviewer — 多评审交叉验证 v1.0
====================================
对关键结论做"多视角交叉评审"，降低单一评审的系统性偏差。

借鉴 ReasFlow 的"3 评审 × 9 维 rubric"评测设计，但做轻量简化：
  - 多视角评审：用不同评审角色（严格/务实/创新）对同一内容打分
  - 分歧度计算：标准差/均值归一化，量化评审间一致性
  - 高分歧自动升级：分歧度过高时标记"需人工仲裁"

设计原则：
  - 分歧度计算是**确定性**的（不依赖 LLM）
  - 评审打分依赖外部 LLM 回调（由调用方注入），本模块不直接持有客户端
  - 全部标准库实现，无外部依赖
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ReviewResult:
    """多评审结果。"""

    scores: dict[str, float] = field(default_factory=dict)   # {视角: 分数}
    reasons: dict[str, str] = field(default_factory=dict)    # {视角: 简要理由}
    divergence: float = 0.0                                   # 分歧度 0-1
    needs_arbitration: bool = False                          # 是否需人工仲裁
    avg_score: float = 0.0
    failed: list[str] = field(default_factory=list)          # 评审失败的视角

    def to_dict(self) -> dict:
        return {
            "scores": self.scores,
            "reasons": self.reasons,
            "divergence": round(self.divergence, 4),
            "needs_arbitration": self.needs_arbitration,
            "avg_score": round(self.avg_score, 2),
            "failed": self.failed,
        }


# ── 多评审器 ──────────────────────────────────────────────


class MultiReviewer:
    """多视角交叉评审器。"""

    # 内置评审视角（不同立场，降低单点偏差）
    PERSPECTIVES: dict[str, str] = {
        "strict": "你是一名极其严格的学术审稿人，重点审查正确性与严谨性，倾向保守打分。",
        "practical": "你是一名务实工程师，重点审查可行性与落地价值，客观中立打分。",
        "innovative": "你是一名创新评审，重点审查新颖性与突破性，给分相对宽容。",
    }

    # 分歧度阈值：超过则需人工仲裁
    DIVERGENCE_THRESHOLD = 0.35

    # ── 单视角评审 ──────────────────────────────────────

    def _single_review(
        self,
        content: str,
        question: str,
        persona: str,
        llm_chat_fn: Callable[[list[dict]], str],
        temperature: float = 0.0,
    ) -> tuple[float, str]:
        """让 LLM 以某视角对内容打分，返回 (分数, 理由)。

        temperature 默认 0.0，对应"确定性评分"协议（降低评分方差）。
        """
        prompt = (
            f"{persona}\n\n"
            f"请以确定性、可复现的方式（等效 temperature={temperature}）"
            f"针对以下问题，对给出的内容打分（0-10 分，可保留一位小数）：\n"
            f"问题：{question}\n\n"
            f"内容：\n{content[:4000]}\n\n"
            f"请严格按以下格式回复：\n"
            f"评分：<数字>\n"
            f"理由：<一句话>"
        )
        raw = llm_chat_fn([{"role": "user", "content": prompt}])
        # 提取分数
        m = re.search(r'评分[：:]\s*(\d+(?:\.\d+)?)', raw)
        if m:
            score = float(m.group(1))
            score = max(0.0, min(10.0, score))
        else:
            # 尝试提取第一个 0-10 的数字
            m = re.search(r'\b(\d+(?:\.\d+)?)\b', raw)
            if m:
                score = max(0.0, min(10.0, float(m.group(1))))
            else:
                score = 0.0
        # 提取理由
        reason = ""
        m = re.search(r'理由[：:]\s*(.+)', raw)
        if m:
            reason = m.group(1).strip()[:100]
        return score, reason

    # ── 分歧度（确定性）────────────────────────────────

    @staticmethod
    def compute_divergence(scores: list[float]) -> float:
        """计算分歧度：标准差 / 均值，归一化到 [0, 1]。"""
        if len(scores) < 2:
            return 0.0
        mean = sum(scores) / len(scores)
        if mean == 0:
            return 0.0
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = variance ** 0.5
        return min(1.0, std / mean)

    # ── 多视角评审 ──────────────────────────────────────

    def review(
        self,
        content: str,
        question: str,
        llm_chat_fn: Callable[[list[dict]], str],
        perspectives: list[str] | None = None,
        runs_per_perspective: int = 1,
        temperature: float = 0.0,
    ) -> ReviewResult:
        """对内容做多视角交叉评审。

        runs_per_perspective: 每个视角的采样次数（>1 时取平均，降低方差）
        temperature: 评分温度（默认 0.0 确定性，借鉴 ReasFlow 协议）
        """
        if not content.strip():
            return ReviewResult(needs_arbitration=True, failed=["empty_content"])

        if perspectives is None:
            perspectives = list(self.PERSPECTIVES.keys())

        runs = max(1, runs_per_perspective)
        result = ReviewResult()
        for name in perspectives:
            persona = self.PERSPECTIVES.get(name, self.PERSPECTIVES["practical"])
            scores_per_run: list[float] = []
            reason = ""
            for _ in range(runs):
                try:
                    score, reason = self._single_review(
                        content, question, persona, llm_chat_fn, temperature
                    )
                    scores_per_run.append(score)
                except Exception:
                    continue
            if scores_per_run:
                # 多运行取平均（温度0 + 多运行，降低评分方差）
                result.scores[name] = round(sum(scores_per_run) / len(scores_per_run), 2)
                result.reasons[name] = reason
            else:
                result.failed.append(name)

        valid_scores = list(result.scores.values())
        if valid_scores:
            result.avg_score = sum(valid_scores) / len(valid_scores)
            result.divergence = self.compute_divergence(valid_scores)
            result.needs_arbitration = result.divergence > self.DIVERGENCE_THRESHOLD
        else:
            result.needs_arbitration = True

        return result

    def format_result(self, result: ReviewResult) -> str:
        icon = "⚖️" if result.needs_arbitration else "✅"
        lines = [
            f"{icon} 多评审交叉验证结果",
            f"{'─'*40}",
            f"平均分: {result.avg_score:.2f}/10",
            f"分歧度: {result.divergence:.3f}（阈值 {self.DIVERGENCE_THRESHOLD}）",
            f"结论: {'⚠️ 需人工仲裁（评审分歧过大）' if result.needs_arbitration else '✅ 评审趋于一致'}",
        ]
        if result.scores:
            lines.append("")
            for name, score in result.scores.items():
                reason = result.reasons.get(name, "")
                lines.append(f"  [{name}] {score:.1f}/10 {('— ' + reason) if reason else ''}")
        if result.failed:
            lines.append("")
            lines.append(f"  ⚠️ 评审失败视角: {', '.join(result.failed)}")
        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_reviewer = MultiReviewer()


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "multi_reviewer",
        "description": (
            "多评审交叉验证。用不同评审视角对同一内容打分，计算分歧度，"
            "分歧过高时标记需人工仲裁，降低单一评审偏差。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要评审的内容",
                },
                "question": {
                    "type": "string",
                    "description": "评审要回答的问题",
                    "default": "该内容是否可信、正确、有价值？",
                },
                "scores": {
                    "type": "string",
                    "description": "已有多视角分数的 JSON（如 '{\"strict\":8.0,\"practical\":7.5}'，用于仅计算分歧度）",
                    "default": "",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
}


def _deterministic_review(content: str, question: str) -> str:
    """确定性降级评审：在无独立 LLM 客户端时，用规则做基础检查。

    不调用 LLM，只做确定性启发式检查，并明确标注「非多视角 LLM 评审」。
    用于避免工具在无客户端时完全失效（摆设）。
    """
    issues: list[str] = []
    checks: list[str] = []

    # 1. 内容非空 / 长度
    checks.append("内容长度")
    stripped = content.strip()
    if not stripped:
        issues.append("内容为空")
    elif len(stripped) < 50:
        issues.append(f"内容过短（{len(stripped)} 字符），可能不足以支撑可信结论")

    # 2. 结论存在性（启发式）
    checks.append("结论存在性")
    conclusion_markers = ("结论", "因此", "综上", "所以", "由此可见", "判定", "诊断")
    if stripped and not any(m in stripped for m in conclusion_markers):
        issues.append("未检测到明确的结论性表述")

    # 3. 数字自洽（百分比越界等明显错误）
    checks.append("数字自洽")
    if stripped:
        for pct in re.findall(r'(\d+(?:\.\d+)?)\s*%', stripped):
            if float(pct) > 100:
                issues.append(f"检测到越界百分比: {pct}%")
                break

    # 4. 未完成占位检测
    checks.append("模糊占位检测")
    if stripped:
        for placeholder in ("TODO", "待补", "待定", "待完善", "略", "…", "……"):
            if placeholder in stripped:
                issues.append(f"检测到可能的未完成占位: {placeholder}")
                break

    lines = [
        "⚠️ 确定性降级评审（本环境无独立 LLM 客户端，未执行多视角 LLM 评审）",
        "─" * 40,
        f"问题: {question}",
        f"已执行确定性检查: {', '.join(checks)}",
    ]
    if issues:
        lines.append("")
        lines.append(f"发现 {len(issues)} 个需注意的点:")
        for i, issue in enumerate(issues, 1):
            lines.append(f"  🔴 {i}. {issue}")
    else:
        lines.append("")
        lines.append("✅ 未发现明显问题（仅规则检查，不代表内容正确）")
    lines.append("")
    lines.append(
        "💡 如需真正的多视角 LLM 评审：请由主 Agent 自行以 "
        "strict/practical/innovative 三视角打分，再用 scores 参数传入计算分歧度。"
    )
    return "\n".join(lines)


def execute_multi_reviewer_tool(arguments: dict[str, Any]) -> str:
    """多评审器工具入口。

    注：真正多视角 LLM 评审需要 LLM 客户端，本工具在无客户端时
    仍可计算给定分数的分歧度（确定性部分），并退化为确定性降级评审。
    """
    content = arguments.get("content", "")
    question = arguments.get("question", "该内容是否可信、正确、有价值？")
    scores_raw = arguments.get("scores", "")

    # 若提供了分数，仅做确定性分歧度计算（不依赖 LLM）
    if scores_raw:
        try:
            scores = json.loads(scores_raw)
        except json.JSONDecodeError as exc:
            return f"分数 JSON 解析错误: {exc}"
        vals = list(scores.values())
        divergence = _reviewer.compute_divergence(vals)
        avg = sum(vals) / len(vals) if vals else 0
        needs = divergence > _reviewer.DIVERGENCE_THRESHOLD
        return (
            f"📊 分歧度计算\n{'─'*40}\n"
            f"分数: {scores}\n"
            f"平均分: {avg:.2f}\n"
            f"分歧度: {divergence:.3f}（阈值 {_reviewer.DIVERGENCE_THRESHOLD}）\n"
            f"结论: {'⚠️ 需人工仲裁' if needs else '✅ 评审趋于一致'}"
        )

    # 无分数时，尝试调用 LLM 做多视角评审
    try:
        import agent1
        client = getattr(agent1, "_global_client", None)
        if client is None:
            return _deterministic_review(content, question)
        def _chat(msgs):
            return client.chat(msgs, tools=None).get("content", "")
        result = _reviewer.review(content, question, _chat)
        return _reviewer.format_result(result)
    except Exception as exc:
        return f"多评审器错误: {type(exc).__name__}: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 确定性分歧度计算示例
    r = MultiReviewer()
    print("分歧度(一致):", round(r.compute_divergence([8.0, 8.2, 7.8]), 4))
    print("分歧度(分歧):", round(r.compute_divergence([9.0, 3.0, 5.0]), 4))
