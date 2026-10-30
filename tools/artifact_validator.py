"""
artifact_validator — 产物验证器 v1.0
====================================
对研究/写作/分析产物做**确定性**校验（不依赖 LLM），借鉴 ReasFlow 的
Internal Verification Loops（证明连贯性 / 数值一致性 / 手稿可编译）。

校验维度：
  1. 结构完整性   —— 必需章节是否齐全
  2. 数字自洽     —— 同一指标在不同位置是否矛盾
  3. 引用可追溯   —— 文中引用标记是否都能在 references 中找到
  4. 可解析性     —— Markdown / JSON / LaTeX 结构是否可解析

设计原则：只报"确定性"错误，不做主观判断；error 级表示必须修复，
warning 级表示建议优化。全部使用标准库，无外部依赖。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ── 错误类型 ──────────────────────────────────────────────


class ArtifactValidatorError(RuntimeError):
    """产物验证器错误。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ArtifactIssue:
    """产物校验发现的一个问题。"""

    level: str          # "error"(必须修复) / "warning"(建议优化)
    dimension: str      # 校验维度：structure / numeric / reference / parsability
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "dimension": self.dimension, "message": self.message}


@dataclass
class ArtifactReport:
    """产物校验报告。"""

    artifact_type: str
    passed: bool
    issues: list[ArtifactIssue] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[ArtifactIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ArtifactIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "checks_run": self.checks_run,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


# ── 产物验证器 ─────────────────────────────────────────────


class ArtifactValidator:
    """产物确定性校验器。

    用法：
        validator = ArtifactValidator()
        report = validator.validate(content, artifact_type="report")
        if not report.passed:
            print(report.errors)
    """

    # 各类型产物"建议具备"的章节标题关键词（中英文）
    REQUIRED_SECTIONS: dict[str, list[str]] = {
        "report": ["引言", "结论", "introduction", "conclusion"],
        "research": ["背景", "方法", "结论", "background", "method", "conclusion"],
        "article": ["引言", "结论", "introduction", "conclusion"],
    }

    def __init__(self) -> None:
        pass

    # ── 主入口 ──────────────────────────────────────────

    def validate(
        self,
        content: str,
        artifact_type: str = "report",
        references: list[str] | None = None,
    ) -> ArtifactReport:
        """校验一段产物文本。返回 ArtifactReport。"""
        if not content or not content.strip():
            report = ArtifactReport(artifact_type=artifact_type, passed=False)
            report.issues.append(ArtifactIssue("error", "structure", "产物内容为空"))
            report.checks_run = ["structure"]
            return report

        report = ArtifactReport(artifact_type=artifact_type, passed=True)

        # 1. 结构完整性
        self._check_structure(content, artifact_type, report)
        # 2. 数字自洽
        self._check_numeric_consistency(content, report)
        # 3. 引用可追溯
        self._check_references(content, references, report)
        # 4. 可解析性
        self._check_parsability(content, artifact_type, report)
        # 5. 执行痕迹检查（v2.0 借鉴 ReasFlow Hallucination Check）
        self._check_execution_evidence(content, artifact_type, report)

        report.passed = len(report.errors) == 0
        return report

    # ── 1. 结构完整性 ──────────────────────────────────

    def _check_structure(self, content: str, artifact_type: str, report: ArtifactReport) -> None:
        report.checks_run.append("structure")
        required = self.REQUIRED_SECTIONS.get(artifact_type, [])
        if not required:
            return

        # 提取所有 Markdown 标题
        headings = [h.strip().lower() for h in re.findall(r'^#{1,6}\s+(.+)$', content, re.M)]
        text_lower = content.lower()

        missing: list[str] = []
        for kw in required:
            kw_lower = kw.lower()
            # 标题命中或正文出现该关键词即视为存在
            if kw_lower in text_lower:
                continue
            if any(kw_lower in h for h in headings):
                continue
            missing.append(kw)

        if missing:
            report.issues.append(
                ArtifactIssue(
                    "warning",
                    "structure",
                    f"可能缺少必需章节关键词: {', '.join(missing)}",
                )
            )

    # ── 2. 数字自洽 ──────────────────────────────────

    def _check_numeric_consistency(self, content: str, report: ArtifactReport) -> None:
        report.checks_run.append("numeric")
        # 匹配 "名称[:：=]\s*数值(单位)" 模式，检测同名指标出现多个不同数值
        pattern = re.compile(
            r'([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z_0-9]*)\s*[:：=]\s*(-?\d+(?:\.\d+)?)\s*(%|ms|s|分|个|条|次)?',
            re.M,
        )
        values_by_name: dict[str, set[str]] = {}
        for name, value, unit in pattern.findall(content):
            # 跳过单/双字母 ASCII 变量（x、y、n、i、f 等），
            # 它们是数学/程序变量而非指标名，避免误报
            if len(name) <= 2 and name.isascii() and name.isalpha():
                continue
            key = name.lower()
            values_by_name.setdefault(key, set()).add(f"{value}{unit or ''}")

        conflicts = []
        for name, vals in values_by_name.items():
            if len(vals) > 1:
                conflicts.append(f"{name}: {' vs '.join(sorted(vals))}")

        if conflicts:
            report.issues.append(
                ArtifactIssue(
                    "warning",
                    "numeric",
                    f"同名指标出现多个不同数值，请核对: {'; '.join(conflicts[:5])}",
                )
            )

    # ── 3. 引用可追溯 ──────────────────────────────────

    def _check_references(
        self, content: str, references: list[str] | None, report: ArtifactReport
    ) -> None:
        report.checks_run.append("reference")
        if not references:
            return  # 未提供参考列表，跳过

        # 提取 [n] 或 [标签] 形式的引用标记
        cite_marks = set(re.findall(r'\[(\d{1,3})\](?!\()', content))
        # 也提取 [Author, Year] 或 (Author, 2020) 形式
        author_year = set(re.findall(r'\(([A-Z][A-Za-z]+(?:\s+et\s+al\.)?,\s*\d{4})\)', content))

        ref_norm = {r.strip().lower() for r in references}

        missing = []
        for mark in cite_marks:
            # 数字引用检查：references 数量是否覆盖
            try:
                idx = int(mark)
                if idx > len(references):
                    missing.append(f"[{mark}]")
            except ValueError:
                pass

        for ay in author_year:
            if ay.lower() not in ref_norm and not any(ay.lower() in r for r in ref_norm):
                missing.append(f"({ay})")

        if missing:
            report.issues.append(
                ArtifactIssue(
                    "warning",
                    "reference",
                    f"文中引用无法在参考列表定位: {', '.join(missing[:5])}",
                )
            )

    # ── 4. 可解析性 ──────────────────────────────────

    def _check_parsability(self, content: str, artifact_type: str, report: ArtifactReport) -> None:
        report.checks_run.append("parsability")

        # JSON 产物
        if artifact_type == "json":
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                report.issues.append(
                    ArtifactIssue("error", "parsability", f"JSON 解析失败: {exc}")
                )
            return

        # LaTeX 环境配对检查
        if artifact_type in ("latex", "paper", "research"):
            begins = re.findall(r'\\begin\{([^}]+)\}', content)
            ends = re.findall(r'\\end\{([^}]+)\}', content)
            from collections import Counter
            cb, ce = Counter(begins), Counter(ends)
            for env in set(list(cb.keys()) + list(ce.keys())):
                if cb.get(env, 0) != ce.get(env, 0):
                    report.issues.append(
                        ArtifactIssue(
                            "error",
                            "parsability",
                            f"LaTeX 环境 '{env}' 不配对: \\begin={cb.get(env, 0)}, \\end={ce.get(env, 0)}",
                        )
                    )

        # Markdown 表格列数一致性
        table_rows = re.findall(r'^\|(.+)\|\s*$', content, re.M)
        if len(table_rows) >= 2:
            col_counts = [row.count("|") for row in table_rows]
            if len(set(col_counts)) > 1:
                report.issues.append(
                    ArtifactIssue(
                        "warning",
                        "parsability",
                        f"Markdown 表格列数不一致: {col_counts}",
                    )
                )

    # ── 5. 执行痕迹检查（v2.0 借鉴 ReasFlow Hallucination Check）──

    def _check_execution_evidence(
        self, content: str, artifact_type: str, report: ArtifactReport
    ) -> None:
        """检查产物是否有"真实执行"的证据，防止伪造实验结果。

        借鉴 ReasFlow 的 Hallucination Check 硬规则：
        - 对声称有实验/结果的产物，检查结果文件引用 + 日志执行痕迹 + 具体数值；
        - 三者皆无 → error（疑似未真实执行）；
        - 有数值但缺文件/痕迹 → warning（建议补充证据）。
        """
        # 仅对实验/研究/论文/报告类产物检查
        if artifact_type not in ("research", "paper", "latex", "report"):
            return
        report.checks_run.append("execution_evidence")

        text = content.lower()

        # 1. 判断是否"声称有实验结果"
        claim_markers = [
            "实验结果", "实验", "准确率", "accuracy", "loss", "精度", "收敛",
            "convergence", "性能", "指标", "metric", "迭代", "结果", "result",
            "训练", "train", "验证", "evaluation", "基准", "benchmark",
        ]
        has_claim = any(m in text for m in claim_markers)
        if not has_claim:
            return  # 纯理论/综述类，不要求执行证据

        # 2. 检查执行证据（三类）
        file_ref_markers = [
            ".csv", ".json", ".txt", ".png", ".pdf", ".log",
            "results/", "data/", "logs/", "output/", "figure", "图", "表", "table",
        ]
        has_file_ref = any(m in text for m in file_ref_markers)

        exec_trace_markers = [
            "迭代", "epoch", "step", "耗时", "秒", "ms", "exit", "stack trace",
            "traceback", "运行", "执行", "print", "输出", "轮", "round",
        ]
        has_exec_trace = any(m in text for m in exec_trace_markers)

        has_numbers = bool(re.search(r'\d+\.\d+|\d+%', content))

        # 3. 硬规则 / 软规则
        if not has_file_ref and not has_exec_trace and not has_numbers:
            report.issues.append(
                ArtifactIssue(
                    "error",
                    "execution_evidence",
                    "声称有实验结果，但无任何执行证据（无结果文件引用、无日志执行痕迹、无具体数值），疑似未真实执行",
                )
            )
        elif not has_file_ref and not has_exec_trace:
            report.issues.append(
                ArtifactIssue(
                    "warning",
                    "execution_evidence",
                    "有数值数据但缺少结果文件引用与执行痕迹，建议补充证据",
                )
            )

    # ── 格式化 ──────────────────────────────────────────

    def format_report(self, report: ArtifactReport) -> str:
        """格式化为可读文本。"""
        icon = "✅" if report.passed else "❌"
        lines = [
            f"{icon} 产物校验报告（类型: {report.artifact_type}）",
            f"{'─'*40}",
            f"结论: {'通过' if report.passed else '未通过'} "
            f"（{len(report.errors)} 错误 / {len(report.warnings)} 警告）",
            f"已执行校验: {', '.join(report.checks_run)}",
        ]
        if report.issues:
            lines.append("")
            for issue in report.issues:
                tag = "🔴 必须修复" if issue.level == "error" else "🟡 建议优化"
                lines.append(f"  {tag} [{issue.dimension}] {issue.message}")
        else:
            lines.append("")
            lines.append("  未发现确定性错误。")
        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_validator = ArtifactValidator()


def validate_artifact(
    content: str,
    artifact_type: str = "report",
    references: list[str] | None = None,
) -> ArtifactReport:
    """便捷函数：校验产物。"""
    return _validator.validate(content, artifact_type, references)


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "artifact_validator",
        "description": (
            "产物确定性验证器。对研究/写作/分析产物做不依赖 LLM 的结构完整性、"
            "数字自洽、引用可追溯、可解析性校验，返回必须修复/建议优化两级清单。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要校验的产物内容文本",
                },
                "artifact_type": {
                    "type": "string",
                    "enum": ["report", "research", "article", "json", "latex", "paper"],
                    "description": "产物类型",
                    "default": "report",
                },
                "references": {
                    "type": "string",
                    "description": "参考来源列表 JSON 数组，如 '[\"source1\",\"source2\"]'",
                    "default": "",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
}


def execute_artifact_validator_tool(arguments: dict[str, Any]) -> str:
    """产物验证器工具入口。"""
    content = arguments.get("content", "")
    artifact_type = arguments.get("artifact_type", "report")
    references_raw = arguments.get("references", "")

    references = None
    if references_raw:
        try:
            references = json.loads(references_raw)
        except json.JSONDecodeError:
            references = None

    try:
        report = _validator.validate(content, artifact_type, references)
        return _validator.format_report(report)
    except Exception as exc:
        return f"产物验证器错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    sample = """# 研究报告

## 引言
本文研究某问题。

## 方法
使用某方法。

## 结论
结论如下：准确率 = 95%，准确率 = 87%。
"""
    rep = _validator.validate(sample, artifact_type="research")
    print(_validator.format_report(rep))
