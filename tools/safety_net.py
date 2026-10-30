"""safety_net — 循环检测与自救机制

检测连续相同错误、死循环、异常模式，并在检测到危险时
自动触发自救流程。读取 supervision/clue.md 获取监护人线索。
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
SAFETY_FILE = SANDBOX_DIR / "memory" / "safety_data.json"

# ── 错误类型 ──────────────────────────────────────────────


class SafetyNetError(RuntimeError):
    """安全网系统错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "safety_net",
        "description": (
            "循环检测与自救机制。检测连续相同错误、重复操作、"
            "异常模式，并在检测到危险时触发自救流程。"
            "读取 supervision/clue.md 获取监护人的提示线索。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "check",
                        "record_event",
                        "status",
                        "reset",
                        "read_clue",
                        "activate_rescue",
                        "auto_trigger_repair",
                    ],
                    "description": (
                        "操作类型："
                        "check — 检查当前状态，检测是否陷入循环或异常；"
                        "record_event — 记录一次事件（工具调用、错误等）；"
                        "status — 查看安全网状态；"
                        "reset — 重置安全网数据；"
                        "read_clue — 读取 supervision/clue.md 获取线索；"
                        "activate_rescue — 手动触发自救流程；"
                        "auto_trigger_repair — 自动触发离线修复流水线（基于最近存储的 traceback）。"
                    ),
                },
                "event_type": {
                    "type": "string",
                    "description": "事件类型：'tool_call'、'error'、'repeat'、'other'",
                    "default": "other",
                },
                "event_detail": {
                    "type": "string",
                    "description": "事件详情描述",
                    "default": "",
                },
                "tool_name": {
                    "type": "string",
                    "description": "涉及的工具名称",
                    "default": "",
                },
                "auto_execute": {
                    "type": "boolean",
                    "description": "是否自动执行修复任务（默认 false，仅创建不执行）",
                    "default": False,
                },
                "auto_apply": {
                    "type": "boolean",
                    "description": "是否自动应用修复补丁（默认 false，安全优先）",
                    "default": False,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 安全网配置 ────────────────────────────────────────────

# 触发自救的阈值
MAX_CONSECUTIVE_ERRORS = 5  # 连续错误次数
MAX_REPEATED_TOOL_CALLS = 8  # 同一工具的连续调用次数
MAX_SAME_ERROR_IN_WINDOW = 3  # 时间窗口内相同错误次数
ERROR_WINDOW_SECONDS = 60  # 错误统计时间窗口（秒）
MAX_TOTAL_EVENTS_WITHOUT_PROGRESS = 20  # 无进展的最大事件数


# ── 安全网引擎 ────────────────────────────────────────────


class SafetyNet:
    """循环检测与自救引擎。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._clue_cache: str | None = None
        self._load()

    def _load(self) -> None:
        """从文件加载安全网数据。"""
        if SAFETY_FILE.is_file():
            try:
                self._data = json.loads(SAFETY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = self._fresh_data()
        else:
            self._data = self._fresh_data()

    def _save(self) -> None:
        """保存安全网数据到文件。"""
        SAFETY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SAFETY_FILE.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _fresh_data() -> dict[str, Any]:
        return {
            "total_events": 0,
            "consecutive_errors": 0,
            "last_event_time": 0.0,
            "last_event_type": "",
            "last_error": "",
            "recent_events": [],  # 最近事件（最多 50 条）
            "tool_call_sequence": [],  # 工具调用序列
            "error_count_in_window": {},  # 时间窗口内错误计数
            "window_start_time": time.time(),
            "rescue_activated": False,
            "rescue_history": [],
            "traceback_storage": [],  # 最近 10 条 traceback（含时间戳）
        }

    # ── 公开接口 ────────────────────────────────────────

    def record_event(self, event_type: str = "other", event_detail: str = "", tool_name: str = "") -> str:
        """记录一次事件。"""
        now = time.time()
        self._data["total_events"] += 1
        self._data["last_event_time"] = now
        self._data["last_event_type"] = event_type

        event = {
            "time": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            "type": event_type,
            "detail": event_detail[:100] if event_detail else "",
            "tool": tool_name,
        }

        # 维护最近事件列表
        self._data["recent_events"].append(event)
        if len(self._data["recent_events"]) > 50:
            self._data["recent_events"] = self._data["recent_events"][-50:]

        # 工具调用序列
        if tool_name:
            self._data["tool_call_sequence"].append(tool_name)
            if len(self._data["tool_call_sequence"]) > 30:
                self._data["tool_call_sequence"] = self._data["tool_call_sequence"][-30:]

        # 错误处理
        if event_type == "error":
            self._data["consecutive_errors"] += 1
            self._data["last_error"] = event_detail[:200] if event_detail else ""

            # 时间窗口内错误计数
            self._clean_error_window(now)
            error_key = event_detail[:50] if event_detail else "unknown"
            self._data["error_count_in_window"][error_key] = \
                self._data["error_count_in_window"].get(error_key, 0) + 1

            # ── 自动存储 traceback ──
            if event_detail and "Traceback (most recent call last)" in event_detail:
                tb_list = self._data.setdefault("traceback_storage", [])
                tb_list.append({
                    "time": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
                    "traceback": event_detail,
                    "error_key": error_key,
                })
                # 只保留最近 10 条
                if len(tb_list) > 10:
                    self._data["traceback_storage"] = tb_list[-10:]
        else:
            # 非错误事件重置连续错误计数
            self._data["consecutive_errors"] = 0

        self._save()
        return f"已记录 {event_type} 事件"

    def check(self) -> str:
        """检查当前状态，检测是否陷入循环或异常。"""
        now = time.time()
        issues: list[str] = []
        warnings: list[str] = []

        # ── 检查 1：连续错误 ──
        if self._data["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
            issues.append(
                f"🔴 严重: 连续 {self._data['consecutive_errors']} 次错误！"
                f"（阈值: {MAX_CONSECUTIVE_ERRORS}）"
            )

        # ── 检查 2：时间窗口内相同错误 ──
        self._clean_error_window(now)
        for error_key, count in self._data["error_count_in_window"].items():
            if count >= MAX_SAME_ERROR_IN_WINDOW:
                issues.append(
                    f"🔴 重复错误: 在 {ERROR_WINDOW_SECONDS} 秒内 "
                    f"相同错误出现 {count} 次: {error_key[:60]}"
                )

        # ── 检查 3：工具调用循环 ──
        seq = self._data["tool_call_sequence"]
        if len(seq) >= MAX_REPEATED_TOOL_CALLS:
            # 检测是否有重复模式
            last_tools = seq[-MAX_REPEATED_TOOL_CALLS:]
            if len(set(last_tools)) <= 2:  # 只有 1-2 个不同工具
                issues.append(
                    f"🔴 工具循环: 最近 {MAX_REPEATED_TOOL_CALLS} 次调用中 "
                    f"只使用了 {set(last_tools)}"
                )

        # ── 检查 4：总事件数过多无进展 ──
        if self._data["total_events"] >= MAX_TOTAL_EVENTS_WITHOUT_PROGRESS:
            # 检查是否有任何完成的任务
            warnings.append(
                f"🟡 注意: 已记录 {self._data['total_events']} 次事件，"
                f"请考虑是否取得进展"
            )

        # ── 生成报告 ──
        lines = [
            f"🛡️ Agent 1 安全网状态检查",
            f"{'='*50}",
            f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"总事件数: {self._data['total_events']}",
            f"连续错误: {self._data['consecutive_errors']}",
            f"自救已激活: {'是 ✅' if self._data.get('rescue_activated') else '否'}",
            "",
        ]

        if issues:
            lines.append(f"🚨 发现 {len(issues)} 个问题:")
            for issue in issues:
                lines.append(f"  {issue}")
            lines.append("")
            lines.append("💡 建议操作:")
            lines.append("  1. 使用 `safety_net` action=read_clue 读取监护人线索")
            lines.append("  2. 使用 `safety_net` action=activate_rescue 触发自救")
            lines.append("  3. 使用 `self_check` 进行健康检查")
            lines.append("")
            # ── 自动触发修复（安全模式：仅创建任务，不自动执行/应用）──
            lines.append("🔧 已自动触发修复流水线（安全模式）:")
            try:
                repair_msg = self.auto_trigger_repair(
                    auto_execute=False, auto_apply=False,
                )
                lines.append(repair_msg)
            except Exception as exc:
                lines.append(f"  ⚠️ 自动触发修复失败: {exc}")
        else:
            lines.append("✅ 一切正常，未检测到循环或异常模式。")

        if warnings:
            for w in warnings:
                lines.append(f"\n{w}")

        return "\n".join(lines)

    def status(self) -> str:
        """查看安全网状态摘要。"""
        now = time.time()
        self._clean_error_window(now)

        lines = [
            f"🛡️ 安全网状态",
            f"{'='*35}",
            f"总事件: {self._data['total_events']}",
            f"连续错误: {self._data['consecutive_errors']}/{MAX_CONSECUTIVE_ERRORS}",
            f"自救激活: {'是' if self._data.get('rescue_activated') else '否'}",
            f"最近事件: {len(self._data['recent_events'])} 条",
        ]

        if self._data["error_count_in_window"]:
            lines.append(f"时间窗口内错误类型: {len(self._data['error_count_in_window'])} 种")

        if self._data.get("rescue_history"):
            lines.append(f"自救历史: {len(self._data['rescue_history'])} 次")

        lines.append(f"\n最近 5 个事件:")
        for event in self._data["recent_events"][-5:]:
            icon = {"error": "❌", "tool_call": "📞", "other": "📝"}.get(event["type"], "•")
            tool_info = f" [{event['tool']}]" if event["tool"] else ""
            lines.append(f"  {icon} [{event['time']}]{tool_info} {event['detail'][:50]}")

        return "\n".join(lines)

    def read_clue(self) -> str:
        """读取 supervision/clue.md 获取监护人线索。"""
        clue_path = SANDBOX_DIR.parent / "supervision" / "clue.md"
        try:
            if clue_path.is_file():
                content = clue_path.read_text(encoding="utf-8")
                self._clue_cache = content
                # 记录读取线索事件
                self.record_event("other", "已读取 supervision/clue.md")
                return f"📜 监护人线索:\n\n{content}"
            else:
                return "⚠️ 未找到 supervision/clue.md 文件。暂无监护人线索。"
        except (OSError, UnicodeDecodeError) as exc:
            return f"错误: 无法读取线索文件: {exc}"

    def activate_rescue(self) -> str:
        """触发自救流程。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rescue_record = {
            "time": now,
            "reason": "",
            "actions_taken": [],
        }

        # 收集异常信息
        issues = []
        if self._data["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
            reason = f"连续 {self._data['consecutive_errors']} 次错误"
            issues.append(reason)
            rescue_record["reason"] = reason

        # 读取线索
        clue_path = SANDBOX_DIR.parent / "supervision" / "clue.md"
        clue_content = ""
        try:
            if clue_path.is_file():
                clue_content = clue_path.read_text(encoding="utf-8")
                rescue_record["actions_taken"].append("已读取 supervision/clue.md")
        except OSError:
            pass

        # 生成自救计划
        actions = [
            "🛟 自救流程已激活",
            f"时间: {now}",
            "",
        ]

        if issues:
            actions.append(f"触发原因: {'; '.join(issues)}")
            actions.append("")

        actions.extend([
            "📋 自救计划:",
            "",
            "  步骤 1 — 冷静分析",
            "    • 使用 `self_check` 进行健康检查",
            "    • 使用 `decision_engine` 获取决策建议",
            "",
            "  步骤 2 — 寻求线索",
            "    • 使用 `safety_net` action=read_clue 读取监护人提示",
        ])

        if clue_content and clue_content.strip() and "暂无" not in clue_content:
            # 有实际线索内容
            clue_lines = [l for l in clue_content.split("\n") if l.strip() and not l.startswith("#")]
            if clue_lines:
                actions.append(f"    • 监护人提示: {clue_lines[0][:100]}")

        actions.extend([
            "",
            "  步骤 3 — 采取行动",
            "    • 重置监视数据: `monitor` action=reset",
            "    • 如果工具异常: 检查 tools/*.py 是否有语法错误",
            "    • 如果是逻辑循环: 重新规划下一步行动",
            "",
            "  步骤 4 — 请求帮助",
            "    • 如无法自行解决，向监护人描述当前困境",
            "    • 说明已尝试的解决方案",
        ])

        # 记录自救历史
        self._data["rescue_activated"] = True
        self._data["rescue_history"].append(rescue_record)
        if len(self._data["rescue_history"]) > 10:
            self._data["rescue_history"] = self._data["rescue_history"][-10:]

        # 重置计数
        self._data["consecutive_errors"] = 0
        self._data["error_count_in_window"] = {}
        self._data["window_start_time"] = time.time()
        self._save()

        return "\n".join(actions)

    def auto_trigger_repair(
        self,
        auto_execute: bool = False,
        auto_apply: bool = False,
    ) -> str:
        """
        自动触发离线修复流水线（safety_net → offline_runner 桥接）。

        从 traceback_storage 中取出最近一条 traceback，
        创建离线修复任务（诊断→计划→备份→修复→验证），
        可选自动执行。

        Args:
            auto_execute: 是否自动执行修复任务（默认 False，安全优先）
            auto_apply: 是否自动应用修复补丁（默认 False，需人工确认）

        Returns:
            操作结果描述（含任务 ID 和执行指令）
        """
        tb_list = self._data.get("traceback_storage", [])
        if not tb_list:
            return (
                "ℹ️ 没有可用的 traceback，无法自动触发修复。\n"
                "💡 请先通过 safety_net action=record_event event_type=error "
                "event_detail='<traceback>' 存储异常信息。"
            )

        latest = tb_list[-1]
        traceback_text = latest.get("traceback", "")
        captured_time = latest.get("time", "未知")

        if not traceback_text or "Traceback" not in traceback_text:
            return "ℹ️ 最近存储的错误不包含有效 traceback。"

        # ── 延迟导入（避免循环依赖）──
        try:
            from .repair_executors import create_repair_offline_task
            from .offline_runner import _manager as offline_manager
        except ImportError as exc:
            return f"❌ 无法导入修复模块: {exc}"

        # ── 第一步：创建离线修复任务 ──
        task_info = create_repair_offline_task(
            traceback_text=traceback_text,
            auto_apply=auto_apply,
            error_source="safety_net_auto",
        )

        submit_result = offline_manager.submit(
            title=task_info["title"],
            description=task_info.get("description", ""),
            params=task_info["params"],
            phases=task_info["phases"],
        )

        # 从 submit 结果中提取 task_id
        import re
        tid_match = re.search(r"任务ID:\s+(OT-\d+)", submit_result)
        task_id = tid_match.group(1) if tid_match else "未知"

        # 记录自救事件
        self.record_event(
            "other",
            f"auto_trigger_repair: 创建修复任务 {task_id} (captured: {captured_time})",
            "safety_net",
        )

        lines = [
            "🔧 自动修复桥接已触发",
            f"{'─'*50}",
            f"任务ID:   {task_id}",
            f"异常捕获: {captured_time}",
            f"自动执行: {'是' if auto_execute else '否'}",
            f"自动应用: {'是' if auto_apply else '否（安全模式）'}",
        ]

        # ── 第二步：可选自动执行 ──
        if auto_execute:
            try:
                from .executor_registry import _registry
                exec_result = offline_manager.execute(
                    task_id=task_id,
                    phase_executor=_registry.get_executor_for_runner(),
                )
                lines.append(f"\n{exec_result}")
            except Exception as exc:
                lines.append(f"\n⚠️ 自动执行失败: {exc}")
                lines.append(f"💡 可手动执行: offline action=execute task_id={task_id}")
        else:
            lines.append(f"\n💡 手动执行: offline action=execute task_id={task_id}")

        return "\n".join(lines)

    def get_stored_tracebacks(self) -> str:
        """查看已存储的 traceback 列表。"""
        tb_list = self._data.get("traceback_storage", [])
        if not tb_list:
            return "📭 traceback 存储为空。"

        lines = [f"📋 已存储的 traceback（最近 {len(tb_list)} 条）:", f"{'─'*45}"]
        for i, tb in enumerate(reversed(tb_list), 1):
            tb_preview = tb.get("traceback", "")[:120].replace("\n", " → ")
            lines.append(f"  {i}. [{tb.get('time', '?')}] {tb.get('error_key', '?')}")
            lines.append(f"     {tb_preview}...")
        return "\n".join(lines)

    def reset(self) -> str:
        """重置安全网数据。"""
        self._data = self._fresh_data()
        self._save()
        return "🔄 安全网数据已重置。"

    # ── 内部方法 ────────────────────────────────────────

    def _clean_error_window(self, now: float) -> None:
        """清理超出时间窗口的错误计数。"""
        if now - self._data.get("window_start_time", now) > ERROR_WINDOW_SECONDS:
            self._data["error_count_in_window"] = {}
            self._data["window_start_time"] = now


# ── 全局实例 ──────────────────────────────────────────────

_safety = SafetyNet()


def execute_safety_net_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")
    event_type = arguments.get("event_type", "other")
    event_detail = arguments.get("event_detail", "")
    tool_name = arguments.get("tool_name", "")
    auto_execute = arguments.get("auto_execute", False)
    auto_apply = arguments.get("auto_apply", False)

    try:
        if action == "check":
            return _safety.check()
        elif action == "record_event":
            return _safety.record_event(event_type, event_detail, tool_name)
        elif action == "status":
            return _safety.status()
        elif action == "read_clue":
            return _safety.read_clue()
        elif action == "activate_rescue":
            return _safety.activate_rescue()
        elif action == "auto_trigger_repair":
            return _safety.auto_trigger_repair(
                auto_execute=auto_execute,
                auto_apply=auto_apply,
            )
        elif action == "reset":
            return _safety.reset()
        else:
            return f"未知操作: {action}"
    except SafetyNetError as exc:
        return f"安全网错误: {exc}"
