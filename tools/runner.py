"""Shell command tool for Agent 1 — 直接执行模式，不再需要 /approve 确认。"""

from __future__ import annotations

import locale
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
MAX_COMMAND_LENGTH = 2_000

# ★T2798：子进程输出解码编码。
# Windows 上 cmd 内建命令与本机 python 均按本地代码页输出（中文系统为 cp936），
# 强制 utf-8 解码会把中文错误信息变成乱码，导致模型读到无效的失败原因。
# ★T2798：子进程输出智能解码。
# 单一编码无法覆盖：Windows 上 cmd 内建命令按本地代码页（中文为 cp936）输出，
# 而本机 python 在 UTF-8 模式下按 UTF-8 输出，同一进程内两种编码并存。
# 策略：先按 UTF-8 严格解码，失败则回退本地代码页，再失败用替换符。
def _smart_decode(data: bytes | str | None) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        return data
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


_SUBPROCESS_ENCODING = (
    "utf-8" if sys.platform != "win32"
    else (locale.getpreferredencoding(False) or "utf-8")
)

# 时限改为分档制：动态读取当前档位（tools/timeout_tier.json），
# 不再使用固定 MAX_TIMEOUT_SECONDS。基础档 120s，可自由切换。
try:
    from tools.timeout_tier import get_current_tier, BASE_TIER as _BASE_TIER
except ImportError:  # 兼容直接以脚本方式运行
    from timeout_tier import get_current_tier, BASE_TIER as _BASE_TIER

# ── 永久性路径解决方案 ──────────────────────────────────
# 所有通过 run_command 执行的命令自动继承以下环境变量，
# 确保 agent-sandbox 下的包（evolver、tools、memory 等）
# 无论 CWD 在哪里都能被 Python 正确导入。
_SANDBOX_PATH = str(SANDBOX_DIR)


def _build_env() -> dict[str, str]:
    """构建子进程环境，自动注入 agent-sandbox 到 PYTHONPATH。

    此函数确保：
    1. Python 导入路径始终包含 agent-sandbox（优先级最高）
    2. 保留已有的 PYTHONPATH 值（追加而非覆盖）
    3. 在不同操作系统上行为一致
    """
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = f"{_SANDBOX_PATH}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = _SANDBOX_PATH
    return env


class RunnerError(RuntimeError):
    """Raised when a command request is invalid."""


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": (
            "在 agent-sandbox 目录下执行 shell 命令。"
            "命令会自动执行，但必须遵守安全限制："
            "不能访问 .env、supervision 或工作区之外的路径。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令。"},
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 30 秒。上限为当前时限档位（分档制，基础 120s，可自由切换）。",
                    "default": 30,
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise RunnerError("命令不能为空")
    command = command.strip()
    if len(command) > MAX_COMMAND_LENGTH:
        raise RunnerError(f"命令超过 {MAX_COMMAND_LENGTH} 个字符")
    lowered = command.lower().replace("/", "\\")
    # ".env" 作为独立文件名（前后不能是标识符字符），避免误伤 os.environ / DEEPSEEK_API_KEY 等
    if re.search(r'(?<![A-Za-z0-9_])\.env(?![A-Za-z0-9_])', lowered):
        raise RunnerError("命令包含受保护路径，禁止执行")
    if "supervision" in lowered or "..\\" in lowered:
        raise RunnerError("命令包含受保护路径，禁止执行")
    return command


def _validate_timeout(timeout: Any) -> int:
    try:
        value = int(timeout)
    except (TypeError, ValueError) as exc:
        raise RunnerError("timeout 必须是整数") from exc
    max_tier = get_current_tier()
    if not 1 <= value <= max_tier:
        raise RunnerError(f"timeout 必须在 1 到 {max_tier} 秒之间")
    return value


def _clamp_timeout(timeout: Any) -> tuple[int, str]:
    """把 timeout 钳制到 [1, 当前档位]，返回 (值, 警告信息)。

    与 _validate_timeout 不同，本函数**永不抛异常**——任何非法输入都
    回退/钳制到合法范围，确保 run_command 不会因参数问题中断调用方。
    上限为当前时限档位（分档制，基础 120s，可自由切换）。
    """
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        return 30, f"timeout 值非法（{timeout!r}），已回退为默认 30 秒"
    max_tier = get_current_tier()
    if value < 1:
        return 1, f"timeout={value} 小于 1，已钳制为 1 秒"
    if value > max_tier:
        return max_tier, (
            f"timeout={value} 超过当前档位上限，已钳制为 {max_tier} 秒"
        )
    return value, ""


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """终止进程及其整个子进程树，避免超时后留下孤儿进程。

    - Windows: 使用 taskkill /T /F 按父子关系杀死整个进程树
    - POSIX:   使用 os.killpg 杀死整个进程组（依赖 start_new_session=True）
    """
    if process.poll() is not None:
        return  # 进程已自然退出

    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        # 兜底：进程树清理失败时，至少杀掉主进程，避免卡死
        try:
            process.kill()
        except Exception:
            pass


