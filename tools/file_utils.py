"""
FileUtils — 文件操作辅助工具集
===============================
提供文件查找、统计、格式分析等辅助功能，增强智能体的文件处理能力。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent

# ── 错误类型 ──────────────────────────────────────────────


class FileUtilsError(RuntimeError):
    """文件工具操作错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "file_utils",
        "description": (
            "文件操作辅助工具，支持查找文件、统计文件类型分布、"
            "分析文件大小、查找最近修改的文件等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "find",
                        "type_stats",
                        "size_analysis",
                        "recent_files",
                        "largest_files",
                    ],
                    "description": (
                        "操作类型："
                        "find — 按文件名模式查找文件；"
                        "type_stats — 文件类型分布统计；"
                        "size_analysis — 文件大小分析；"
                        "recent_files — 最近修改的文件列表；"
                        "largest_files — 最大的文件列表。"
                    ),
                },
                "pattern": {
                    "type": "string",
                    "description": "查找模式，如 '*.py'、'*test*'（用于 find 操作）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量限制，默认 20",
                    "default": 20,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 核心功能 ──────────────────────────────────────────────


def _safe_walk() -> list[tuple[Path, list[Path]]]:
    """安全地遍历 sandbox 目录，返回 (相对路径, 文件列表) 对。"""
    entries: list[tuple[Path, list[Path]]] = []
    for root, _dirs, files in os.walk(SANDBOX_DIR):
        rel_root = Path(root).relative_to(SANDBOX_DIR)
        # 跳过隐藏目录
        if any(part.startswith(".") or part == "__pycache__" for part in rel_root.parts):
            continue
        file_paths: list[Path] = []
        for fname in files:
            fpath = Path(root) / fname
            try:
                fpath.stat()
                file_paths.append(fpath)
            except OSError:
                continue
        if file_paths:
            entries.append((rel_root, file_paths))
    return entries


def _match_pattern(filename: str, pattern: str) -> bool:
    """简单的通配符匹配。"""
    if not pattern:
        return True
    import re
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    regex = regex.replace("\\?", ".")
    return bool(re.match(f"^{regex}$", filename, re.IGNORECASE))


def find_files(pattern: str = "", limit: int = 20) -> str:
    """查找匹配文件名模式的文件。"""
    results: list[str] = []
    for rel_root, files in _safe_walk():
        for fpath in files:
            if pattern and not _match_pattern(fpath.name, pattern):
                continue
            rel_path = fpath.relative_to(SANDBOX_DIR)
            results.append(str(rel_path))
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    if not results:
        return f"未找到匹配 '{pattern}' 的文件。"
    return f"找到 {len(results)} 个文件（显示前 {len(results)} 个）：\n" + "\n".join(results)


def type_stats() -> str:
    """统计文件类型分布。"""
    type_count: dict[str, int] = {}
    type_size: dict[str, int] = {}
    total_files = 0

    for _rel_root, files in _safe_walk():
        for fpath in files:
            ext = fpath.suffix.lower() if fpath.suffix else "(无扩展名)"
            type_count[ext] = type_count.get(ext, 0) + 1
            try:
                type_size[ext] = type_size.get(ext, 0) + fpath.stat().st_size
            except OSError:
                continue
            total_files += 1

    if not total_files:
        return "工作区中没有文件。"

    lines = [f"📊 文件类型统计（共 {total_files} 个文件）\n"]
    lines.append(f"{'扩展名':<16} {'数量':>6} {'大小':>10}")
    lines.append("-" * 36)
    for ext in sorted(type_count.keys(), key=lambda e: -type_count[e]):
        count = type_count[ext]
        size = type_size.get(ext, 0)
        size_str = _format_size(size)
        lines.append(f"{ext:<16} {count:>6} {size_str:>10}")

    return "\n".join(lines)


def size_analysis() -> str:
    """分析文件大小分布。"""
    sizes: list[int] = []
    for _rel_root, files in _safe_walk():
        for fpath in files:
            try:
                sizes.append(fpath.stat().st_size)
            except OSError:
                continue

    if not sizes:
        return "工作区中没有文件。"

    sizes.sort()
    total = sum(sizes)
    count = len(sizes)
    avg = total / count if count else 0
    median = sizes[count // 2] if count else 0
    largest = sizes[-1] if sizes else 0

    # 分布统计
    small = sum(1 for s in sizes if s < 1024)  # < 1KB
    medium = sum(1 for s in sizes if 1024 <= s < 10240)  # 1KB ~ 10KB
    large = sum(1 for s in sizes if 10240 <= s < 102400)  # 10KB ~ 100KB
    huge = sum(1 for s in sizes if s >= 102400)  # >= 100KB

    return (
        f"📏 文件大小分析（{count} 个文件）\n"
        f"{'='*35}\n"
        f"总大小: {_format_size(total)}\n"
        f"平均大小: {_format_size(avg)}\n"
        f"中位数: {_format_size(median)}\n"
        f"最大文件: {_format_size(largest)}\n\n"
        f"分布:\n"
        f"  < 1KB:     {small:>4} 个\n"
        f"  1KB~10KB:  {medium:>4} 个\n"
        f"  10KB~100KB:{large:>4} 个\n"
        f"  >= 100KB:  {huge:>4} 个"
    )


def recent_files(limit: int = 20) -> str:
    """列出最近修改的文件。"""
    file_mtimes: list[tuple[float, Path]] = []

    for _rel_root, files in _safe_walk():
        for fpath in files:
            try:
                mtime = fpath.stat().st_mtime
                file_mtimes.append((mtime, fpath))
            except OSError:
                continue

    file_mtimes.sort(key=lambda x: -x[0])

    actual_limit = min(limit, len(file_mtimes))
    if not actual_limit:
        return "工作区中没有文件。"

    lines = [f"🕐 最近修改的 {actual_limit} 个文件:\n"]
    for mtime, fpath in file_mtimes[:actual_limit]:
        dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        rel = fpath.relative_to(SANDBOX_DIR)
        try:
            size = _format_size(fpath.stat().st_size)
        except OSError:
            size = "?"
        lines.append(f"  {dt}  {size:>8}  {rel}")

    return "\n".join(lines)


def largest_files(limit: int = 20) -> str:
    """列出最大的文件。"""
    file_sizes: list[tuple[int, Path]] = []

    for _rel_root, files in _safe_walk():
        for fpath in files:
            try:
                file_sizes.append((fpath.stat().st_size, fpath))
            except OSError:
                continue

    file_sizes.sort(key=lambda x: -x[0])

    actual_limit = min(limit, len(file_sizes))
    if not actual_limit:
        return "工作区中没有文件。"

    lines = [f"📦 最大的 {actual_limit} 个文件:\n"]
    for size, fpath in file_sizes[:actual_limit]:
        rel = fpath.relative_to(SANDBOX_DIR)
        lines.append(f"  {_format_size(size):>10}  {rel}")

    return "\n".join(lines)


def _format_size(size: float) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# ── 工具入口 ──────────────────────────────────────────────


_ACTIONS = {
    "find": find_files,
    "type_stats": type_stats,
    "size_analysis": size_analysis,
    "recent_files": recent_files,
    "largest_files": largest_files,
}


def execute_file_utils_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")
    pattern = arguments.get("pattern", "")
    limit = int(arguments.get("limit", 20))

    if action not in _ACTIONS:
        return f"未知操作: {action}，可用操作: {', '.join(_ACTIONS.keys())}"

    try:
        if action == "find":
            return find_files(pattern, limit)
        elif action == "recent_files":
            return recent_files(limit)
        elif action == "largest_files":
            return largest_files(limit)
        else:
            return _ACTIONS[action]()
    except FileUtilsError as exc:
        return f"文件工具错误: {exc}"
