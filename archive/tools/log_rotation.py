"""log_rotation — 日志轮转与归档工具

检测 logs/ 目录下日志文件的大小，超过阈值时自动归档
（重命名为带时间戳的归档文件），防止日志无限增长。

设计原则：
  - 默认阈值 1MB，超过才触发归档
  - 归档文件保留最近 N 份，超出自动清理最旧的
  - 幂等：可重复运行，不重复归档
  - 安全：只处理 *.log 文件，不触碰其他文件
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = SANDBOX_DIR / "logs"

DEFAULT_MAX_SIZE_BYTES = 1_000_000  # 1MB
DEFAULT_KEEP_ARCHIVES = 5


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "log_rotation",
        "description": (
            "日志轮转工具。检测 logs/ 目录下日志文件大小，"
            "超过阈值时自动归档，防止日志无限增长。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_size_mb": {
                    "type": "number",
                    "description": "归档阈值（MB），默认 1.0",
                    "default": 1.0,
                },
                "keep_archives": {
                    "type": "integer",
                    "description": "每个日志保留的归档份数，默认 5",
                    "default": 5,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "仅报告不实际归档，默认 False",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
    },
}


def rotate_logs(
    max_size_mb: float = 1.0,
    keep_archives: int = DEFAULT_KEEP_ARCHIVES,
    dry_run: bool = False,
) -> str:
    """检查并轮转日志文件。"""
    if not LOG_DIR.is_dir():
        return "⚠️ logs/ 目录不存在。"

    max_size_bytes = int(max_size_mb * 1024 * 1024)
    lines: list[str] = [
        f"📜 日志轮转检查",
        f"{'─'*40}",
        f"阈值: {max_size_mb} MB | 保留归档: {keep_archives} 份 | 模式: {'预演' if dry_run else '执行'}",
        "",
    ]

    log_files = sorted(LOG_DIR.glob("*.log"))
    if not log_files:
        lines.append("ℹ️ 无 .log 文件，无需轮转。")
        return "\n".join(lines)

    rotated_count = 0
    cleaned_count = 0

    for log_file in log_files:
        size = log_file.stat().st_size
        status = "✅ 正常" if size < max_size_bytes else "🔴 超阈值"
        lines.append(f"  {log_file.name}: {size:,} bytes ({size/1024/1024:.2f} MB) → {status}")

        if size >= max_size_bytes:
            rotated_count += 1
            if dry_run:
                lines.append(f"    ↳ [预演] 将归档 {log_file.name}")
                continue

            # 归档：重命名为 name.YYYYMMDD-HHMMSS.log
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            archive_name = f"{log_file.stem}.{stamp}.log"
            archive_path = LOG_DIR / archive_name
            try:
                log_file.rename(archive_path)
                lines.append(f"    ↳ 已归档 → {archive_name}")
            except OSError as exc:
                lines.append(f"    ↳ ❌ 归档失败: {exc}")
                continue

            # 清理旧归档：保留最近 keep_archives 份
            stem = log_file.stem
            archives = sorted(
                LOG_DIR.glob(f"{stem}.*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in archives[keep_archives:]:
                try:
                    old.unlink()
                    cleaned_count += 1
                    lines.append(f"    ↳ 清理旧归档: {old.name}")
                except OSError:
                    pass

    lines.append("")
    if dry_run:
        lines.append(f"ℹ️ 预演完成：{rotated_count} 个文件需归档（未实际执行）。")
    else:
        lines.append(
            f"✅ 轮转完成：{rotated_count} 个归档，{cleaned_count} 个旧归档清理。"
        )
    return "\n".join(lines)


def execute_log_rotation_tool(arguments: dict[str, Any]) -> str:
    max_size_mb = float(arguments.get("max_size_mb", 1.0))
    keep_archives = int(arguments.get("keep_archives", DEFAULT_KEEP_ARCHIVES))
    dry_run = bool(arguments.get("dry_run", False))
    return rotate_logs(max_size_mb, keep_archives, dry_run)


# ── 独立运行入口 ──────────────────────────────────────────

if __name__ == "__main__":
    print(rotate_logs())
