"""launch_worker.py — 可靠地后台启动研究 worker（真正脱离会话进程）

用 subprocess.DETACHED_PROCESS 启动 research_worker.py，本脚本立即退出，
使 run_command 立即返回，worker 在后台独立运行（不受 120 秒超时影响）。

用法：
    python research/launch_worker.py <task_id>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python research/launch_worker.py <task_id>")
        sys.exit(1)

    task_id = sys.argv[1]
    log_path = SANDBOX_DIR / "memory" / "offline" / task_id / "bg_stdout.log"
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

    print(f"✅ 离线研究任务已后台启动: {task_id}")


if __name__ == "__main__":
    main()
