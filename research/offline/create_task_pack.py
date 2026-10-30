"""create_task_pack.py — 生成离线研究任务包

Agent 1 在线解析用户研究指令后，调用本脚本生成结构化任务包，
再由 research_worker.py 在后台执行。

用法：
    python research/create_task_pack.py --theme "..." --goal "..." [--type research] [--query "..."]

或作为函数导入：
    from research.create_task_pack import create_task_pack
    task_id = create_task_pack(theme="...", goal="...")
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent
OFFLINE_DIR = SANDBOX_DIR / "memory" / "offline"

# 任务类型 → 阶段模板
PHASE_TEMPLATES = {
    "research": ["检索", "精读", "综合"],
    "build": ["检索", "精读", "综合", "实现"],   # 调研 + 生成骨架代码
    "innovate": ["检索", "精读", "假设", "推导", "实验", "综合"],
}


def create_task_pack(
    theme: str,
    goal: str,
    task_type: str = "research",
    query: str = "",
    max_sources: int = 5,
) -> str:
    """生成任务包并落盘，返回 task_id。"""
    task_id = f"OT-R-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    phases = PHASE_TEMPLATES.get(task_type, PHASE_TEMPLATES["research"])

    pack = {
        "task_id": task_id,
        "theme": theme,
        "goal": goal,
        "task_type": task_type,
        "phases": phases,
        "phase_params": {
            "检索": {"query": query or theme, "max_sources": max_sources},
        },
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }

    d = OFFLINE_DIR / task_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "task_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return task_id


def _parse_args(argv):
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and i + 1 < len(argv):
            args[a[2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return args


if __name__ == "__main__":
    a = _parse_args(sys.argv[1:])
    theme = a.get("theme", "")
    goal = a.get("goal", theme)
    if not theme:
        print("用法: python create_task_pack.py --theme <主题> [--goal <目标>] [--type research] [--query <搜索词>]")
        sys.exit(1)
    tid = create_task_pack(
        theme=theme,
        goal=goal,
        task_type=a.get("type", "research"),
        query=a.get("query", ""),
        max_sources=int(a.get("max_sources", 5)),
    )
    print(f"任务包已生成: {tid}")
