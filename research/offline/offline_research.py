"""offline_research.py — 离线无人值守研究工具（agent1 工具入口）

把 research/ 目录下的 create_task_pack + launch_worker + offline_status
封装成一个 agent1 工具，实现"一句话触发离线研究"。

用户说「学习 XXX + 离线模式运行」后，Agent 1 解析指令，提取
theme/goal/task_type/query，调用本工具的 submit，即可后台启动研究流水线。

使用方式（工具调用）：
  offline_research action=submit theme="..." goal="..." task_type=research query="..."
  offline_research action=status
  offline_research action=report task_id="..."
  offline_research action=recover task_id="..."
  offline_research action=list
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent
OFFLINE_DIR = SANDBOX_DIR / "memory" / "offline"

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "offline_research",
        "description": (
            "离线无人值守研究工具。提交研究主题后，由后台独立进程完成"
            "「检索→精读→综合→(实现/假设/推导/实验)」流水线，"
            "产出结构化报告和可运行代码。适合用户说「学习 XXX + 离线模式运行」的场景。"
            "支持 submit/status/report/recover/list 操作。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["submit", "paper", "status", "report", "recover", "list"],
                    "description": (
                        "submit — 提交研究任务并后台启动；"
                        "paper — 提交「投稿人↔审稿人」论文协作任务并后台启动；"
                        "status — 查看所有任务状态；"
                        "report — 查看指定任务的最终报告；"
                        "recover — 恢复失败/中断的任务；"
                        "list — 列出所有任务（同 status）"
                    ),
                },
                "theme": {
                    "type": "string",
                    "description": "研究主题（submit 时必需）",
                    "default": "",
                },
                "goal": {
                    "type": "string",
                    "description": "研究目标（submit 时可选，默认用主题）",
                    "default": "",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["research", "build", "innovate"],
                    "description": (
                        "任务类型：research 调研报告 / build 调研+生成可运行代码 / "
                        "innovate 论文级创新（含假设/推导/实验）"
                    ),
                    "default": "research",
                },
                "query": {
                    "type": "string",
                    "description": "检索关键词（submit 时可选，默认用主题）",
                    "default": "",
                },
                "max_sources": {
                    "type": "integer",
                    "description": "检索来源数量，默认 5",
                    "default": 5,
                },
                "task_id": {
                    "type": "string",
                    "description": "任务 ID（report/recover 时必需）",
                    "default": "",
                },
                "requirements": {
                    "type": "string",
                    "description": "论文写作要求（paper 时可选）",
                    "default": "",
                },
                "max_rounds": {
                    "type": "integer",
                    "description": "投稿人-审稿人最大协作轮数（paper 时使用，默认 3）",
                    "default": 3,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


def _launch_worker(task_id: str) -> None:
    """后台启动 research_worker.py（脱离会话进程，不受 120 秒超时影响）。"""
    log_path = OFFLINE_DIR / task_id / "bg_stdout.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP

    with open(log_path, "w", encoding="utf-8") as log:
        subprocess.Popen(
            [
                sys.executable, "-X", "utf8",
                str(SANDBOX_DIR / "research" / "offline" / "research_worker.py"),
                "--task", task_id,
            ],
            stdout=log,
            stderr=log,
            creationflags=flags if flags else 0,
            close_fds=True,
            cwd=str(SANDBOX_DIR),
        )


def _submit(arguments: dict[str, Any]) -> str:
    from research.offline.create_task_pack import create_task_pack

    theme = (arguments.get("theme") or "").strip()
    if not theme:
        return "⚠️ 请提供 theme（研究主题）"

    goal = (arguments.get("goal") or "").strip()
    task_type = arguments.get("task_type") or "research"
    query = (arguments.get("query") or "").strip()
    try:
        max_sources = int(arguments.get("max_sources", 5))
    except (TypeError, ValueError):
        max_sources = 5

    try:
        task_id = create_task_pack(
            theme=theme,
            goal=goal,
            task_type=task_type,
            query=query,
            max_sources=max_sources,
        )
    except Exception as exc:
        return f"⚠️ 任务包生成失败: {type(exc).__name__}: {exc}"

    try:
        _launch_worker(task_id)
    except Exception as exc:
        return f"⚠️ 任务包已生成但启动失败: {task_id}（{exc}）"

    return (
        f"📦 离线研究任务已提交并后台启动\n"
        f"{'─' * 40}\n"
        f"任务ID:   {task_id}\n"
        f"主题:     {theme}\n"
        f"类型:     {task_type}\n"
        f"\n后台独立进程正在执行，稍后可用 offline_research action=status 查看进度，"
        f"或用 action=report task_id={task_id} 查看最终报告。"
    )


def _launch_paper(paper_id: str, topic: str, requirements: str, max_rounds: int) -> None:
    """后台启动 paper_collab.py（投稿人-审稿人协作）。"""
    out_dir = OFFLINE_DIR / paper_id
    log_path = out_dir / "bg_stdout.log"

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP

    with open(log_path, "w", encoding="utf-8") as log:
        subprocess.Popen(
            [
                sys.executable, "-X", "utf8",
                str(SANDBOX_DIR / "research" / "offline" / "paper_collab.py"),
                "--topic", topic,
                "--requirements", requirements,
                "--max_rounds", str(max_rounds),
                "--output", str(out_dir),
                "--task_id", paper_id,
            ],
            stdout=log,
            stderr=log,
            creationflags=flags if flags else 0,
            close_fds=True,
            cwd=str(SANDBOX_DIR),
        )


def _submit_paper(arguments: dict[str, Any]) -> str:
    from datetime import datetime

    topic = (arguments.get("theme") or "").strip()
    if not topic:
        return "⚠️ 请提供 theme（论文主题）"

    requirements = (arguments.get("requirements") or "").strip()
    try:
        max_rounds = int(arguments.get("max_rounds", 3))
    except (TypeError, ValueError):
        max_rounds = 3

    paper_id = f"OP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    out_dir = OFFLINE_DIR / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写 task_pack.json（让 offline_status 能扫描到 paper 任务）
    pack = {
        "task_id": paper_id,
        "theme": topic,
        "goal": requirements or "投稿人-审稿人协作产出论文",
        "task_type": "paper",
        "phases": ["写作", "评审"],
        "phase_params": {},
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }
    (out_dir / "task_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        _launch_paper(paper_id, topic, requirements, max_rounds)
    except Exception as exc:
        return f"⚠️ 论文协作启动失败: {exc}"

    return (
        f"📝 论文协作任务已提交并后台启动\n"
        f"{'─' * 40}\n"
        f"任务ID:   {paper_id}\n"
        f"主题:     {topic}\n"
        f"模式:     投稿人↔审稿人 多轮协作（最多 {max_rounds} 轮）\n"
        f"\n稍后用 offline_research action=status 查看进度，"
        f"或读取 memory/offline/{paper_id}/paper.md 查看最终论文。"
    )


def _status() -> str:
    from research.offline.offline_status import scan_offline_tasks, format_report
    return format_report(scan_offline_tasks(), show_all=True)


def _report(arguments: dict[str, Any]) -> str:
    from research.offline.offline_status import read_report
    task_id = (arguments.get("task_id") or "").strip()
    if not task_id:
        return "⚠️ 请提供 task_id"
    return read_report(task_id)


def _recover(arguments: dict[str, Any]) -> str:
    task_id = (arguments.get("task_id") or "").strip()
    if not task_id:
        return "⚠️ 请提供 task_id"

    p = OFFLINE_DIR / task_id / "progress.json"
    if not p.is_file():
        return f"⚠️ 未找到任务 '{task_id}'"

    try:
        prog = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"⚠️ progress.json 读取失败: {exc}"

    status = prog.get("status", "")
    if status == "done":
        return f"✅ 任务 '{task_id}' 已完成，无需恢复"
    if status == "running":
        return f"🔄 任务 '{task_id}' 正在运行中"

    # 重置失败/中断状态，保留 done_phases（worker 会跳过已完成阶段）
    failed_phase = prog.get("failed_phase", "")
    prog["status"] = "pending"
    prog["failed_phase"] = ""
    prog["error"] = ""
    prog.pop("error_trace", None)
    p.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

    _launch_worker(task_id)

    return (
        f"🔧 任务 '{task_id}' 已恢复并重新启动\n"
        f"{'─' * 40}\n"
        f"失败阶段: {failed_phase or '（无记录）'}\n"
        f"已完成的阶段会跳过，从失败处继续执行。\n"
        f"\n稍后用 offline_research action=status 查看进度。"
    )


def execute_offline_research_tool(arguments: dict[str, Any]) -> str:
    """offline_research 工具入口。保证永不抛异常。"""
    try:
        action = arguments.get("action", "submit")
        if action == "submit":
            return _submit(arguments)
        if action == "paper":
            return _submit_paper(arguments)
        if action in ("status", "list"):
            return _status()
        if action == "report":
            return _report(arguments)
        if action == "recover":
            return _recover(arguments)
        return f"未知操作: {action}"
    except Exception as exc:
        return f"⚠️ offline_research 异常: {type(exc).__name__}: {exc}"
