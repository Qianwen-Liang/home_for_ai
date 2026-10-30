"""Conversation state and terminal I/O for the local agent."""

from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.read import ReadToolError, execute_read_tool
from core.write import WriteToolError, execute_write_tool
from tools.runner import (
    RunnerError,
    run_command as runner_run_command,
)


@dataclass
class Conversation:
    """Keep the messages sent to and received from the language model."""

    system_prompt: str
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_assistant_tool_request(self, message: dict[str, Any]) -> None:
        self.messages.append(deepcopy(message))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": content,
            }
        )

    def api_messages(self) -> list[dict[str, Any]]:
        messages = deepcopy(self.messages)
        repaired = self._repair_orphan_tool_calls(messages)
        return [
            {"role": "system", "content": self.system_prompt},
            *repaired,
        ]

    @staticmethod
    def _placeholder_tool_message(tool_call_id: str, name: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": "（系统占位回执：该工具调用未正常执行，请忽略并继续。）",
        }

    @staticmethod
    def _repair_orphan_tool_calls(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """检测并修复孤儿 tool_calls：为缺失回执的 tool_call 注入占位 tool 消息。

        某些异常路径（工具调用参数非法抛异常）可能在写入 assistant 的
        tool_calls 消息后，未补上对应的 tool 回执，导致后续 API 请求因
        "insufficient tool messages following tool_calls message" 被 400 拒绝。
        这里在发送前统一兜底，保证每个 tool_call_id 都有紧跟其后的回执。
        """
        repaired: list[dict[str, Any]] = []
        pending: dict[str, str] = {}  # tool_call_id -> name（保持登记顺序）

        def _flush_pending() -> None:
            for tc_id, name in pending.items():
                repaired.append(
                    Conversation._placeholder_tool_message(tc_id, name)
                )
            pending.clear()

        for msg in messages:
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                # 结算上一批残留的孤儿（防御式，正常不应发生）
                _flush_pending()
                # 登记本消息的所有 tool_calls
                for tc in msg.get("tool_calls", []):
                    if not isinstance(tc, dict):
                        continue
                    tc_id = tc.get("id")
                    if not isinstance(tc_id, str) or not tc_id:
                        continue
                    fn = tc.get("function")
                    name = "unknown"
                    if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                        name = fn["name"]
                    pending[tc_id] = name
                repaired.append(msg)
            elif role == "tool":
                tc_id = msg.get("tool_call_id")
                if isinstance(tc_id, str):
                    pending.pop(tc_id, None)
                repaired.append(msg)
            else:
                # user 或纯文本 assistant：tool_calls 的回执必须紧跟其后，
                # 因此先补齐所有未回执的孤儿再插入该消息。
                _flush_pending()
                repaired.append(msg)

        # 末尾残留的孤儿
        _flush_pending()
        return repaired

    def clear(self) -> None:
        self.messages.clear()

    def save(self, path: Path) -> None:
        data: dict[str, Any] = {
            "system_prompt": self.system_prompt,
            "messages": self.messages,
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class StreamPrinter:
    """
    流式输出打印机。
    
    负责在终端上实时显示：
    - 🧠 模型的思考过程（逐字输出）
    - 🔧 工具调用（名称+参数）
    - ✅ 工具执行结果
    - 📝 最终回复
    """

    # 颜色代码
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CLEAR_LINE = "\033[2K\r"

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._current_line = ""
        self._in_tool_call = False

    def _write(self, text: str, end: str = "") -> None:
        """写入文本到终端。"""
        if self._enabled:
            print(text, end=end, flush=True)

    def _color(self, text: str, color: str, bold: bool = False) -> str:
        """给文本加颜色。"""
        if bold:
            return f"{self.BOLD}{color}{text}{self.RESET}"
        return f"{color}{text}{self.RESET}"

    # ── 流式输出方法 ────────────────────────────────────

    def on_thinking_start(self) -> None:
        """开始思考。"""
        self._write(self._color("🧠 思考中 ", self.CYAN, bold=True))

    def on_thinking_chunk(self, chunk: str) -> None:
        """思考中的每个文本块。"""
        self._write(chunk, end="")

    def on_thinking_end(self) -> None:
        """思考结束。"""
        self._write("")

    def on_tool_call_start(self, tool_name: str, arguments: str) -> None:
        """工具调用开始。"""
        self._in_tool_call = True
        args_preview = arguments[:120] + "…" if len(arguments) > 120 else arguments
        self._write(
            f"\n{self._color('🔧 调用工具 ', self.YELLOW, bold=True)}"
            f"{self._color(tool_name, self.GREEN, bold=True)}"
        )
        self._write(f"\n  {self._color('参数', self.DIM)}: {args_preview}")

    def on_tool_call_result(self, tool_name: str, result: str) -> None:
        """工具调用结果。"""
        result_preview = result[:200].replace("\n", " ")
        if len(result) > 200:
            result_preview += "…"
        result_color = self.RED if result.startswith("错误") or result.startswith("❌") else self.GREEN
        self._write(
            f"\n  {self._color('结果', self.DIM)}: {self._color(result_preview, result_color)}"
        )

    def on_tool_call_end(self) -> None:
        """工具调用结束（准备下一步思考）。"""
        self._in_tool_call = False

    def on_final_output(self, text: str, already_streamed: bool = False) -> None:
        """显示最终输出；纯流式内容已显示时只补充完成标记。"""
        self._write(f"\n{self._color('='*50, self.DIM)}")
        if already_streamed:
            self._write(f"\n{self._color('📝 回复完成', self.BLUE, bold=True)}")
        else:
            self._write(f"\n{self._color('📝 回复', self.BLUE, bold=True)}\n")
            self._write(text)
        self._write(f"\n{self._color('='*50, self.DIM)}\n")

    def on_error(self, error_msg: str) -> None:
        """错误信息。"""
        self._write(f"\n{self._color('❌ 错误', self.RED, bold=True)}: {error_msg}\n")

    def on_notice(self, msg: str) -> None:
        """提示信息。"""
        self._write(f"\n{self._color('ℹ️', self.CYAN)} {msg}\n")


class TerminalInterface:
    """Exchange messages with the user through a command-line terminal."""

    def __init__(self, stream_enabled: bool = True) -> None:
        self.stream = StreamPrinter(enabled=stream_enabled)

    def show_welcome(self) -> None:
        self.stream._write(
            f"\n{self.stream._color('='*55, self.stream.DIM)}"
        )
        self.stream._write(
            f"\n{self.stream._color(' Agent 1 v4.0', self.stream.CYAN, bold=True)}"
            f"{self.stream._color(' — 流式输出模式已启用', self.stream.DIM)}"
        )
        self.stream._write(
            f"\n{self.stream._color('='*55, self.stream.DIM)}"
        )
        self.stream._write(
            "\n可使用 /read、/list、/write、/mkdir、/clear、/save、/restart、/exit\n"
        )

    def read_user_message(self) -> str | None:
        try:
            message = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        return message

    def show_assistant_message(self, content: str) -> None:
        self.stream.on_final_output(content)

    def show_notice(self, content: str) -> None:
        self.stream.on_notice(content)

    def show_error(self, content: str) -> None:
        self.stream.on_error(content)


def execute_direct_read_command(command: str) -> tuple[bool, str]:
    """Execute explicit /read and /list commands from the user."""

    name, separator, argument = command.strip().partition(" ")
    normalized = name.lower()
    if normalized not in {"/read", "/list"}:
        return False, ""

    try:
        if normalized == "/read":
            if not separator or not argument.strip():
                raise ReadToolError("用法: /read <文件路径>")
            result = execute_read_tool("read_file", {"path": argument.strip()})
        else:
            path = argument.strip() if separator and argument.strip() else "."
            result = execute_read_tool("list_directory", {"path": path})
    except ReadToolError as exc:
        return True, f"读取失败: {exc}"

    return True, result


def execute_direct_write_command(command: str) -> tuple[bool, str]:
    """Execute explicit /write and /mkdir commands from the user."""

    name, separator, argument = command.strip().partition(" ")
    normalized = name.lower()
    if normalized not in {"/write", "/mkdir"}:
        return False, ""

    try:
        if normalized == "/mkdir":
            if not separator or not argument.strip():
                raise WriteToolError("用法: /mkdir <目录路径>")
            result = execute_write_tool(
                "make_directory", {"path": argument.strip()}
            )
        else:
            path, content_separator, content = argument.partition("::")
            if not separator or not content_separator or not path.strip():
                raise WriteToolError("用法: /write <文件路径> :: <文件内容>")
            result = execute_write_tool(
                "write_file",
                {"path": path.strip(), "content": content.lstrip()},
            )
    except WriteToolError as exc:
        return True, f"写入失败: {exc}"

    return True, result


def execute_direct_command_control(command: str) -> tuple[bool, str]:
    """Handle configuration-related command controls."""
    normalized = command.lower().strip()
    if normalized in {"/run", "/approve", "/deny", "/pending"}:
        return True, "已迁移到直接执行模式：使用 run_command 工具即可自动执行命令，无需 /approve 流程。"
    return False, ""
