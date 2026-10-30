"""Bootstrap — 统一环境入口脚本。

解决所有智能体 / 工具中 "agent-sandbox 下的包无法导入" 的路径问题。

用法（在项目根目录执行）：
    python agent-sandbox/bootstrap.py -c "from evolver.health_dashboard import HealthDashboard; print('OK')"
    python agent-sandbox/bootstrap.py --check        # 验证所有关键包可导入
    python agent-sandbox/bootstrap.py --install      # pip install -e agent-sandbox（推荐）

原理：
    将 agent-sandbox/ 加到 sys.path 首位，
    确保 evolver / tools / memory / knowledge 全局可导入。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "agent-sandbox"

# 关键包列表，用于 --check 验证
KEY_IMPORTS = [
    "evolver",
    "evolver.health_dashboard",
    "evolver.safe_deploy",
    "evolver.usage_analyzer",
    "evolver.tech_radar",
    "evolver.env_awareness",
    "evolver.evolution_strategy",
    "evolver.audit_log",
    "tools",
    "tools.runner",
    "memory.blackboard",
    "memory.blackboard.blackboard_manager",
]


def ensure_path() -> None:
    """将 agent-sandbox 注入 sys.path，去重。"""
    sandbox_str = str(SANDBOX)
    if sandbox_str not in sys.path:
        sys.path.insert(0, sandbox_str)


def run_code(code: str) -> None:
    """在正确的 sys.path 下执行 Python 代码片段。"""
    ensure_path()
    exec(code)


def check_imports() -> int:
    """验证所有关键包是否能正常导入。返回失败数。"""
    ensure_path()
    failures = 0
    max_width = max(len(name) for name in KEY_IMPORTS)
    for name in KEY_IMPORTS:
        try:
            __import__(name)
            print(f"  ✅  {name:<{max_width}}  导入成功")
        except Exception as exc:
            print(f"  ❌  {name:<{max_width}}  导入失败: {exc}")
            failures += 1
    return failures


def install_editable() -> int:
    """以可编辑模式安装 agent-sandbox 包（推荐）。"""
    print(f"→ pip install -e {SANDBOX}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(SANDBOX)],
        capture_output=False,
        cwd=str(ROOT),
    )
    if result.returncode == 0:
        print("✅ 安装成功 — evolver/tools/memory/knowledge 现在全局可用")
    else:
        print(f"❌ 安装失败，返回码: {result.returncode}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent-sandbox 统一环境入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python agent-sandbox/bootstrap.py -c "from evolver.health_dashboard import HealthDashboard; hd=HealthDashboard(); print(hd.aggregate())"
  python agent-sandbox/bootstrap.py --check
  python agent-sandbox/bootstrap.py --install
        """,
    )
    parser.add_argument("-c", "--code", help="要执行的 Python 代码片段")
    parser.add_argument("--check", action="store_true", help="验证所有关键包可导入")
    parser.add_argument("--install", action="store_true", help="pip install -e agent-sandbox（推荐）")
    args = parser.parse_args()

    if args.install:
        sys.exit(install_editable())

    if args.check:
        print("📦 关键包导入验证:")
        failures = check_imports()
        if failures:
            print(f"\n❌ {failures} 个包导入失败")
            sys.exit(1)
        else:
            print(f"\n✅ 全部 {len(KEY_IMPORTS)} 个包导入成功")
        return

    if args.code:
        run_code(args.code)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
