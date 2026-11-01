"""role_system 契约修复 + 工具命名约定测试（T2828）。

背景：self_check 自动发现后报出
  ⚠️ role_system: 有 TOOL_DEFINITION 但未找到执行函数 execute_role_system_tool
原因：模块把执行函数命名为 `execute_role_tool`，与项目约定
      `execute_{TOOL_DEFINITION.function.name}_tool` 不一致。

本文件既锁定该修复，也用一条**通用约定检查**防止未来出现同类问题——
只修一个模块而不加通用约束，等于等着下一个模块再犯一遍。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.self_check import HealthCheck, execute_self_check_tool  # noqa: E402


# ── 1. 本次修复 ─────────────────────────────────────────

def test_role_system_has_conventional_executor() -> None:
    mod = importlib.import_module("tools.role_system")
    name = mod.TOOL_DEFINITION["function"]["name"]
    assert callable(getattr(mod, f"execute_{name}_tool", None)), \
        f"role_system 缺少约定命名的执行函数 execute_{name}_tool"


def test_role_system_backward_alias_kept() -> None:
    """旧名保留为别名，防止遗漏的外部调用方受影响。"""
    mod = importlib.import_module("tools.role_system")
    assert callable(getattr(mod, "execute_role_tool", None))


def test_role_system_executor_works() -> None:
    mod = importlib.import_module("tools.role_system")
    out = mod.execute_role_system_tool({"action": "list_roles"})
    assert isinstance(out, str) and out


def test_self_check_reports_no_warning_for_role_system() -> None:
    out = execute_self_check_tool({"scope": "tools"})
    bad = [line for line in out.splitlines()
           if "role_system" in line and ("⚠️" in line or "❌" in line)]
    assert not bad, f"role_system 仍有告警: {bad}"


# ── 2. 通用约定检查（防复发） ───────────────────────────

def test_all_tool_modules_follow_naming_convention() -> None:
    """凡声明了 TOOL_DEFINITION 的模块，都必须有 execute_{name}_tool 或同名函数。

    这是本次缺陷的通用形式：单个模块命名不一致 → 契约检查报错。
    与其逐个修，不如一次性断言全部符合约定。
    """
    violations: list[str] = []
    for module_name in HealthCheck._discover_modules():
        try:
            mod = importlib.import_module(f"tools.{module_name}")
        except Exception:  # noqa: BLE001  导入失败由 self_check 单独报告
            continue
        td = getattr(mod, "TOOL_DEFINITION", None)
        if not isinstance(td, dict):
            continue
        func = td.get("function") or {}
        tool_name = func.get("name")
        if not tool_name:
            violations.append(f"{module_name}: TOOL_DEFINITION 缺少 function.name")
            continue
        if not (callable(getattr(mod, f"execute_{tool_name}_tool", None))
                or callable(getattr(mod, tool_name, None))):
            violations.append(f"{module_name}: 缺少执行函数 execute_{tool_name}_tool")
    assert not violations, "命名约定违规:\n  " + "\n  ".join(violations)


def test_self_check_is_fully_green() -> None:
    """回归：修复后自检应全绿（69/69，0 警告 0 失败）。

    注意这个"绿"是真实的——模块覆盖已达 100%，
    与改造前"覆盖 23% 却报绿"有本质区别。
    """
    out = execute_self_check_tool({"scope": "tools"})
    assert "100%" in out.split("模块覆盖")[1].split("\n")[0]
    assert "⚠️ 警告: 0" in out
    assert "❌ 失败: 0" in out
