"""
evidence_verifier — 确定性证据验证器 v1.0
========================================
不调用 LLM，直接校验评估/评审数据的**内部一致性**，对抗"自评偏差"。

借鉴 ReasFlow 的"离线证据验证器"（offline evidence verifier）：
在评审结论被采信前，先验证分数、快照、判定之间是否自洽。

校验项：
  1. 快照完整性   —— before/after 快照关键字段是否齐全
  2. 判定一致性   —— verdict 与 veto_reasons / overall_score 是否矛盾
  3. 分数自洽     —— 总分与维度分是否对得上（可选，传入明细时校验）
  4. 审计交叉一致 —— 评估报告与审计日志是否交叉一致（可选）

全部使用标准库，无外部依赖。只做确定性检查，不做主观判断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceIssue:
    """证据校验发现的问题。"""

    check: str       # 校验项名称
    message: str


@dataclass
class EvidenceReport:
    """证据校验报告。"""

    passed: bool
    issues: list[EvidenceIssue] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [{"check": i.check, "message": i.message} for i in self.issues],
            "checks_run": self.checks_run,
        }


class EvidenceVerifier:
    """确定性证据验证器。"""

    # 判定与分数的一致性规则：verdict 与 overall_score 的合理区间
    def verify_snapshot(self, snapshot: dict | None) -> list[EvidenceIssue]:
        """校验指标快照的完整性。"""
        issues: list[EvidenceIssue] = []
        if snapshot is None:
            issues.append(EvidenceIssue("snapshot", "快照缺失（None）"))
            return issues

        # 关键字段存在性（允许为 0，但字段必须存在）
        required = [
            "health_score", "error_rate", "test_total", "test_passed",
            "test_failed", "knowledge_entries", "module_import_ms",
        ]
        for key in required:
            if key not in snapshot:
                issues.append(EvidenceIssue("snapshot", f"快照缺少字段: {key}"))

        # 逻辑一致性：test_passed + test_failed == test_total
        if all(k in snapshot for k in ("test_total", "test_passed", "test_failed")):
            tp = snapshot.get("test_passed", 0) or 0
            tf = snapshot.get("test_failed", 0) or 0
            tt = snapshot.get("test_total", 0) or 0
            if tp + tf != tt:
                issues.append(
                    EvidenceIssue(
                        "snapshot",
                        f"测试计数不自洽: passed({tp}) + failed({tf}) != total({tt})",
                    )
                )

        # error_rate 应在 [0, 100] 区间
        er = snapshot.get("error_rate")
        if er is not None and isinstance(er, (int, float)):
            if er < 0 or er > 100:
                issues.append(EvidenceIssue("snapshot", f"error_rate 越界: {er}"))

        return issues

    def verify_report(
        self,
        report: dict | None,
        dimension_scores: list[float] | None = None,
    ) -> list[EvidenceIssue]:
        """校验评估报告的判定一致性。"""
        issues: list[EvidenceIssue] = []
        if report is None:
            issues.append(EvidenceIssue("report", "评估报告缺失（None）"))
            return issues

        verdict = report.get("verdict", "pending")
        score = report.get("overall_score")
        veto = report.get("veto_reasons") or []

        # 1. 判定与分数一致性
        if isinstance(score, (int, float)):
            if verdict == "improved" and score < 0:
                issues.append(
                    EvidenceIssue("report", f"verdict=improved 但 overall_score={score} < 0")
                )
            if verdict == "degraded" and score > 0:
                issues.append(
                    EvidenceIssue("report", f"verdict=degraded 但 overall_score={score} > 0")
                )

        # 2. 一票否决与判定的矛盾：有 veto 但判定不是 degraded
        if veto and verdict != "degraded":
            issues.append(
                EvidenceIssue(
                    "report",
                    f"存在 veto_reasons({len(veto)}条) 但 verdict={verdict}，应为 degraded",
                )
            )

        # 3. 分数自洽（传入维度分时校验加权和）
        if dimension_scores is not None and isinstance(score, (int, float)):
            total = sum(s for s in dimension_scores)
            if abs(total - score) > 0.01:
                issues.append(
                    EvidenceIssue(
                        "report",
                        f"维度分之和({total:.4f}) 与 overall_score({score:.4f}) 不一致",
                    )
                )

        return issues

    def verify_effect_report(self, report: Any) -> EvidenceReport:
        """校验 EffectReport 对象（或 dict）的完整一致性。"""
        checks = ["snapshot", "report"]
        issues: list[EvidenceIssue] = []

        # 兼容 EffectReport 对象和 dict
        if hasattr(report, "to_dict"):
            d = report.to_dict()
        elif isinstance(report, dict):
            d = report
        else:
            return EvidenceReport(
                passed=False,
                issues=[EvidenceIssue("report", f"不支持的报告类型: {type(report)}")],
                checks_run=["report"],
            )

        # 快照校验
        issues.extend(self.verify_snapshot(d.get("before")))
        issues.extend(self.verify_snapshot(d.get("after")))

        # 报告判定校验
        issues.extend(self.verify_report(d))

        report_obj = EvidenceReport(
            passed=len(issues) == 0,
            issues=issues,
            checks_run=checks,
        )
        return report_obj

    def format_report(self, report: EvidenceReport) -> str:
        icon = "✅" if report.passed else "❌"
        lines = [
            f"{icon} 证据一致性校验",
            f"{'─'*40}",
            f"结论: {'通过' if report.passed else '未通过'} "
            f"（{len(report.issues)} 个问题）",
            f"已执行: {', '.join(report.checks_run)}",
        ]
        if report.issues:
            lines.append("")
            for issue in report.issues:
                lines.append(f"  🔴 [{issue.check}] {issue.message}")
        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_verifier = EvidenceVerifier()


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "evidence_verifier",
        "description": (
            "确定性证据验证器。不调用 LLM，校验评估快照与报告的内部一致性"
            "（快照完整性、判定一致性、分数自洽），对抗自评偏差。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "report": {
                    "type": "string",
                    "description": "评估报告 JSON（含 before/after 快照、verdict、overall_score、veto_reasons）",
                    "default": "",
                },
            },
            "required": ["report"],
            "additionalProperties": False,
        },
    },
}


def execute_evidence_verifier_tool(arguments: dict[str, Any]) -> str:
    """证据验证器工具入口。"""
    import json

    report_raw = arguments.get("report", "")
    if not report_raw:
        return "请提供评估报告 JSON"

    try:
        report = json.loads(report_raw)
    except json.JSONDecodeError as exc:
        return f"报告 JSON 解析错误: {exc}"

    result = _verifier.verify_effect_report(report)
    return _verifier.format_report(result)


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 构造一个"分数与判定矛盾"的报告，验证拦截
    bad = {
        "verdict": "improved",
        "overall_score": -0.5,
        "veto_reasons": ["测试失败数增加: 0→1"],
        "before": {"health_score": 85, "error_rate": 5.0, "test_total": 10, "test_passed": 10, "test_failed": 0, "knowledge_entries": 5, "module_import_ms": 100.0},
        "after": {"health_score": 80, "error_rate": 8.0, "test_total": 10, "test_passed": 8, "test_failed": 2, "knowledge_entries": 5, "module_import_ms": 110.0},
    }
    rep = _verifier.verify_effect_report(bad)
    print(_verifier.format_report(rep))
