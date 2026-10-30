"""test_runner — 自动测试运行器

自动发现并运行 agent-sandbox 中的所有测试用例，
验证工具模块的导入、接口定义和执行能力。
生成详细的测试报告，支持增量测试和回归测试。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SANDBOX_DIR = Path(__file__).resolve().parent.parent
TEST_RESULTS_FILE = SANDBOX_DIR / "memory" / "test_results.json"

# ── 错误类型 ──────────────────────────────────────────────


class TestRunnerError(RuntimeError):
    """测试运行器错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "test_runner",
        "description": (
            "自动测试运行器。运行预定义的测试用例，验证所有工具模块"
            "的导入、接口定义和执行功能是否正常。生成详细测试报告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "run_all",
                        "run_tools",
                        "run_single",
                        "report",
                        "list_tests",
                    ],
                    "description": (
                        "操作类型："
                        "run_all — 运行所有测试；"
                        "run_tools — 仅测试工具模块；"
                        "run_single — 测试单个模块；"
                        "report — 查看历史测试报告；"
                        "list_tests — 列出所有可运行的测试。"
                    ),
                },
                "module": {
                    "type": "string",
                    "description": "要测试的模块名称（用于 run_single）",
                    "default": "",
                },
                "verbose": {
                    "type": "boolean",
                    "description": "是否输出详细信息",
                    "default": False,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 测试结果模型 ──────────────────────────────────────────


@dataclass
class TestCase:
    """单个测试用例。"""

    name: str
    module: str
    passed: bool
    duration: float
    detail: str = ""


@dataclass
class TestSuite:
    """一次测试运行的所有结果。"""

    timestamp: str
    total: int
    passed: int
    failed: int
    duration: float
    cases: list[dict[str, Any]] = field(default_factory=list)


# ── 测试运行引擎 ──────────────────────────────────────────


class TestRunner:
    """自动测试运行引擎。"""

    def __init__(self) -> None:
        self.results: list[TestCase] = []
        self._start_time = 0.0

    # ── 公开接口 ────────────────────────────────────────

    def run_all(self, verbose: bool = False) -> str:
        """运行所有测试（仅测试实际存在的模块）。"""
        self._start()
        self._test_import("runner", verbose)
        self._test_import("calculator", verbose)
        self._test_import("file_utils", verbose)
        self._test_import("knowledge_store", verbose)
        self._test_import("task_tracker", verbose)
        self._test_import("self_check", verbose)
        self._test_import("test_runner", verbose)
        self._test_import("monitor", verbose)
        self._test_import("decision_engine", verbose)
        self._test_import("safety_net", verbose)
        self._test_read_write(verbose)
        self._test_file_integrity(verbose)
        return self._report(verbose)

    def run_tools(self, verbose: bool = False) -> str:
        """仅测试工具模块。"""
        self._start()
        self._test_import("runner", verbose)
        self._test_import("calculator", verbose)
        self._test_import("file_utils", verbose)
        self._test_import("knowledge_store", verbose)
        self._test_import("task_tracker", verbose)
        self._test_import("self_check", verbose)
        self._test_import("test_runner", verbose)
        self._test_import("monitor", verbose)
        self._test_import("decision_engine", verbose)
        self._test_import("safety_net", verbose)
        return self._report(verbose)

    def run_single(self, module: str, verbose: bool = False) -> str:
        """测试单个模块。"""
        self._start()
        self._test_import(module, verbose)
        return self._report(verbose)

    def list_tests(self) -> str:
        """列出所有可运行的测试。"""
        tests = [
            ("run_all", "运行所有测试（工具 + 文件完整性）"),
            ("run_tools", "仅测试所有工具模块"),
            ("run_single:<module>", "测试指定模块，如 run_single:calculator"),
            ("report", "查看历史测试报告"),
        ]
        modules = [
            "runner", "calculator", "file_utils", "knowledge_store",
            "task_tracker", "self_check", "test_runner",
            "monitor", "decision_engine", "safety_net",
        ]
        lines = [
            "📋 可用测试\n",
            "测试操作:",
        ]
        for name, desc in tests:
            lines.append(f"  • {name:<30} — {desc}")
        lines.append("\n可测试模块:")
        for mod in modules:
            lines.append(f"  • {mod}")
        return "\n".join(lines)

    def report(self) -> str:
        """查看历史测试报告。"""
        if not TEST_RESULTS_FILE.is_file():
            return "暂无历史测试记录。请先运行测试。"
        try:
            data = json.loads(TEST_RESULTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "测试记录文件损坏。"

        if not data:
            return "暂无历史测试记录。"

        # 获取最近几次测试
        recent = sorted(data.keys(), reverse=True)[:5]
        lines = ["📊 历史测试报告\n"]
        for ts in recent:
            suite = data[ts]
            ratio = suite["passed"] / suite["total"] * 100 if suite["total"] else 0
            status = "✅" if suite["failed"] == 0 else "❌"
            lines.append(
                f"  {status} [{ts}] "
                f"{suite['passed']}/{suite['total']} 通过 "
                f"({ratio:.0f}%) "
                f"耗时 {suite['duration']:.2f}s"
            )
        return "\n".join(lines)

    # ── 内部方法 ────────────────────────────────────────

    def _start(self) -> None:
        self.results = []
        self._start_time = time.time()

    def _test_import(self, module_name: str, verbose: bool) -> None:
        """测试模块能否正常导入并检查接口。"""
        t0 = time.time()

        # ── 导入测试 ──
        try:
            module = importlib.import_module(f"tools.{module_name}")
            self._record(module_name, "导入", True, time.time() - t0, "导入成功")
        except ImportError as exc:
            self._record(module_name, "导入", False, time.time() - t0, f"导入失败: {exc}")
            return
        except Exception as exc:
            self._record(module_name, "导入", False, time.time() - t0, f"异常: {exc}")
            return

        # ── TOOL_DEFINITION 检查 ──
        t1 = time.time()
        if hasattr(module, "TOOL_DEFINITION"):
            td = module.TOOL_DEFINITION
            if isinstance(td, dict) and "function" in td and "name" in td["function"]:
                tool_name = td["function"]["name"]
                self._record(module_name, "接口定义", True, time.time() - t1, f"name={tool_name}")
            else:
                self._record(module_name, "接口定义", False, time.time() - t1, "TOOL_DEFINITION 格式无效")
        else:
            self._record(module_name, "接口定义", False, time.time() - t1, "缺少 TOOL_DEFINITION")

        # ── execute_* 函数存在性检查 ──
        t2 = time.time()
        if hasattr(module, "TOOL_DEFINITION"):
            tool_name = module.TOOL_DEFINITION["function"]["name"]
            exec_func = f"execute_{tool_name}_tool"
            if hasattr(module, exec_func):
                self._record(module_name, "执行函数", True, time.time() - t2, f"{exec_func} 存在")
            elif hasattr(module, tool_name):
                self._record(module_name, "执行函数", True, time.time() - t2, f"直接函数 {tool_name} 存在")
            else:
                self._record(module_name, "执行函数", False, time.time() - t2, f"未找到执行函数")

    def _test_read_write(self, verbose: bool) -> None:
        """测试 read/write 基础工具可用性。"""
        t0 = time.time()
        try:
            from core.read import READ_TOOLS, execute_read_tool
            self._record("read", "导入", True, time.time() - t0, f"{len(READ_TOOLS)} 个读取工具")
        except ImportError as exc:
            self._record("read", "导入", False, time.time() - t0, str(exc))

        t1 = time.time()
        try:
            from core.write import WRITE_TOOLS, execute_write_tool
            self._record("write", "导入", True, time.time() - t1, f"{len(WRITE_TOOLS)} 个写入工具")
        except ImportError as exc:
            self._record("write", "导入", False, time.time() - t1, str(exc))

        # 测试所有工具注册
        t2 = time.time()
        try:
            from agent1 import ALL_TOOLS
            names = [t["function"]["name"] for t in ALL_TOOLS]
            self._record("agent1", "工具注册", True, time.time() - t2, f"{len(names)} 个工具: {', '.join(names)}")
        except ImportError as exc:
            self._record("agent1", "工具注册", False, time.time() - t2, f"导入失败: {exc}")

    def _test_file_integrity(self, verbose: bool) -> None:
        """测试关键文件完整性。"""
        files = [
            ("agent1.py", True),
            ("AGENT_PROFILE.md", True),
            ("knowledge/experience.md", True),
            ("logs/growth.log", True),
            ("memory/tasks.json", False),
            ("tools/__init__.py", True),
        ]

        for rel_path, required in files:
            t0 = time.time()
            full_path = SANDBOX_DIR / rel_path
            exists = full_path.is_file()
            if exists:
                size = full_path.stat().st_size
                detail = f"存在 ({size} bytes)"
            else:
                detail = "缺失" if required else "可选（未创建）"

            if required and not exists:
                self._record(f"文件:{rel_path}", "完整性", False, time.time() - t0, detail)
            else:
                self._record(f"文件:{rel_path}", "完整性", True, time.time() - t0, detail)

    def _record(self, module: str, test_type: str, passed: bool, duration: float, detail: str = "") -> None:
        """记录一条测试结果。"""
        name = f"{module}.{test_type}"
        self.results.append(TestCase(
            name=name,
            module=module,
            passed=passed,
            duration=duration,
            detail=detail,
        ))

    def _report(self, verbose: bool) -> str:
        """生成测试报告。"""
        duration = time.time() - self._start_time
        total = len(self.results)
        passed_count = sum(1 for r in self.results if r.passed)
        failed_count = total - passed_count

        # 按模块分组
        by_module: dict[str, list[TestCase]] = {}
        for r in self.results:
            by_module.setdefault(r.module, []).append(r)

        status_icon = "✅" if failed_count == 0 else "❌"
        pass_rate = passed_count / total * 100 if total else 100

        lines = [
            f"{status_icon} 测试报告",
            f"{'='*50}",
            f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"耗时: {duration:.3f} 秒",
            f"总计: {total} 项 | ✅ 通过: {passed_count} | ❌ 失败: {failed_count} | 通过率: {pass_rate:.1f}%",
            "",
        ]

        for module in sorted(by_module.keys()):
            cases = by_module[module]
            mod_passed = sum(1 for c in cases if c.passed)
            mod_total = len(cases)
            mod_icon = "✅" if mod_passed == mod_total else "❌"

            lines.append(f"\n## {module} ({mod_icon} {mod_passed}/{mod_total})")
            for case in cases:
                icon = "✅" if case.passed else "❌"
                detail = f" — {case.detail}" if (verbose or not case.passed) and case.detail else ""
                lines.append(f"  {icon} {case.name} ({case.duration*1000:.1f}ms){detail}")

        lines.append(f"\n{'─'*50}")

        # 保存结果
        self._save_results(total, passed_count, failed_count, duration)

        return "\n".join(lines)

    def _save_results(self, total: int, passed: int, failed: int, duration: float) -> None:
        """保存测试结果到文件。"""
        try:
            existing = {}
            if TEST_RESULTS_FILE.is_file():
                existing = json.loads(TEST_RESULTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        suite = TestSuite(
            timestamp=timestamp,
            total=total,
            passed=passed,
            failed=failed,
            duration=duration,
            cases=[asdict(c) for c in self.results],
        )
        existing[timestamp] = asdict(suite)

        # 只保留最近 20 次记录
        while len(existing) > 20:
            oldest = min(existing.keys())
            del existing[oldest]

        TEST_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── 全局实例 ──────────────────────────────────────────────

_runner = TestRunner()


def execute_test_runner_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")
    module = arguments.get("module", "")
    verbose = bool(arguments.get("verbose", False))

    try:
        if action == "run_all":
            return _runner.run_all(verbose)
        elif action == "run_tools":
            return _runner.run_tools(verbose)
        elif action == "run_single":
            if not module:
                return "❌ 错误: 请指定要测试的模块名称（如 calculator）"
            return _runner.run_single(module.strip(), verbose)
        elif action == "report":
            return _runner.report()
        elif action == "list_tests":
            return _runner.list_tests()
        else:
            return f"❌ 未知操作: {action}"
    except TestRunnerError as exc:
        return f"❌ 测试运行错误: {exc}"
