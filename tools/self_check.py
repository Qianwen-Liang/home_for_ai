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

        # 1. 检查工具模块（仅检查实际存在的模块）
        self._check_tools_module("runner", "run_command")
        self._check_tools_module("calculator", "calculate")
        self._check_tools_module("file_utils", "file_utils")
        self._check_tools_module("knowledge_store", "knowledge")
        self._check_tools_module("task_tracker", "task_tracker")
        self._check_tools_module("self_check", "self_check")
        self._check_tools_module("test_runner", "test_runner")
        self._check_tools_module("monitor", "monitor")
        self._check_tools_module("decision_engine", "decision_engine")
        self._check_tools_module("safety_net", "safety_net")

        # 2. 检查配置文件
        self._check_config()

        # 3. 检查目录结构
        self._check_directories()

        # 4. 检查记忆系统
        self._check_memory()

        return self._generate_report(verbose)

    def check_tools(self, verbose: bool = False) -> str:
        """仅检查工具模块。"""
        self.results = []
        self._check_tools_module("runner", "run_command")
        self._check_tools_module("calculator", "calculate")
        self._check_tools_module("file_utils", "file_utils")
        self._check_tools_module("knowledge_store", "knowledge")
        self._check_tools_module("task_tracker", "task_tracker")
        self._check_tools_module("self_check", "self_check")
        self._check_tools_module("test_runner", "test_runner")
        self._check_tools_module("monitor", "monitor")
        self._check_tools_module("decision_engine", "decision_engine")
        self._check_tools_module("safety_net", "safety_net")
        return self._generate_report(verbose)

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

    def _check_tools_module(self, module_name: str, tool_name: str | None) -> None:
        """检查一个工具模块。"""
        try:
            module = importlib.import_module(f"tools.{module_name}")

            # 检查 TOOL_DEFINITION
            if hasattr(module, "TOOL_DEFINITION"):
                td = module.TOOL_DEFINITION
                assert isinstance(td, dict), "TOOL_DEFINITION 必须是 dict"
                assert "function" in td, "TOOL_DEFINITION 缺少 function"
                assert "name" in td["function"], "TOOL_DEFINITION.function 缺少 name"
                actual_name = td["function"]["name"]
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
                    "status": "⚠️",
                    "detail": "缺少 TOOL_DEFINITION",
                })

            # 检查 execute_* 函数
            if tool_name:
                func_name = f"execute_{tool_name}_tool"
                # 也尝试直接函数名
                if hasattr(module, func_name):
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "✅",
                        "detail": f"函数 {func_name} 存在",
                    })
                elif tool_name and hasattr(module, tool_name):
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "✅",
                        "detail": f"函数 {tool_name} 存在",
                    })
                else:
                    self.results.append({
                        "type": "tool",
                        "name": module_name,
                        "status": "⚠️",
                        "detail": f"未找到执行函数",
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
            "",
        ]

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
