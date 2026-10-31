"""self_check 自动发现与覆盖率测试（T2824）。

背景：原实现硬编码 10 个模块名，而 tools/ 下有 42 个——覆盖率仅 23%，
报告却显示「20 项全通过 / 🟢 优」。健康度是用未覆盖的样本算出来的。

本次改为自动发现（外部依据：go-sundheit 的健康检查采用注册式而非静态清单），
并把覆盖率显式写进报告。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.self_check import HealthCheck, execute_self_check_tool  # noqa: E402


# ── 1. 自动发现 ─────────────────────────────────────────

def test_discover_returns_all_tool_modules() -> None:
    """必须发现 tools/ 下全部模块，不能漏。"""
    discovered = HealthCheck._discover_modules()
    actual = {p.stem for p in (ROOT / "tools").glob("*.py")} - {"__init__"}
    assert set(discovered) == actual, "发现的模块集合与磁盘文件不一致"


def test_discover_excludes_init() -> None:
    assert "__init__" not in HealthCheck._discover_modules()


def test_discover_is_sorted_and_nonempty() -> None:
    discovered = HealthCheck._discover_modules()
    assert discovered == sorted(discovered)
    assert len(discovered) >= 40, f"模块数异常偏少: {len(discovered)}"


# ── 2. 覆盖率必须真实 ───────────────────────────────────

def test_coverage_reaches_all_modules() -> None:
    """回归：曾只覆盖 10/42（23%）。现在报告必须显示 100%。"""
    out = execute_self_check_tool({"scope": "tools"})
    assert "模块覆盖" in out, "报告未披露覆盖率"
    assert "100%" in out.split("模块覆盖")[1].split("\n")[0], "覆盖率未达 100%"


def test_new_module_would_be_covered(tmp_path, monkeypatch) -> None:
    """新增模块应自动纳入，无需维护清单。"""
    tools_dir = ROOT / "tools"
    fake = tools_dir / "_tmp_probe_module.py"
    fake.write_text("VALUE = 1\n", encoding="utf-8")
    try:
        discovered = HealthCheck._discover_modules()
        assert "_tmp_probe_module" in discovered, "新增模块未被自动发现"
    finally:
        fake.unlink(missing_ok=True)


# ── 3. 分类正确性：基础设施不该被误报 ───────────────────

def test_infrastructure_modules_not_warned() -> None:
    """errors/budget/registry/middleware 本就不提供 TOOL_DEFINITION。

    原实现会把它们标为「⚠️ 缺少 TOOL_DEFINITION」，产生噪音。
    """
    checker = HealthCheck()
    checker.results = []
    for name in ("errors", "budget", "registry", "middleware"):
        checker._check_tools_module(name, None)
    for r in checker.results:
        assert r["status"] != "⚠️", f"{r['name']} 被误报为警告: {r['detail']}"


def test_tool_module_with_definition_is_ok() -> None:
    checker = HealthCheck()
    checker.results = []
    checker._check_tools_module("calculator", None)
    assert all(r["status"] == "✅" for r in checker.results)


def test_missing_execute_function_warns() -> None:
    """有 TOOL_DEFINITION 但无执行函数 → 必须警告（当前 role_system 即此情况）。"""
    checker = HealthCheck()
    checker.results = []
    checker._check_tools_module("role_system", None)
    statuses = [r["status"] for r in checker.results]
    assert "⚠️" in statuses, "契约不完整应产生警告"


# ── 4. 健康状态诚实反映问题 ─────────────────────────────

def test_health_is_not_falsely_green() -> None:
    """存在导入失败时，健康状态不得为「优」。

    这是本次改造的核心：旧版在只覆盖 23% 的情况下报「🟢 优」。
    debugger_agent 当前存在循环导入，因此必须体现为问题。
    """
    out = execute_self_check_tool({"scope": "tools"})
    has_failure = "❌" in out
    if has_failure:
        assert "🟢 优" not in out, "存在失败项却报告健康状态为优"


def test_report_shape_stable() -> None:
    """报告的对外结构不能变（下游依赖）。"""
    out = execute_self_check_tool({"scope": "tools"})
    for key in ("健康状态", "总检查项", "模块覆盖", "工具模块"):
        assert key in out, f"报告缺少字段: {key}"


def test_unknown_scope_message() -> None:
    out = execute_self_check_tool({"scope": "nonexistent"})
    assert "未知" in out
