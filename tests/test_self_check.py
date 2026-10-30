"""
Self Check 单元测试（v2.0 — 对齐源码 API）
==========================================
测试 HealthCheck 所有公共方法及工具入口。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.self_check import HealthCheck, execute_self_check_tool


def test_create_health_check():
    """创建 HealthCheck"""
    hc = HealthCheck()
    assert hc is not None
    print("✅ 创建HealthCheck: 通过")


def test_check_all():
    """全面检查 — 返回 str"""
    hc = HealthCheck()
    result = hc.check_all()
    assert isinstance(result, str), f"期望 str，实际 {type(result)}"
    assert "健康检查报告" in result
    assert "工具模块" in result or "📁" in result
    print("✅ 全面检查: 通过")


def test_check_tools():
    """工具检查 — 返回 str"""
    hc = HealthCheck()
    result = hc.check_tools()
    assert isinstance(result, str), f"期望 str，实际 {type(result)}"
    assert "健康检查报告" in result
    print("✅ 工具检查: 通过")


def test_check_config():
    """配置检查 — 返回 str"""
    hc = HealthCheck()
    result = hc.check_config()
    assert isinstance(result, str), f"期望 str，实际 {type(result)}"
    assert "健康检查报告" in result
    print("✅ 配置检查: 通过")


def test_check_memory():
    """记忆系统检查 — 返回 str"""
    hc = HealthCheck()
    result = hc.check_memory()
    assert isinstance(result, str), f"期望 str，实际 {type(result)}"
    assert "健康检查报告" in result
    print("✅ 记忆检查: 通过")


def test_check_verbose():
    """详细模式 — 返回 str"""
    hc = HealthCheck()
    result = hc.check_all(verbose=True)
    assert isinstance(result, str), f"期望 str，实际 {type(result)}"
    print("✅ 详细模式: 通过")


def test_check_scope_all():
    """scope=all — 通过工具入口"""
    result = execute_self_check_tool({"scope": "all"})
    assert isinstance(result, str)
    assert "健康检查报告" in result
    print("✅ scope=all: 通过")


def test_check_scope_tools():
    """scope=tools — 通过工具入口"""
    result = execute_self_check_tool({"scope": "tools"})
    assert isinstance(result, str)
    assert "健康检查报告" in result
    print("✅ scope=tools: 通过")


def test_check_scope_config():
    """scope=config — 通过工具入口"""
    result = execute_self_check_tool({"scope": "config"})
    assert isinstance(result, str)
    assert "健康检查报告" in result
    print("✅ scope=config: 通过")


def test_check_scope_memory():
    """scope=memory — 通过工具入口"""
    result = execute_self_check_tool({"scope": "memory"})
    assert isinstance(result, str)
    assert "健康检查报告" in result
    print("✅ scope=memory: 通过")


def test_tool_definition():
    """工具定义"""
    from tools.self_check import TOOL_DEFINITION
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "self_check"
    print("✅ 工具定义: 通过")


def test_execute_tool_scope_all():
    """工具入口 — scope=all"""
    result = execute_self_check_tool({"scope": "all"})
    assert isinstance(result, str)
    assert len(result) > 0
    print("✅ 工具入口 scope=all: 通过")


def test_execute_tool_scope_tools():
    """工具入口 — scope=tools"""
    result = execute_self_check_tool({"scope": "tools"})
    assert isinstance(result, str)
    print("✅ 工具入口 scope=tools: 通过")


def test_execute_tool_scope_config():
    """工具入口 — scope=config"""
    result = execute_self_check_tool({"scope": "config"})
    assert isinstance(result, str)
    print("✅ 工具入口 scope=config: 通过")


def test_execute_tool_scope_memory():
    """工具入口 — scope=memory"""
    result = execute_self_check_tool({"scope": "memory"})
    assert isinstance(result, str)
    print("✅ 工具入口 scope=memory: 通过")


def test_execute_tool_all_verbose():
    """工具入口 — scope=all verbose=True"""
    result = execute_self_check_tool({"scope": "all", "verbose": True})
    assert isinstance(result, str)
    print("✅ 工具入口 all verbose: 通过")


def test_execute_tool_invalid_scope():
    """工具入口 — 无效 scope"""
    result = execute_self_check_tool({"scope": "nonexistent"})
    assert isinstance(result, str)
    assert "未知" in result
    print("✅ 工具入口 无效scope: 通过")


def test_execute_tool_defaults():
    """工具入口 — 空参数（使用默认值 scope=all）"""
    result = execute_self_check_tool({})
    assert isinstance(result, str)
    assert "健康检查报告" in result
    print("✅ 工具入口 默认参数: 通过")


def test_module_structure():
    """模块结构"""
    import tools.self_check as sc
    assert hasattr(sc, 'HealthCheck')
    assert hasattr(sc, 'execute_self_check_tool')
    assert hasattr(sc, 'TOOL_DEFINITION')
    print("✅ 模块结构: 通过")


if __name__ == "__main__":
    all_tests = [
        test_create_health_check,
        test_check_all,
        test_check_tools,
        test_check_config,
        test_check_memory,
        test_check_verbose,
        test_check_scope_all,
        test_check_scope_tools,
        test_check_scope_config,
        test_check_scope_memory,
        test_tool_definition,
        test_execute_tool_scope_all,
        test_execute_tool_scope_tools,
        test_execute_tool_scope_config,
        test_execute_tool_scope_memory,
        test_execute_tool_all_verbose,
        test_execute_tool_invalid_scope,
        test_execute_tool_defaults,
        test_module_structure,
    ]

    passed = 0
    failed = 0

    print("=" * 50)
    print("🧪 Self Check 单元测试 (v2.0)")
    print("=" * 50)

    for test in all_tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__}: {e}")

    print("=" * 50)
    print(f"🎉 测试完成: {passed} 通过, {failed} 失败")
    print("=" * 50)
