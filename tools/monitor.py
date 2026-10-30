"""monitor — 自我监控与性能分析系统

监控所有工具调用的频次、响应时间、异常率，
生成性能报告和趋势分析。帮助 Agent 1 了解自身运行状况。
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
MONITOR_DATA_FILE = SANDBOX_DIR / "memory" / "monitor_data.json"

# ── 错误类型 ──────────────────────────────────────────────


class MonitorError(RuntimeError):
    """监控系统错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "monitor",
        "description": (
            "自我监控与性能分析系统。跟踪工具调用频次、响应时间、"
            "异常率等指标，生成性能报告。帮助了解自身运行状况。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "record",
                        "report",
                        "summary",
                        "top_tools",
                        "slow_tools",
                        "errors",
                        "reset",
                    ],
                    "description": (
                        "操作类型："
                        "record — 记录一次工具调用（内部使用）；"
                        "report — 生成完整监控报告；"
                        "summary — 简要状态摘要；"
                        "top_tools — 最常使用的工具排行；"
                        "slow_tools — 最慢的工具排行；"
                        "errors — 错误统计；"
                        "reset — 重置监控数据。"
                    ),
                },
                "tool_name": {
                    "type": "string",
                    "description": "工具名称（record 操作必需）",
                    "default": "",
                },
                "duration": {
                    "type": "number",
                    "description": "调用耗时（秒，record 操作可选）",
                    "default": 0.0,
                },
                "success": {
                    "type": "boolean",
                    "description": "调用是否成功（record 操作可选）",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制",
                    "default": 10,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 监控引擎 ──────────────────────────────────────────────


class Monitor:
    """自我监控引擎。"""

    def __init__(self, path: Path | None = None) -> None:
        # path 允许测试传入独立文件路径，隔离测试数据与生产数据
        self._path: Path = path or MONITOR_DATA_FILE
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载监控数据。"""
        if self._path.is_file():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = self._fresh_data()
        else:
            self._data = self._fresh_data()

    def _save(self) -> None:
        """保存监控数据到文件。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _fresh_data() -> dict[str, Any]:
        return {
            "total_calls": 0,
            "total_errors": 0,
            "start_time": time.time(),
            "tools": {},
            "recent_errors": [],
        }

    def record(self, tool_name: str, duration: float = 0.0, success: bool = True) -> str:
        """记录一次工具调用。"""
        if not tool_name:
            raise MonitorError("工具名称不能为空")

        self._data["total_calls"] += 1
        if not success:
            self._data["total_errors"] += 1

        # 按工具统计
        if tool_name not in self._data["tools"]:
            self._data["tools"][tool_name] = {
                "calls": 0,
                "errors": 0,
                "total_duration": 0.0,
                "max_duration": 0.0,
                "min_duration": float("inf"),
                "last_called": "",
            }

        t = self._data["tools"][tool_name]
        t["calls"] += 1
        if not success:
            t["errors"] += 1
        t["total_duration"] += duration
        t["max_duration"] = max(t["max_duration"], duration)
        t["min_duration"] = min(t["min_duration"], duration)
        t["last_called"] = datetime.now().strftime("%H:%M:%S")

        # 记录错误详情
        if not success:
            error_entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tool": tool_name,
                "duration": duration,
            }
            self._data["recent_errors"].append(error_entry)
            # 只保留最近 100 条错误
            if len(self._data["recent_errors"]) > 100:
                self._data["recent_errors"] = self._data["recent_errors"][-100:]

        self._save()
        return f"已记录 {tool_name} 调用（{'成功' if success else '失败'}，{duration*1000:.1f}ms）"

    def summary(self) -> str:
        """简要状态摘要。"""
        uptime = time.time() - self._data["start_time"]
        uptime_str = str(timedelta(seconds=int(uptime)))
        tools_count = len(self._data["tools"])
        error_rate = (
            self._data["total_errors"] / self._data["total_calls"] * 100
            if self._data["total_calls"] > 0 else 0
        )

        # 计算平均响应时间
        total_dur = sum(
            t["total_duration"] for t in self._data["tools"].values()
        )
        avg_dur = total_dur / self._data["total_calls"] * 1000 if self._data["total_calls"] > 0 else 0

        return (
            f"📊 Agent 1 运行摘要\n"
            f"{'='*35}\n"
            f"🕐 运行时间: {uptime_str}\n"
            f"📞 总调用次数: {self._data['total_calls']}\n"
            f"🔧 活跃工具数: {tools_count}\n"
            f"❌ 错误次数: {self._data['total_errors']} ({error_rate:.1f}%)\n"
            f"⚡ 平均响应: {avg_dur:.1f}ms"
        )

    def report(self) -> str:
        """生成完整监控报告。"""
        uptime = time.time() - self._data["start_time"]
        uptime_str = str(timedelta(seconds=int(uptime)))
        tools = self._data["tools"]

        error_rate = (
            self._data["total_errors"] / self._data["total_calls"] * 100
            if self._data["total_calls"] > 0 else 0
        )

        lines = [
            f"📊 Agent 1 性能监控报告",
            f"{'='*50}",
            f"报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"运行时长: {uptime_str}",
            f"总调用: {self._data['total_calls']} 次",
            f"总错误: {self._data['total_errors']} 次 ({error_rate:.1f}%)",
            f"活跃工具: {len(tools)} 个",
            "",
            "## 工具调用统计",
            f"{'工具':<20} {'调用数':>8} {'错误':>6} {'平均(ms)':>10} {'最慢(ms)':>10} {'最后调用':>10}",
            "-" * 64,
        ]

        for name in sorted(tools.keys()):
            t = tools[name]
            avg_ms = t["total_duration"] / t["calls"] * 1000 if t["calls"] > 0 else 0
            max_ms = t["max_duration"] * 1000
            error_str = f"{t['errors']}" if t["errors"] > 0 else "0"
            lines.append(
                f"{name:<20} {t['calls']:>8} {error_str:>6} "
                f"{avg_ms:>8.1f} {max_ms:>8.1f} {t['last_called']:>10}"
            )

        # 最近错误
        if self._data["recent_errors"]:
            lines.append("\n## 最近错误")
            for err in self._data["recent_errors"][-5:]:
                lines.append(f"  ❌ [{err['time']}] {err['tool']} ({err['duration']*1000:.1f}ms)")

        return "\n".join(lines)

    def top_tools(self, limit: int = 10) -> str:
        """最常使用的工具排行。"""
        tools = self._data["tools"]
        if not tools:
            return "暂无数据。"

        sorted_tools = sorted(tools.items(), key=lambda x: -x[1]["calls"])[:limit]

        lines = [f"🏆 最常用工具 TOP {min(limit, len(sorted_tools))}\n"]
        lines.append(f"{'排名':>4} {'工具':<20} {'调用数':>8} {'错误':>6}")
        lines.append("-" * 40)
        for i, (name, t) in enumerate(sorted_tools, 1):
            error_str = f"{t['errors']}" if t["errors"] > 0 else "0"
            lines.append(f"{i:>4} {name:<20} {t['calls']:>8} {error_str:>6}")

        return "\n".join(lines)

    def slow_tools(self, limit: int = 10) -> str:
        """最慢的工具排行。"""
        tools = self._data["tools"]
        if not tools:
            return "暂无数据。"

        # 按平均耗时排序
        with_avg = [
            (name, t, t["total_duration"] / t["calls"] * 1000)
            for name, t in tools.items() if t["calls"] > 0
        ]
        sorted_tools = sorted(with_avg, key=lambda x: -x[2])[:limit]

        lines = [f"🐢 最慢工具 TOP {min(limit, len(sorted_tools))}\n"]
        lines.append(f"{'排名':>4} {'工具':<20} {'平均(ms)':>10} {'最慢(ms)':>10} {'调用数':>8}")
        lines.append("-" * 52)
        for i, (name, t, avg_ms) in enumerate(sorted_tools, 1):
            max_ms = t["max_duration"] * 1000
            lines.append(f"{i:>4} {name:<20} {avg_ms:>8.1f} {max_ms:>8.1f} {t['calls']:>8}")

        return "\n".join(lines)

    def errors(self) -> str:
        """错误统计。"""
        if not self._data["total_errors"]:
            return "🎉 没有记录到任何错误！"

        # 按工具统计错误
        error_by_tool: dict[str, int] = {}
        for name, t in self._data["tools"].items():
            if t["errors"] > 0:
                error_by_tool[name] = t["errors"]

        lines = [
            f"❌ 错误统计（共 {self._data['total_errors']} 次）\n",
            "按工具分布:",
        ]
        for name, count in sorted(error_by_tool.items(), key=lambda x: -x[1]):
            lines.append(f"  {name}: {count} 次")

        lines.append(f"\n最近 {min(5, len(self._data['recent_errors']))} 条错误记录:")
        for err in self._data["recent_errors"][-5:]:
            lines.append(f"  [{err['time']}] {err['tool']}")

        return "\n".join(lines)

    def reset(self) -> str:
        """重置监控数据。"""
        self._data = self._fresh_data()
        self._save()
        return "🔄 监控数据已重置。"


# ── 全局实例 ──────────────────────────────────────────────

_monitor = Monitor()


def execute_monitor_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")
    tool_name = arguments.get("tool_name", "")
    duration = float(arguments.get("duration", 0.0))
    success = bool(arguments.get("success", True))
    limit = int(arguments.get("limit", 10))

    try:
        if action == "record":
            return _monitor.record(tool_name, duration, success)
        elif action == "summary":
            return _monitor.summary()
        elif action == "report":
            return _monitor.report()
        elif action == "top_tools":
            return _monitor.top_tools(limit)
        elif action == "slow_tools":
            return _monitor.slow_tools(limit)
        elif action == "errors":
            return _monitor.errors()
        elif action == "reset":
            return _monitor.reset()
        else:
            return f"未知操作: {action}"
    except MonitorError as exc:
        return f"监控错误: {exc}"
