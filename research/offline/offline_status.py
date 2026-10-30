"""offline_status.py — 离线任务状态扫描与汇报

Agent 1 会话启动时（或用户询问时）扫描 memory/offline/ 目录，
汇总所有离线研究任务的状态，主动汇报"已完成/进行中/失败"的任务。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent
OFFLINE_DIR = SANDBOX_DIR / "memory" / "offline"


def scan_offline_tasks() -> list[dict]:
    """扫描所有离线任务，返回状态列表（按 task_id 倒序）。"""
    if not OFFLINE_DIR.is_dir():
        return []

    tasks = []
    for d in sorted(OFFLINE_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        pack_file = d / "task_pack.json"
        if not pack_file.is_file():
            continue
        try:
            pack = json.loads(pack_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        prog_file = d / "progress.json"
        prog = {}
        if prog_file.is_file():
            try:
                prog = json.loads(prog_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        tasks.append({
            "task_id": d.name,
            "theme": pack.get("theme", d.name),
            "goal": pack.get("goal", ""),
            "status": prog.get("status", pack.get("status", "pending")),
            "done_phases": prog.get("done_phases", []),
            "failed_phase": prog.get("failed_phase", ""),
            "error": prog.get("error", ""),
            "completed_at": prog.get("completed_at", ""),
            "has_report": (d / "report.md").is_file(),
        })
    return tasks


def format_report(tasks: list[dict], show_all: bool = False) -> str:
    """把任务列表格式化为人类可读的汇报文本。"""
    if not tasks:
        return "📭 暂无离线任务记录。"

    done = [t for t in tasks if t["status"] == "done"]
    running = [t for t in tasks if t["status"] == "running"]
    failed = [t for t in tasks if t["status"] == "failed"]
    pending = [t for t in tasks if t["status"] == "pending"]

    lines = ["📦 离线任务状态汇总", "=" * 50]

    # 优先汇报"已完成"（第二天用户最关心的）
    if done:
        lines.append(f"\n✅ 已完成（{len(done)}）:")
        for t in done:
            lines.append(f"  • [{t['task_id']}] {t['theme']}")
            lines.append(f"    报告: memory/offline/{t['task_id']}/report.md")

    if running:
        lines.append(f"\n🔄 进行中（{len(running)}）:")
        for t in running:
            done_n = len(t["done_phases"])
            lines.append(f"  • [{t['task_id']}] {t['theme']}（已完成 {done_n} 阶段）")

    if failed:
        lines.append(f"\n❌ 失败（{len(failed)}）:")
        for t in failed:
            lines.append(f"  • [{t['task_id']}] {t['theme']} — {t['error'][:80]}")

    if pending and show_all:
        lines.append(f"\n📋 待执行（{len(pending)}）:")
        for t in pending:
            lines.append(f"  • [{t['task_id']}] {t['theme']}")

    return "\n".join(lines)


def read_report(task_id: str) -> str:
    """读取指定离线任务的最终报告。"""
    p = OFFLINE_DIR / task_id / "report.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return f"未找到任务 '{task_id}' 的报告。"


if __name__ == "__main__":
    tasks = scan_offline_tasks()
    print(format_report(tasks, show_all=True))