def run_command(command: str, timeout: int = 30) -> str:
    """直接执行命令，无需等待批准。

    本函数**保证永不抛异常**：参数校验失败、超时、执行错误等所有情况
    都返回提示字符串，绝不向上传播异常以中断调用方（对话）。

    超时后清理整个子进程树，避免孤儿进程残留导致后续调用卡住。
    """

    # 参数校验：失败时返回友好提示，绝不抛异常
    try:
        command = _validate_command(command)
    except RunnerError as exc:
        return f"⚠️ 命令未执行：{exc}"

    timeout, timeout_warning = _clamp_timeout(timeout)

    # POSIX 上开启新会话，使子进程成为独立进程组，便于超时后 killpg；
    # Windows 上无需额外标志，taskkill /T 按父子关系清理进程树。
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            # ★T2798：Windows 下子进程（cmd 内建命令、本机 python）按**本地代码页**
            # 输出，强制 utf-8 解码会把中文错误信息变成乱码（实测
            # "'xxx' 不是内部或外部命令" → "'xxx' �����ڲ����ⲿ���"），
            # 模型读到的失败原因是废信息。按平台选择解码编码。
            # ★T2798：读 bytes 后智能解码（见 _smart_decode）。
            # 单一编码无解：cmd 内建命令按本地代码页(cp936)输出，而本机 python
            # 在 PYTHONUTF8=1 时按 UTF-8 输出，同一会话内两种编码并存。
            cwd=str(SANDBOX_DIR),
            env=_build_env(),
            start_new_session=(sys.platform != "win32"),
        )
    except OSError as exc:
        return f"错误：{type(exc).__name__}: {exc}"
    except Exception as exc:  # 兜底：任何启动异常都返回字符串
        return f"错误：{type(exc).__name__}: {exc}"

    try:
        stdout_raw, stderr_raw = process.communicate(timeout=timeout)
        stdout, stderr = _smart_decode(stdout_raw), _smart_decode(stderr_raw)
    except subprocess.TimeoutExpired:
        # 超时：先清理进程树，再尽力收集已产生的部分输出
        _terminate_process_tree(process)
        try:
            partial_raw = process.communicate(timeout=5)
            partial_out = _smart_decode(partial_raw[0] if partial_raw else b"")
            partial_err = _smart_decode(partial_raw[1] if partial_raw else b"")
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            partial_out, partial_err = "", ""

        lines: list[str] = [f"⚠️ 命令执行超时（{timeout}秒），已终止。"]
        if timeout_warning:
            lines.append(f"ℹ️ {timeout_warning}")
        if partial_out and partial_out.strip():
            lines.append("── 已产生输出 ──")
            lines.append(partial_out.rstrip())
        if partial_err and partial_err.strip():
            lines.append("── 已产生 STDERR ──")
            lines.append(partial_err.rstrip())
        return "\n".join(lines)

    # 正常结束
    output_parts: list[str] = []
    if timeout_warning:
        output_parts.append(f"ℹ️ {timeout_warning}\n")
    if stdout:
        output_parts.append(stdout)
    if stderr:
        output_parts.append(f"[STDERR]\n{stderr}")
    if process.returncode != 0:
        # ★T2798/K2：失败必须携带机器可判定的标记。
        # 原实现只追加中性的 "返回码: N"，模型可能把失败读成成功（静默失败，
        # 参见 arXiv 2608.02464 对该失效模式的定义与量化）。
        output_parts.append(
            f"\n❌ 命令失败（返回码 {process.returncode}）：本次执行未成功，"
            f"不要据此推断已达成目标，需先修复错误。"
        )
    result = "".join(output_parts) if output_parts else "(无输出)"
    return _truncate_output(result)


# ── P2 上下文治理：超大输出摘出上下文 ──────────────────
try:
    from tools.budget import RESULT_LIMIT as MAX_OUTPUT_CHARS  # 步骤4.3 统一阈值来源
except ImportError:  # pragma: no cover
    from budget import RESULT_LIMIT as MAX_OUTPUT_CHARS


def _truncate_output(text: str) -> str:
    """超大输出截断为「头部+尾部采样」，完整内容落盘供按需分段读取。

    对齐 Anthropic Programmatic Tool Calling 思路：避免大结果整体涌入
    模型上下文（实测大输出是最主要的上下文污染源之一）。
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    import time as _t
    from pathlib import Path as _P

    head_n = int(MAX_OUTPUT_CHARS * 0.7)
    tail_n = MAX_OUTPUT_CHARS - head_n
    handle = ""
    try:
        out_dir = _P(__file__).resolve().parent.parent / "memory" / "cmd_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        fn = out_dir / f"out_{int(_t.time() * 1000)}.txt"
        fn.write_text(text, encoding="utf-8")
        handle = f"memory/cmd_output/{fn.name}"
    except Exception:
        pass
    parts = [f"⚠️ 输出过大（{len(text)} 字符），已返回头部+尾部采样。"]
    if handle:
        parts.append(f"💡 完整输出已落盘：{handle}（可用 read_file offset/limit 分段读取）")
    parts += ["", f"── 前 {head_n} 字符 ──", text[:head_n],
              "", f"── 末 {tail_n} 字符 ──", text[-tail_n:]]
    return "\n".join(parts)


def execute_runner_tool(arguments: dict[str, Any]) -> str:
    """run_command 工具入口。**保证永不抛异常**，任何异常都转为友好提示。"""
    try:
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 30)
        return run_command(command, timeout)
    except Exception as exc:  # 兜底：工具入口绝不抛异常穿透到上层
        return f"⚠️ 命令执行异常：{type(exc).__name__}: {exc}"
