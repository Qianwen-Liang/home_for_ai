"""self_check — 工具自检与健康检查系统

对 Agent 1 的各个工具模块进行健康检查，确保所有组件正常运作。
生成健康报告，帮助快速定位问题。
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent

# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "self_check",
        "description": (
            "工具自检与健康检查系统。检查所有工具模块能否正常导入，"
            "验证工具接口是否正确，生成完整的健康报告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all", "tools", "config", "memory"],
                    "description": (
                        "检查范围："
                        "all — 全面检查所有组件；"
                        "tools — 仅检查工具模块；"
                        "config — 仅检查配置文件；"
                        "memory — 仅检查记忆系统。"
                    ),
                    "default": "all",
                },
                "verbose": {
                    "type": "boolean",
                    "description": "是否输出详细信息，默认为 False",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
    },
}


# ── 健康检查引擎 ──────────────────────────────────────────


class HealthCheck:
    """健康检查引擎。"""

    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self._start_time = datetime.now()

    def check_all(self, verbose: bool = False) -> str:
        """执行全面健康检查。"""
        self.results = []

        # 1. 检查工具模块（★T2824：自动发现全部 tools/ 模块）
        for module_name in self._discover_modules():
            self._check_tools_module(module_name, None)

        # 2. 检查配置文件
        self._check_config()

        # 3. 检查目录结构
        self._check_directories()

        # 4. 检查记忆系统
        self._check_memory()

        return self._generate_report(verbose)

    def check_tools(self, verbose: bool = False) -> str:
        """检查全部 tools/ 模块（★T2824：自动发现，不再硬编码清单）。

        原实现硬编码 10 个模块名，而 tools/ 下有 43 个——覆盖率仅 23%，
        报告却显示「🟢 优」。新增模块永远不会被自检，等于自检慢慢失真。
        改为自动发现：新增模块自动纳入，无需维护清单。
        """
        self.results = []
        for module_name in self._discover_modules():
            self._check_tools_module(module_name, None)
        return self._generate_report(verbose)

    @staticmethod
    def _discover_modules() -> list[str]:
        """发现 tools/ 下所有模块（排除 __init__）。

        外部依据：go-sundheit 的健康检查设计是「注册式/自动发现」而非静态清单，
        理由一致——手工清单必然滞后于代码增长。
        """
        tools_dir = SANDBOX_DIR / "tools"
        if not tools_dir.is_dir():
            return []
        return sorted(
            p.stem for p in tools_dir.glob("*.py")
            if p.stem != "__init__" and not p.stem.startswith(".")
        )

    def check_config(self, verbose: bool = False) -> str:
        """检查配置文件。"""
        self.results = []
        self._check_config()
        return self._generate_report(verbose)

    def check_memory(self, verbose: bool = False) -> str:
        """检查记忆系统。"""
        self.results = []
        self._check_memory()
        return self._generate_report(verbose)

    def _check_tools_module(self, module_name: str, tool_name: str | None = None) -> None:
        """检查一个 tools/ 模块。

        ★T2824：区分两类模块，避免把「基础设施没有 TOOL_DEFINITION」误报为警告。
          - 工具实现：应有 TOOL_DEFINITION + 执行函数
          - 基础设施（errors/budget/registry/middleware 等）：只需能导入
        """
        try:
            module = importlib.import_module(f"tools.{module_name}")

            resolved_tool = tool_name
            # 检查 TOOL_DEFINITION
            if hasattr(module, "TOOL_DEFINITION"):
                td = module.TOOL_DEFINITION
                assert isinstance(td, dict), "TOOL_DEFINITION 必须是 dict"
                assert "function" in td, "TOOL_DEFINITION 缺少 function"
                assert "name" in td["function"], "TOOL_DEFINITION.function 缺少 name"
                actual_name = td["function"]["name"]
                resolved_tool = resolved_tool or actual_name
                self.results.append({
                    "type": "tool",
                    "name": module_name,
                    "status": "✅",
                    "detail": f"TOOL_DEFINITION OK (name={actual_name})",
                })
            else:
                self.results.append({
                    "type": "tool",
                    "name": module_name,
                    "status": "✅",
                    "detail": "非工具模块（可导入）",
                })
                resolved_tool = None

            # 检查 execute_* 函数（仅对有 TOOL_DEFINITION 的模块）
            if resolved_tool:
                func_name = f"execute_{resolved_tool}_tool"
                if hasattr(module, func_name):
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "✅",
                        "detail": f"函数 {func_name} 存在",
                    })
                elif hasattr(module, resolved_tool):
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "✅",
                        "detail": f"函数 {resolved_tool} 存在",
                    })
                else:
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "⚠️",
                        "detail": f"有 TOOL_DEFINITION 但未找到执行函数 {func_name}",
                    })

        except ImportError as exc:
            self.results.append({
                "type": "tool",
                "name": module_name,
                "status": "❌",
                "detail": f"导入失败: {exc}",
            })
        except Exception as exc:
            self.results.append({
                "type": "tool",
                "name": module_name,
                "status": "❌",
                "detail": f"检查异常: {exc}\n{traceback.format_exc()}",
            })

    def _check_config(self) -> None:
        """检查配置文件。"""
        # 检查 AGENT_PROFILE.md
        profile = SANDBOX_DIR / "AGENT_PROFILE.md"
        if profile.is_file():
            self.results.append({
                "type": "config",
                "name": "AGENT_PROFILE.md",
                "status": "✅",
                "detail": f"存在 ({profile.stat().st_size} bytes)",
            })
        else:
            self.results.append({
                "type": "config",
                "name": "AGENT_PROFILE.md",
                "status": "❌",
                "detail": "文件缺失",
            })

        # 检查 knowledge/experience.md
        exp = SANDBOX_DIR / "knowledge" / "experience.md"
        if exp.is_file():
            self.results.append({
                "type": "config",
                "name": "knowledge/experience.md",
                "status": "✅",
                "detail": f"存在 ({exp.stat().st_size} bytes)",
            })
        else:
            self.results.append({
                "type": "config",
                "name": "knowledge/experience.md",
                "status": "⚠️",
                "detail": "文件缺失",
            })

        # 检查 logs/growth.log
        growth = SANDBOX_DIR / "logs" / "growth.log"
        if growth.is_file():
            self.results.append({
                "type": "config",
                "name": "logs/growth.log",
                "status": "✅",
                "detail": f"存在 ({growth.stat().st_size} bytes)",
            })
        else:
            self.results.append({
                "type": "config",
                "name": "logs/growth.log",
                "status": "⚠️",
                "detail": "文件缺失",
            })

    def _check_directories(self) -> None:
        """检查必要目录结构。"""
        dirs = [
            ("tools", True),
            ("knowledge", True),
            ("logs", True),
            ("memory", True),
            ("tests", True),
            (".backups", True),
        ]

        for dir_name, required in dirs:
            dir_path = SANDBOX_DIR / dir_name
            if dir_path.is_dir():
                contents = list(dir_path.iterdir())
                self.results.append({
                    "type": "directory",
                    "name": dir_name,
                    "status": "✅",
                    "detail": f"存在 ({len(contents)} 个条目)",
                })
            elif required:
                self.results.append({
                    "type": "directory",
                    "name": dir_name,
                    "status": "❌",
                    "detail": "缺失（必需目录）",
                })
            else:
                self.results.append({
                    "type": "directory",
                    "name": dir_name,
                    "status": "⚠️",
                    "detail": "缺失（可选目录）",
                })

    def _check_memory(self) -> None:
        """检查记忆系统。"""
        memory_dir = SANDBOX_DIR / "memory"

        if not memory_dir.is_dir():
            self.results.append({
                "type": "memory",
                "name": "memory/",
                "status": "❌",
                "detail": "记忆目录不存在",
            })
            return

        # 检查 tasks.json
        tasks = memory_dir / "tasks.json"
        if tasks.is_file():
            self.results.append({
                "type": "memory",
                "name": "memory/tasks.json",
                "status": "✅",
                "detail": f"存在 ({tasks.stat().st_size} bytes)",
            })
        else:
            self.results.append({
                "type": "memory",
                "name": "memory/tasks.json",
                "status": "ℹ️",
                "detail": "不存在（将在首次使用时创建）",
            })

    def _generate_report(self, verbose: bool) -> str:
        """生成健康报告。"""
        elapsed = (datetime.now() - self._start_time).total_seconds()

        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "✅")
        warnings = sum(1 for r in self.results if r["status"] in ("⚠️", "ℹ️"))
        failed = sum(1 for r in self.results if r["status"] == "❌")

        health = "🟢 优" if failed == 0 and warnings == 0 else (
            "🟡 良" if failed == 0 else "🔴 差"
        )

        lines = [
            f"🏥 Agent 1 健康检查报告",
            f"{'='*50}",
            f"检查时间: {self._start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"耗时: {elapsed:.2f} 秒",
            f"健康状态: {health}",
            f"{'='*50}",
            f"总检查项: {total} | ✅ 通过: {passed} | ⚠️ 警告: {warnings} | ❌ 失败: {failed}",
        ]

        # ★T2824：显式披露模块覆盖率。
        # 旧版报「20 项全通过 / 🟢 优」，实际只检查了 10/43 个模块（23%），
        # 健康度是用未覆盖的样本算出来的。现在把覆盖率摆到报告里，
        # 避免「项数多」被误读为「覆盖全」。
        tool_names = {r["name"] for r in self.results if r["type"] == "tool"}
        if tool_names:
            discovered = self._discover_modules()
            covered = len(tool_names & set(discovered))
            pct = (covered / len(discovered) * 100) if discovered else 0.0
            lines.append(f"模块覆盖: {covered}/{len(discovered)}（{pct:.0f}%）")

        lines.append("")

        # 按类型分组显示
        categories = {"tool": "🔧 工具模块", "config": "📄 配置文件", "directory": "📁 目录结构", "memory": "🧠 记忆系统"}

        for cat_key, cat_title in categories.items():
            items = [r for r in self.results if r["type"] == cat_key]
            if not items:
                continue

            lines.append(f"\n## {cat_title}")
            for item in items:
                if verbose or item["status"] != "✅":
                    lines.append(f"  {item['status']} {item['name']}: {item['detail']}")
                else:
                    lines.append(f"  {item['status']} {item['name']}")

        lines.append(f"\n{'─'*50}")
        lines.append(f"报告结束 | 共 {total} 项检查")

        return "\n".join(lines)


# ── 全局实例 ──────────────────────────────────────────────

_checker = HealthCheck()


def execute_self_check_tool(arguments: dict[str, Any]) -> str:
    scope = arguments.get("scope", "all")
    verbose = bool(arguments.get("verbose", False))

    # 每次调用重置计时起点，避免复用模块导入时刻导致耗时虚高
    _checker._start_time = datetime.now()

    if scope == "all":
        return _checker.check_all(verbose)
    elif scope == "tools":
        return _checker.check_tools(verbose)
    elif scope == "config":
        return _checker.check_config(verbose)
    elif scope == "memory":
        return _checker.check_memory(verbose)
    else:
        return f"未知检查范围: {scope}，可用: all, tools, config, memory"
