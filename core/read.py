"""Read-only tools constrained to the local workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent

# ★可移植性修复（T2798）：原实现把允许访问的顶层目录硬编码为
# {"agent-sandbox", "supervision"}，导致项目一旦被检出到其他名字的目录
# （CI 的 /home/runner/work/...、任何 fork、任何子目录）就**所有 read_file 全部被拒**。
# 现改为基于项目根动态推导：项目根自身（无论叫什么名字）+ 同级 supervision（若存在）。
PROJECT_DIR_NAME = PROJECT_ROOT.name
ALLOWED_TOP_LEVEL = {PROJECT_DIR_NAME}
if (WORKSPACE_ROOT / "supervision").is_dir():
    ALLOWED_TOP_LEVEL.add("supervision")
ALLOWED_TOP_LEVEL = frozenset(ALLOWED_TOP_LEVEL)
from tools.budget import HARD_FILE_LIMIT as MAX_FILE_BYTES  # 步骤4.3 统一阈值来源
from tools.budget import FULL_TEXT_LIMIT  # noqa: F401  (供本模块使用)

READ_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取工作区内 agent-sandbox 或 supervision 中的 UTF-8 文本文件。"
                "不能读取 .env 等受保护的密钥文件。"
                "大文件会返回头部+尾部采样，可用 offset/limit 分段读取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于工作区根目录的文件路径。",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（0 基），默认 0。大文件分段读取时使用。",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多读取行数，0 表示不限。大文件分段读取时使用。",
                        "default": 0,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出工作区根目录或其子目录中的直接内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于工作区根目录的目录，默认为根目录。",
                        "default": ".",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
]


class ReadToolError(RuntimeError):
    """Raised when a requested read is invalid or outside the allowed scope."""


def _is_protected(path: Path) -> bool:
    name = path.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in {".restart-state.json", ".restart-state.json.tmp"}
    )


def _resolve_path(requested_path: str) -> Path:
    if not isinstance(requested_path, str) or not requested_path.strip():
        raise ReadToolError("路径不能为空")

    raw_path = Path(requested_path.strip())

    # ── 路径基准统一桥接 ──────────────────────────────────────────
    # read 工具的 WORKSPACE_ROOT 比 write/run_command 的基准高一级。
    # run_command 输出的路径（如 "tools/foo.py"）缺少 "agent-sandbox/" 前缀，
    # 需要自动补全。同时兼容已带前缀的路径（如 "agent-sandbox/tools/foo.py"）。
    if not raw_path.is_absolute():
        first_part = raw_path.parts[0] if raw_path.parts else ""
        if first_part not in ALLOWED_TOP_LEVEL:
            # 尝试自动添加项目根目录名前缀（run_command 基准）
            auto_prefixed = Path(PROJECT_DIR_NAME) / raw_path
            candidate = WORKSPACE_ROOT / auto_prefixed
            try:
                resolved = candidate.resolve(strict=True)
                relative = resolved.relative_to(WORKSPACE_ROOT)
            except (FileNotFoundError, ValueError):
                pass  # 回退到原始路径解析
            else:
                if relative.parts and relative.parts[0] in ALLOWED_TOP_LEVEL:
                    if _is_protected(resolved):
                        raise ReadToolError("该文件包含受保护的环境变量，禁止读取")
                    return resolved
    # ─────────────────────────────────────────────────────────────────

    candidate = raw_path if raw_path.is_absolute() else WORKSPACE_ROOT / raw_path
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(WORKSPACE_ROOT)
    except FileNotFoundError as exc:
        raise ReadToolError(f"路径不存在: {requested_path}") from exc
    except ValueError as exc:
        raise ReadToolError("拒绝访问工作区之外的路径") from exc

    if relative.parts and relative.parts[0] not in ALLOWED_TOP_LEVEL:
        raise ReadToolError(
            f"只允许访问 {sorted(ALLOWED_TOP_LEVEL)} 中的路径（当前为 {relative.parts[0]!r}）"
        )
    if _is_protected(resolved):
        raise ReadToolError("该文件包含受保护的环境变量，禁止读取")
    return resolved


def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """读取文本文件。

    offset: 起始行号（0-based），默认 0
    limit:  最多读取行数，0 表示不限（受大小策略约束）

    P2 上下文治理：大文件不再直接拒绝，而是返回「头部+尾部采样 + 分段指引」，
    避免模型因体积限制而完全读不到内容（原逻辑 7.1% 的 read_file 失败即源于此）。
    """
    target = _resolve_path(path)
    if not target.is_file():
        raise ReadToolError(f"目标不是文件: {path}")

    size = target.stat().st_size
    data = target.read_bytes()
    if b"\x00" in data:
        raise ReadToolError("只允许读取文本文件")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReadToolError("文件不是有效的 UTF-8 文本") from exc

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    # 显式分段请求：按行切片返回
    if offset or limit:
        start = max(0, offset)
        end = start + limit if limit > 0 else total_lines
        chunk = "".join(lines[start:end])
        header = (f"[分段读取] 第 {start + 1}-{min(end, total_lines)} 行 / "
                  f"共 {total_lines} 行，{size} 字节\n")
        return header + chunk

    # 小文件：全文返回（阈值统一由 tools/budget.py 提供）
    if size <= FULL_TEXT_LIMIT:
        return text

    # 大文件：采样 + 指引（不拒绝）
    head_n, tail_n = 80, 40
    head = "".join(lines[:head_n])
    tail = "".join(lines[-tail_n:]) if total_lines > head_n + tail_n else ""
    parts = [
        f"⚠️ 文件较大（{size} 字节 / {total_lines} 行），已返回采样内容。",
        "💡 分段读取：read_file(path, offset=<起始行,0基>, limit=<行数>)",
        "",
        f"── 前 {min(head_n, total_lines)} 行 ──",
        head,
    ]
    if tail:
        parts += ["", f"── 末 {tail_n} 行 ──", tail]
    return "\n".join(parts)


def list_directory(path: str = ".") -> str:
    target = _resolve_path(path)
    if not target.is_dir():
        raise ReadToolError(f"目标不是目录: {path}")

    entries: list[str] = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        suffix = "/" if entry.is_dir() else ""
        protected = " [受保护]" if _is_protected(entry) else ""
        entries.append(f"{entry.name}{suffix}{protected}")
    return "\n".join(entries) if entries else "（空目录）"


def execute_read_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "read_file":
        path = arguments.get("path")
        if not isinstance(path, str):
            raise ReadToolError("read_file 需要字符串参数 path")
        try:
            offset = int(arguments.get("offset", 0) or 0)
            limit = int(arguments.get("limit", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ReadToolError("offset/limit 必须是整数") from exc
        return read_file(path, offset=offset, limit=limit)
    if name == "list_directory":
        path = arguments.get("path", ".")
        if not isinstance(path, str):
            raise ReadToolError("list_directory 的 path 必须是字符串")
        return list_directory(path)
    raise ReadToolError(f"未知读取工具: {name}")
