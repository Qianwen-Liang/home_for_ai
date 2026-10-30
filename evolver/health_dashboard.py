"""
health_dashboard — 系统健康仪表盘 v1.0

聚合 self_check + monitor + safety_net 三个数据源，
输出统一的结构化健康报告和综合评分。

Evolver 会话启动时自动运行，提供系统健康快照。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ── 路径设置 ──────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
sys.path.insert(0, str(SANDBOX_DIR))

# ── 健康状态枚举 ──────────────────────────────────────────


class HealthStatus(Enum):
    HEALTHY = ("🟢 健康", 80, 100)
    DEGRADED = ("🟡 降级", 60, 79)
    UNSTABLE = ("🟠 不稳定", 40, 59)
    CRITICAL = ("🔴 危急", 0, 39)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def min_score(self) -> int:
        return self.value[1]

    @property
    def max_score(self) -> int:
        return self.value[2]

    @classmethod
    def from_score(cls, score: int) -> "HealthStatus":
        for status in cls:
            if status.min_score <= score <= status.max_score:
                return status
        return cls.CRITICAL


# ── 仪表盘引擎 ────────────────────────────────────────────


class HealthDashboard:
    """系统健康仪表盘 — 聚合三个自感知数据源。"""

    def __init__(self):
        self._self_check_result: str | None = None
        self._monitor_summary: str | None = None
        self._safety_status: str | None = None
        self._score: int = 0
        self._issues: list[str] = []
        self._warnings: list[str] = []

    # ── 数据采集 ────────────────────────────────────────

    def _collect_self_check(self) -> dict[str, Any]:
        """调用 self_check 获取模块健康数据。"""
        try:
            from tools.self_check import _checker
            result = _checker.check_all(verbose=False)
            self._self_check_result = result

            # 使用结构化数据精确统计（避免表头图标被误计为失败/警告）
            results = _checker.results
            passed = sum(1 for r in results if r.get("status") == "✅")
            warnings = sum(1 for r in results if r.get("status") in ("⚠️", "ℹ️"))
            failed = sum(1 for r in results if r.get("status") == "❌")

            return {
                "source": "self_check",
                "total": passed + warnings + failed,
                "passed": passed,
                "warnings": warnings,
                "failed": failed,
                "healthy": failed == 0,
            }
        except Exception as exc:
            self._issues.append(f"self_check 采集失败: {exc}")
            return {"source": "self_check", "error": str(exc), "healthy": False}

    def _collect_monitor(self) -> dict[str, Any]:
        """调用 monitor 获取性能摘要数据。"""
        try:
            from tools.monitor import _monitor

            summary = _monitor.summary()
            self._monitor_summary = summary

            # 从 monitor 内部数据提取指标
            data = _monitor._data
            total_calls = data.get("total_calls", 0)
            total_errors = data.get("total_errors", 0)
            tool_count = len(data.get("tools", {}))

            error_rate = (total_errors / total_calls * 100) if total_calls > 0 else 0

            # 计算平均响应时间
            total_dur = sum(
                t["total_duration"] for t in data.get("tools", {}).values()
            )
            avg_dur_ms = (
                total_dur / total_calls * 1000 if total_calls > 0 else 0
            )

            healthy = error_rate < 5.0 and avg_dur_ms < 500

            return {
                "source": "monitor",
                "total_calls": total_calls,
                "total_errors": total_errors,
                "error_rate": round(error_rate, 1),
                "tool_count": tool_count,
                "avg_response_ms": round(avg_dur_ms, 1),
                "has_data": total_calls > 0,   # 数据新鲜度：无调用记录时性能维度无法评估
                "healthy": healthy,
            }
        except Exception as exc:
            self._issues.append(f"monitor 采集失败: {exc}")
            return {"source": "monitor", "error": str(exc), "healthy": False}

    def _collect_safety(self) -> dict[str, Any]:
        """调用 safety_net 获取安全状态。"""
        try:
            from tools.safety_net import _safety

            # 直接读取内部数据
            data = _safety._data
            consecutive_errors = data.get("consecutive_errors", 0)
            total_events = data.get("total_events", 0)
            rescue_activated = data.get("rescue_activated", False)
            rescue_count = len(data.get("rescue_history", []))

            healthy = consecutive_errors < 3 and not rescue_activated

            return {
                "source": "safety_net",
                "total_events": total_events,
                "consecutive_errors": consecutive_errors,
                "rescue_activated": rescue_activated,
                "rescue_count": rescue_count,
                "healthy": healthy,
            }
        except Exception as exc:
            self._issues.append(f"safety_net 采集失败: {exc}")
            return {"source": "safety_net", "error": str(exc), "healthy": False}

    # ── 综合评分 ────────────────────────────────────────

    def _compute_score(self, results: list[dict[str, Any]]) -> int:
        """基于三个数据源计算综合健康评分 0-100。"""
        score = 100
        self._issues = []
        self._warnings = []

        for r in results:
            source = r.get("source", "unknown")

            if source == "self_check":
                if "error" in r:
                    score -= 30
                    self._issues.append("self_check 不可用")
                elif r.get("failed", 0) > 0:
                    score -= r["failed"] * 10
                    self._issues.append(
                        f"self_check: {r['failed']} 项检查失败"
                    )
                if r.get("warnings", 0) > 0:
                    score -= r["warnings"] * 2
                    self._warnings.append(
                        f"self_check: {r['warnings']} 项警告"
                    )

            elif source == "monitor":
                if "error" in r:
                    score -= 20
                    self._issues.append("monitor 不可用")
                elif not r.get("has_data", True):
                    # 无调用记录：不扣分，但标记性能维度"未知"（修复"无数据默认健康"盲区）
                    self._warnings.append(
                        "monitor 无调用记录（total_calls=0），性能维度无法评估"
                    )
                else:
                    error_rate = r.get("error_rate", 0)
                    if error_rate > 10:
                        score -= 25
                        self._issues.append(f"错误率过高: {error_rate}%")
                    elif error_rate > 5:
                        score -= 15
                        self._warnings.append(f"错误率偏高: {error_rate}%")

                    avg_ms = r.get("avg_response_ms", 0)
                    if avg_ms > 1000:
                        score -= 15
                        self._issues.append(f"平均响应过慢: {avg_ms}ms")
                    elif avg_ms > 500:
                        score -= 5
                        self._warnings.append(f"平均响应偏慢: {avg_ms}ms")

            elif source == "safety_net":
                if "error" in r:
                    score -= 20
                    self._issues.append("safety_net 不可用")
                else:
                    if r.get("rescue_activated"):
                        score -= 30
                        self._issues.append("自救流程已激活 — 系统可能处于异常状态")
                    consecutive = r.get("consecutive_errors", 0)
                    if consecutive >= 3:
                        score -= consecutive * 5
                        self._issues.append(
                            f"连续错误 {consecutive} 次"
                        )

        return max(0, min(100, score))

    # ── 公开接口 ────────────────────────────────────────

    def aggregate(self) -> HealthStatus:
        """执行一轮完整数据采集和评分。返回健康状态。"""
        results = [
            self._collect_self_check(),
            self._collect_monitor(),
            self._collect_safety(),
        ]
        self._score = self._compute_score(results)
        return HealthStatus.from_score(self._score)

    def score(self) -> int:
        """返回综合评分 0-100。需先调用 aggregate()。"""
        return self._score

    def alert(self) -> str | None:
        """评分低于阈值时返回告警消息，否则返回 None。"""
        status = HealthStatus.from_score(self._score)
        if status in (HealthStatus.CRITICAL, HealthStatus.UNSTABLE):
            return (
                f"🚨 系统健康告警: {status.label} (评分: {self._score}/100)\n"
                f"问题:\n" +
                "\n".join(f"  • {i}" for i in self._issues) +
                "\n\n建议立即执行 self_check 和 safety_net.activate_rescue"
            )
        elif status == HealthStatus.DEGRADED:
            return (
                f"⚠️ 系统健康提示: {status.label} (评分: {self._score}/100)\n"
                f"注意事项:\n" +
                "\n".join(f"  • {w}" for w in self._warnings)
            )
        return None

    def report(self) -> str:
        """生成 Markdown 格式的完整健康报告。"""
        status = HealthStatus.from_score(self._score)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# 🏥 Agent1 系统健康仪表盘",
            f"",
            f"**报告时间**: {now}",
            f"**健康状态**: {status.label}",
            f"**综合评分**: {self._score}/100",
            f"",
            f"---",
            f"",
            f"## 📊 数据源概览",
            f"",
        ]

        # self_check 结果
        if self._self_check_result:
            # 提取关键行
            sc_lines = self._self_check_result.split("\n")
            key_lines = [
                l for l in sc_lines
                if any(kw in l for kw in ["健康状态", "总检查项", "✅", "❌", "⚠️"])
                and "报告结束" not in l
            ]
            lines.append("### 🔧 模块自检 (self_check)")
            lines.append("```")
            for l in key_lines[:10]:
                if l.strip():
                    lines.append(l.strip())
            lines.append("```")
            lines.append("")

        # monitor 结果
        if self._monitor_summary:
            lines.append("### 📞 性能监控 (monitor)")
            lines.append("```")
            for l in self._monitor_summary.split("\n"):
                if l.strip():
                    lines.append(l.strip())
            lines.append("```")
            lines.append("")

        # safety_net 结果
        try:
            from tools.safety_net import _safety
            safety_status = _safety.status()
            lines.append("### 🛡️ 安全状态 (safety_net)")
            lines.append("```")
            for l in safety_status.split("\n")[:12]:
                if l.strip():
                    lines.append(l.strip())
            lines.append("```")
            lines.append("")
        except Exception:
            pass

        # 综合评估
        lines.append("---")
        lines.append("")
        lines.append("## 🎯 综合评估")
        lines.append("")

        if self._issues:
            lines.append("### 🔴 问题")
            for issue in self._issues:
                lines.append(f"- {issue}")
            lines.append("")

        if self._warnings:
            lines.append("### 🟡 警告")
            for warning in self._warnings:
                lines.append(f"- {warning}")
            lines.append("")

        if not self._issues and not self._warnings:
            lines.append("✅ 系统运行正常，未检测到问题。")

        lines.append("")
        lines.append("---")
        lines.append(f"*由 health_dashboard v1.0 生成*")

        return "\n".join(lines)

    def quick_check(self) -> str:
        """快速检查 — 仅返回一句话健康摘要。"""
        status = HealthStatus.from_score(self._score)
        parts = [f"{status.label} (评分: {self._score}/100)"]
        if self._issues:
            parts.append(f"问题: {len(self._issues)} 个")
        if self._warnings:
            parts.append(f"警告: {len(self._warnings)} 个")
        return " | ".join(parts)


# ── 全局单例 ───────────────────────────────────────────────

_dashboard = HealthDashboard()


# ── 工具函数 ──────────────────────────────────────────────


def execute_health_dashboard_tool(arguments: dict[str, Any]) -> str:
    """健康仪表盘工具入口。"""
    action = arguments.get("action", "report")

    try:
        if action == "report":
            _dashboard.aggregate()
            return _dashboard.report()
        elif action == "quick":
            _dashboard.aggregate()
            alert = _dashboard.alert()
            if alert:
                return alert
            return _dashboard.quick_check()
        elif action == "score":
            _dashboard.aggregate()
            status = _dashboard.aggregate()
            return f"健康评分: {_dashboard.score()}/100 ({status.label})"
        elif action == "alert":
            _dashboard.aggregate()
            alert = _dashboard.alert()
            return alert or "✅ 系统正常，无告警。"
        else:
            return f"未知操作: {action}。可用: report, quick, score, alert"
    except Exception as exc:
        return f"健康仪表盘错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "health_dashboard",
        "description": (
            "系统健康仪表盘。聚合 self_check + monitor + safety_net "
            "三个数据源，输出统一的结构化健康报告和综合评分(0-100)。"
            "支持快速检查、完整报告、告警检测。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["report", "quick", "score", "alert"],
                    "description": (
                        "操作类型：report — 完整报告；"
                        "quick — 快速摘要+告警；"
                        "score — 仅评分；"
                        "alert — 仅告警检测"
                    ),
                    "default": "report",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    _dashboard.aggregate()
    print(f"Score: {_dashboard.score()}")
    print(_dashboard.quick_check())
    print()
    print(_dashboard.report())
