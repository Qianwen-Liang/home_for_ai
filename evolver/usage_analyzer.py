"""
usage_analyzer — 使用模式分析器 v1.0

基于 monitor 累积的历史数据，自动识别:
  - 热点工具（高频调用 → 应优化）
  - 冷门工具（低频/零调用 → 可淘汰或合并）
  - 性能瓶颈（响应慢的工具）
  - 调用趋势（上升/下降模式）

定期分析生成"系统瘦身建议"，帮助 Evolver 做出数据驱动的优化决策。
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ── 路径设置 ──────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
sys.path.insert(0, str(SANDBOX_DIR))

ANALYSIS_LOG = EVOLVER_DIR / "usage_analysis.json"

# ── 分析引擎 ──────────────────────────────────────────────


class UsageAnalyzer:
    """使用模式分析器 — 挖掘 monitor 数据提供优化建议。"""

    def __init__(self):
        self._raw_data: dict[str, Any] = {}
        self._analysis: dict[str, Any] = {}

    # ── 数据加载 ────────────────────────────────────────

    def load_data(self) -> dict[str, Any]:
        """从 monitor 加载原始数据。"""
        try:
            from tools.monitor import _monitor
            self._raw_data = _monitor._data
            return self._raw_data
        except Exception as exc:
            return {"error": f"无法加载 monitor 数据: {exc}"}

    # ── 热点分析 ────────────────────────────────────────

    def hot_spot_analysis(self, top_n: int = 10) -> list[dict[str, Any]]:
        """识别 Top-N 热点工具（按调用频次）。"""
        tools = self._raw_data.get("tools", {})
        if not tools:
            return []

        sorted_tools = sorted(
            tools.items(),
            key=lambda x: -x[1].get("calls", 0)
        )

        results = []
        for name, data in sorted_tools[:top_n]:
            calls = data.get("calls", 0)
            errors = data.get("errors", 0)
            avg_ms = (
                data.get("total_duration", 0) / calls * 1000
                if calls > 0 else 0
            )
            error_rate = (errors / calls * 100) if calls > 0 else 0

            results.append({
                "tool": name,
                "calls": calls,
                "errors": errors,
                "error_rate": round(error_rate, 1),
                "avg_ms": round(avg_ms, 1),
                "last_called": data.get("last_called", ""),
            })

        return results

    # ── 冷门分析 ────────────────────────────────────────

    def cold_spot_analysis(self) -> list[dict[str, Any]]:
        """识别冷门工具 — 低频或从未调用的工具。

        对比 monitor 中的工具和所有已注册工具，找出:
        - 零调用工具（注册了但从没被用过）
        - 低频工具（调用次数低于平均值 10% 的工具）
        """
        tools = self._raw_data.get("tools", {})

        # 获取所有已注册工具
        all_registered = self._get_registered_tools()
        monitored_tools = set(tools.keys())

        results = []

        # 1. 零调用工具
        for tool_name in all_registered:
            if tool_name not in monitored_tools:
                results.append({
                    "tool": tool_name,
                    "calls": 0,
                    "status": "zero_calls",
                    "suggestion": "从未被调用，考虑是否仍需要此工具",
                })

        # 2. 低频工具
        if tools:
            total_calls = sum(t.get("calls", 0) for t in tools.values())
            avg_calls = total_calls / len(tools) if tools else 0
            threshold = max(avg_calls * 0.1, 1)  # 至少 1 次

            for name, data in tools.items():
                calls = data.get("calls", 0)
                if 0 < calls < threshold:
                    results.append({
                        "tool": name,
                        "calls": calls,
                        "avg_calls_all": round(avg_calls, 1),
                        "status": "low_usage",
                        "suggestion": f"调用次数 ({calls}) 远低于平均值 ({avg_calls:.1f})，考虑合并或优化",
                    })

        return results

    # ── 趋势分析 ────────────────────────────────────────

    def trend_analysis(self) -> list[dict[str, Any]]:
        """检测工具调用频次的趋势（上升/下降）。

        由于 monitor 当前只有聚合数据（没有时间序列），
        此方法基于 last_called 和调用频率估算趋势。
        未来如果有时间序列数据，可提供更精确的趋势检测。
        """
        tools = self._raw_data.get("tools", {})
        if not tools:
            return []

        total_calls = self._raw_data.get("total_calls", 1)
        results = []

        for name, data in tools.items():
            calls = data.get("calls", 0)
            pct = (calls / total_calls * 100) if total_calls > 0 else 0

            # 基于调用占比进行趋势判断
            if pct > 20:
                trend = "up"
                label = "📈 上升"
                suggestion = "高频工具，考虑性能优化和缓存策略"
            elif pct > 5:
                trend = "stable"
                label = "➡️ 稳定"
                suggestion = "使用正常"
            elif pct > 0:
                trend = "down"
                label = "📉 低速"
                suggestion = "使用频率较低，观察是否需要保留"
            else:
                trend = "idle"
                label = "⏸️ 闲置"
                suggestion = "长期未使用"

            results.append({
                "tool": name,
                "calls": calls,
                "pct_of_total": round(pct, 1),
                "trend": trend,
                "label": label,
                "suggestion": suggestion,
            })

        # 按调用数降序
        results.sort(key=lambda x: -x["calls"])
        return results

    # ── 瓶颈检测 ────────────────────────────────────────

    def bottleneck_detection(self, slow_threshold_ms: float = 500) -> list[dict[str, Any]]:
        """识别慢工具 — 响应时间超过阈值的工具。"""
        tools = self._raw_data.get("tools", {})
        if not tools:
            return []

        results = []
        for name, data in tools.items():
            calls = data.get("calls", 0)
            if calls == 0:
                continue

            avg_ms = data.get("total_duration", 0) / calls * 1000
            max_ms = data.get("max_duration", 0) * 1000

            if avg_ms > slow_threshold_ms or max_ms > slow_threshold_ms * 2:
                severity = (
                    "critical" if avg_ms > slow_threshold_ms * 2 else
                    "warning" if avg_ms > slow_threshold_ms else "info"
                )
                icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(severity, "•")

                results.append({
                    "tool": name,
                    "avg_ms": round(avg_ms, 1),
                    "max_ms": round(max_ms, 1),
                    "calls": calls,
                    "severity": severity,
                    "icon": icon,
                    "suggestion": self._bottleneck_suggestion(name, avg_ms),
                })

        results.sort(key=lambda x: -x["avg_ms"])
        return results

    def _bottleneck_suggestion(self, tool_name: str, avg_ms: float) -> str:
        """为慢工具生成优化建议。"""
        suggestions = {
            "web_search": "网络 I/O 是固有延迟，考虑增加结果缓存 (TTL 5min)",
            "knowledge": "检查知识库索引是否需要重建 (reindex)，或条目数过多需分片",
            "file_utils": "文件扫描耗时，考虑缩小扫描范围或异步执行",
            "self_check": "检查频率是否需要降低，或改为增量检查",
            "test_runner": "测试执行本身耗时长，考虑并行运行",
        }

        for key, suggestion in suggestions.items():
            if key in tool_name:
                return suggestion

        if avg_ms > 1000:
            return f"平均响应 {avg_ms:.0f}ms 严重超标，建议: 添加超时控制、异步执行或结果缓存"
        elif avg_ms > 500:
            return f"平均响应 {avg_ms:.0f}ms 偏高，建议: 分析耗时环节并优化"
        return "响应时间略高于阈值，持续观察"

    # ── 综合报告 ────────────────────────────────────────

    def report(self) -> str:
        """生成完整的使用模式分析报告。"""
        self.load_data()

        hot = self.hot_spot_analysis(5)
        cold = self.cold_spot_analysis()
        trends = self.trend_analysis()
        bottlenecks = self.bottleneck_detection()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_calls = self._raw_data.get("total_calls", 0)
        total_errors = self._raw_data.get("total_errors", 0)
        tool_count = len(self._raw_data.get("tools", {}))
        error_rate = (total_errors / total_calls * 100) if total_calls > 0 else 0

        lines = [
            f"# 📊 Agent1 使用模式分析报告",
            f"",
            f"**分析时间**: {now}",
            f"**数据基线**: {total_calls} 次调用 | {tool_count} 个工具 | {error_rate:.1f}% 错误率",
            f"",
            f"---",
            f"",
            f"## 🔥 热点工具 TOP 5",
            f"",
        ]

        if hot:
            lines.append("| 排名 | 工具 | 调用数 | 错误率 | 平均(ms) | 最后调用 |")
            lines.append("|------|------|--------|--------|----------|----------|")
            for i, h in enumerate(hot, 1):
                lines.append(
                    f"| {i} | `{h['tool']}` | {h['calls']} | "
                    f"{h['error_rate']}% | {h['avg_ms']} | {h['last_called']} |"
                )
        else:
            lines.append("暂无足够数据。")

        lines.extend(["", "## ❄️ 冷门工具"])
        if cold:
            for c in cold:
                icon = "🆕" if c["status"] == "zero_calls" else "🥶"
                lines.append(f"- {icon} **{c['tool']}**: {c['suggestion']}")
        else:
            lines.append("✅ 所有工具都在正常使用中。")

        lines.extend(["", "## 🐢 性能瓶颈"])
        if bottlenecks:
            for b in bottlenecks:
                lines.append(
                    f"- {b['icon']} **{b['tool']}**: 平均 {b['avg_ms']}ms, "
                    f"最慢 {b['max_ms']}ms ({b['calls']} 次调用)"
                )
                lines.append(f"  ↳ {b['suggestion']}")
        else:
            lines.append("✅ 未检测到性能瓶颈。")

        lines.extend(["", "## 📈 调用趋势"])
        if trends:
            # 仅显示有意义的趋势
            notable = [t for t in trends if t["trend"] in ("up", "idle")]
            for t in notable[:5]:
                lines.append(
                    f"- {t['label']} **{t['tool']}**: "
                    f"{t['calls']} 次 ({t['pct_of_total']}%) — {t['suggestion']}"
                )
            if not notable:
                lines.append("✅ 所有工具使用模式稳定。")
        else:
            lines.append("暂无趋势数据。")

        lines.extend([
            "",
            "---",
            "",
            "## 💡 优化建议",
            "",
        ])

        advice = self.optimization_advice()
        if advice:
            for a in advice:
                lines.append(f"- {a}")
        else:
            lines.append("✅ 当前无需特别优化。")

        lines.extend([
            "",
            "---",
            f"*由 usage_analyzer v1.0 生成*",
        ])

        return "\n".join(lines)

    def optimization_advice(self) -> list[str]:
        """生成可执行的优化建议列表。"""
        advice = []

        # 基于热点分析
        hot = self.hot_spot_analysis(5)
        if hot and hot[0]["error_rate"] > 10:
            advice.append(
                f"⚠️ 最高频工具 `{hot[0]['tool']}` 错误率 {hot[0]['error_rate']}%，"
                f"建议优先排查其稳定性"
            )

        # 基于冷门分析
        cold = self.cold_spot_analysis()
        zero_call = [c for c in cold if c["status"] == "zero_calls"]
        if len(zero_call) >= 2:
            names = [c["tool"] for c in zero_call]
            advice.append(
                f"🔧 {len(zero_call)} 个工具从未被调用 ({', '.join(names)})，"
                f"考虑从 TOOL_DEFINITION 中移除或标记为 deprecated"
            )

        low_usage = [c for c in cold if c["status"] == "low_usage"]
        if len(low_usage) >= 3:
            advice.append(
                f"📉 {len(low_usage)} 个工具调用频率极低，考虑合并相似功能或精简代码"
            )

        # 基于瓶颈分析
        bottlenecks = self.bottleneck_detection()
        critical = [b for b in bottlenecks if b["severity"] == "critical"]
        if critical:
            advice.append(
                f"🚨 {len(critical)} 个工具存在严重性能瓶颈，建议立即优化"
            )

        return advice

    def summary(self) -> str:
        """一句话摘要。"""
        self.load_data()
        hot = self.hot_spot_analysis(3)
        cold = self.cold_spot_analysis()
        bn = self.bottleneck_detection()

        parts = []
        if hot:
            parts.append(f"热点: {hot[0]['tool']}({hot[0]['calls']}次)")
        zero = [c for c in cold if c["status"] == "zero_calls"]
        if zero:
            parts.append(f"闲置: {len(zero)}个工具")
        critical = [b for b in bn if b["severity"] == "critical"]
        if critical:
            parts.append(f"瓶颈: {len(critical)}个")

        if not parts:
            return "✅ 系统使用模式正常"

        return " | ".join(parts)

    # ── 内部辅助 ────────────────────────────────────────

    def _get_registered_tools(self) -> list[str]:
        """获取所有已注册的工具名称。"""
        try:
            from agent1 import ALL_TOOLS
            return [t["function"]["name"] for t in ALL_TOOLS]
        except Exception:
            # 降级：从 tools/ 目录扫描
            tools_dir = SANDBOX_DIR / "tools"
            if tools_dir.is_dir():
                return [
                    f.stem for f in tools_dir.glob("*.py")
                    if not f.name.startswith("_") and f.name != "test_tools.py"
                ]
            return []

    def _save_analysis(self) -> None:
        """保存分析结果到磁盘。"""
        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hot_spots": self.hot_spot_analysis(5),
            "cold_spots": self.cold_spot_analysis(),
            "bottlenecks": self.bottleneck_detection(),
            "advice": self.optimization_advice(),
        }

        existing = []
        if ANALYSIS_LOG.is_file():
            try:
                existing = json.loads(ANALYSIS_LOG.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []

        existing.append(record)
        if len(existing) > 20:
            existing = existing[-20:]

        ANALYSIS_LOG.parent.mkdir(parents=True, exist_ok=True)
        ANALYSIS_LOG.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── 全局单例 ───────────────────────────────────────────────

_analyzer = UsageAnalyzer()


# ── 工具函数 ──────────────────────────────────────────────


def execute_usage_analyzer_tool(arguments: dict[str, Any]) -> str:
    """使用模式分析器工具入口。"""
    action = arguments.get("action", "report")

    try:
        if action == "report":
            return _analyzer.report()
        elif action == "summary":
            return _analyzer.summary()
        elif action == "hot_spots":
            top_n = int(arguments.get("top_n", 5))
            hot = _analyzer.hot_spot_analysis(top_n)
            if not hot:
                return "暂无数据。"
            lines = [f"🔥 热点工具 TOP {len(hot)}"]
            for i, h in enumerate(hot, 1):
                lines.append(
                    f"  {i}. {h['tool']}: {h['calls']} 次, "
                    f"{h['avg_ms']}ms, 错误率 {h['error_rate']}%"
                )
            return "\n".join(lines)
        elif action == "cold_spots":
            _analyzer.load_data()
            cold = _analyzer.cold_spot_analysis()
            if not cold:
                return "✅ 所有工具使用正常，无冷门工具。"
            lines = [f"❄️ 冷门工具 ({len(cold)} 个)"]
            for c in cold:
                lines.append(f"  • {c['tool']}: {c['suggestion']}")
            return "\n".join(lines)
        elif action == "bottlenecks":
            _analyzer.load_data()
            bn = _analyzer.bottleneck_detection(
                slow_threshold_ms=float(arguments.get("threshold_ms", 500))
            )
            if not bn:
                return "✅ 未检测到性能瓶颈。"
            lines = [f"🐢 性能瓶颈 ({len(bn)} 个)"]
            for b in bn:
                lines.append(
                    f"  {b['icon']} {b['tool']}: 平均 {b['avg_ms']}ms, "
                    f"最慢 {b['max_ms']}ms"
                )
            return "\n".join(lines)
        elif action == "advice":
            _analyzer.load_data()
            advice = _analyzer.optimization_advice()
            if not advice:
                return "✅ 当前无需特别优化。"
            return "💡 优化建议:\n" + "\n".join(f"  • {a}" for a in advice)
        else:
            return f"未知操作: {action}。可用: report, summary, hot_spots, cold_spots, bottlenecks, advice"

    except Exception as exc:
        return f"使用分析器错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "usage_analyzer",
        "description": (
            "使用模式分析器。基于 monitor 累积数据，识别热点工具、"
            "冷门工具、性能瓶颈和调用趋势，生成优化建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "report", "summary", "hot_spots",
                        "cold_spots", "bottlenecks", "advice",
                    ],
                    "description": (
                        "操作类型：report — 完整分析报告；"
                        "summary — 一句话摘要；"
                        "hot_spots — 热点工具排行；"
                        "cold_spots — 冷门工具识别；"
                        "bottlenecks — 性能瓶颈检测；"
                        "advice — 优化建议"
                    ),
                    "default": "report",
                },
                "top_n": {
                    "type": "integer",
                    "description": "热点工具排行数量",
                    "default": 5,
                },
                "threshold_ms": {
                    "type": "number",
                    "description": "性能瓶颈阈值（毫秒），默认 500",
                    "default": 500,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print(_analyzer.summary())
    print()
    print(_analyzer.report())
