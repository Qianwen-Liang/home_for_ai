"""Write tools restricted to the agent-sandbox directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SANDBOX_ROOT = Path(__file__).resolve().parent.parent
MAX_WRITE_BYTES = 100_000

WRITE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "在 agent-sandbox 内创建或覆盖 UTF-8 文本文件。"
                "只有用户明确要求创建或修改时才能调用。"
                "⚠️ 单次 content 请控制在约 8000 字符（约 24KB）以内；"
                "超长内容应拆分为多次 write_file 调用（先写主体，再用 replace_text 补充），"
                "避免流式生成时参数被截断导致调用失败。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "沙箱内的相对文件路径。"},
                    "content": {"type": "string", "description": "要写入的完整文本。"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_text",
            "description": (
                "在 agent-sandbox 内的 UTF-8 文本文件中精确替换一段文本。"
                "只有匹配一次时才执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "沙箱内的相对文件路径。"},
                    "old_text": {"type": "string", "description": "待替换且应只出现一次的文本。"},
                    "new_text": {"type": "string", "description": "替换后的文本。"},
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_directory",
            "description": "在 agent-sandbox 内创建目录及其父目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "沙箱内的相对目录路径。"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


class WriteToolError(RuntimeError):
    """Raised when a requested write is invalid or outside the sandbox."""


def _is_protected(path: Path) -> bool:
    name = path.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in {".restart-state.json", ".restart-state.json.tmp"}
    )


def _resolve_write_path(requested_path: str) -> Path:
    if not isinstance(requested_path, str) or not requested_path.strip():
        raise WriteToolError("路径不能为空")

    raw_path = Path(requested_path.strip())
    # 规范化：去掉前导 "agent-sandbox/" 或 "agent-sandbox\"。
    # read_file 的基准是工作区根（agent-sandbox 的父目录），
    # write_file 的基准是 agent-sandbox 自身。LLM 可能用
    # read_file 的路径直接写回，导致 agent-sandbox/agent-sandbox/ 嵌套。
    parts = raw_path.parts
    if parts and parts[0] == "agent-sandbox":
        raw_path = Path(*parts[1:]) if len(parts) > 1 else Path(".")

    candidate = raw_path if raw_path.is_absolute() else SANDBOX_ROOT / raw_path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(SANDBOX_ROOT)
    except (OSError, RuntimeError) as exc:
        raise WriteToolError("无法解析目标路径") from exc
    except ValueError as exc:
        raise WriteToolError("写入路径必须位于 agent-sandbox 内") from exc

    if resolved == SANDBOX_ROOT:
        raise WriteToolError("不能把沙箱根目录作为写入目标")
    if _is_protected(resolved):
        raise WriteToolError("环境变量文件属于受保护文件，禁止写入")
    return resolved


def _validate_content(content: str) -> None:
    if not isinstance(content, str):
        raise WriteToolError("文件内容必须是字符串")
    size = len(content.encode("utf-8"))
    if size > MAX_WRITE_BYTES:
        raise WriteToolError(
            f"内容大小为 {size} 字节，超过 {MAX_WRITE_BYTES} 字节限制"
        )


# 主入口及根目录基础模块：无法热重载，修改后需重启进程生效
_RESTART_REQUIRED_FILES = frozenset({
    "agent1.py", "core/read.py", "core/write.py", "core/conversation.py",
    "core/restart.py", "bootstrap.py",
})


def _auto_hot_reload(target: Path) -> str:
    """写后自动热重载：若目标是已加载的可热重载模块，立即 reload 使宿主进程生效。

    这是"Agent 修复代码后自动 reload 宿主进程"闭环的核心钩子。
    返回追加到写入结果后的提示文本（无提示则返回空串）。
    """
    rel = str(target.relative_to(SANDBOX_ROOT)).replace("\\", "/")

    # 主入口等不可热重载文件：明确提示需重启
    if rel in _RESTART_REQUIRED_FILES:
        return "（⚠️ 主入口/基础模块，需重启进程生效）"

    try:
        from evolver.hot_reload import hot_reload, resolve_module_name
        mod_name = resolve_module_name(rel)
        if mod_name is None:
            return ""  # 非模块文件（.md/.json/tests 等），无需 reload
        results = hot_reload([rel])
        reloaded = [r for r in results if r.startswith("✅")]
        if reloaded:
            return f"（✅ 已热重载 {reloaded[0].split(' ', 1)[1]}，立即生效）"
        # 模块未加载（如首次写入的新模块），无需 reload
        return ""
    except Exception:
        return ""


def write_file(path: str, content: str) -> str:
    target = _resolve_write_path(path)
    _validate_content(content)
    if target.exists() and target.is_dir():
        raise WriteToolError(f"目标是目录，不能写入文件: {path}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")
    msg = f"已写入 {target.relative_to(SANDBOX_ROOT)}"
    reload_note = _auto_hot_reload(target)
    if reload_note:
        msg += f"\n{reload_note}"
    return msg


def replace_text(path: str, old_text: str, new_text: str) -> str:
    target = _resolve_write_path(path)
    if not target.is_file():
        raise WriteToolError(f"目标文件不存在: {path}")
    try:
        current = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise WriteToolError("只允许编辑 UTF-8 文本文件") from exc

    occurrences = current.count(old_text)
    if occurrences != 1:
        raise WriteToolError(f"待替换文本出现 {occurrences} 次，必须恰好出现 1 次")
    updated = current.replace(old_text, new_text, 1)
    return write_file(path, updated)


def make_directory(path: str) -> str:
    target = _resolve_write_path(path)
    if target.exists() and not target.is_dir():
        raise WriteToolError(f"目标已存在且不是目录: {path}")
    target.mkdir(parents=True, exist_ok=True)
    return f"已创建目录 {target.relative_to(SANDBOX_ROOT)}"


def execute_write_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "write_file":
        path, content = arguments.get("path"), arguments.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise WriteToolError("write_file 需要字符串参数 path 和 content")
        return write_file(path, content)
    if name == "replace_text":
        path = arguments.get("path")
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")
        if not all(isinstance(value, str) for value in (path, old_text, new_text)):
            raise WriteToolError(
                "replace_text 需要字符串参数 path、old_text 和 new_text"
            )
        return replace_text(path, old_text, new_text)
    if name == "make_directory":
        path = arguments.get("path")
        if not isinstance(path, str):
            raise WriteToolError("make_directory 需要字符串参数 path")
        return make_directory(path)
    raise WriteToolError(f"未知写入工具: {name}")
