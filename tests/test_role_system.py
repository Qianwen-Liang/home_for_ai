"""
Role System 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.role_system import (
    RoleSystem, RoleType, RoleSystemError, ROLE_LIBRARY, DEFAULT_ROLE_SEQUENCE
)


def test_role_library():
    """测试角色库完整性"""
    assert len(ROLE_LIBRARY) == 4, f"应有4个角色: {len(ROLE_LIBRARY)}"
    for name in ["分析师", "设计师", "执行者", "审查者"]:
        assert name in ROLE_LIBRARY, f"缺少角色: {name}"
        role = ROLE_LIBRARY[name]
        assert role.name, f"{name} 应有 name"
        assert role.objective, f"{name} 应有 objective"
        assert len(role.checklist) >= 4, f"{name} 检查清单应>=4项"
        assert role.thinking_pattern, f"{name} 应有思维模式"
    print("✅ 测试1 角色库完整性: 通过")


def test_default_sequence():
    """测试默认角色序列"""
    assert len(DEFAULT_ROLE_SEQUENCE) == 4
    assert DEFAULT_ROLE_SEQUENCE == ["分析师", "设计师", "执行者", "审查者"]
    print("✅ 测试2 默认序列: 通过")


def test_switch_role():
    """测试角色切换"""
    rs = RoleSystem()

    # 初始角色
    result = rs.current()
    assert "分析师" in result, f"初始应为分析师: {result}"
    print("✅ 测试3 初始角色: 通过")

    # 切换到设计师
    result = rs.switch("设计师")
    assert "设计师" in result, f"切换失败: {result}"
    assert "🎨" in result, f"应有设计师图标: {result}"
    print("✅ 测试4 切换到设计师: 通过")

    # 确认当前角色
    result = rs.current()
    assert "设计师" in result, f"当前应为设计师: {result}"
    print("✅ 测试5 确认当前: 通过")

    # 切换到执行者
    rs.switch("执行者")
    result = rs.current()
    assert "执行者" in result, f"当前应为执行者: {result}"
    print("✅ 测试6 切换到执行者: 通过")

    # 切换到审查者
    rs.switch("审查者")
    result = rs.current()
    assert "审查者" in result, f"当前应为审查者: {result}"
    print("✅ 测试7 切换到审查者: 通过")


def test_invalid_role():
    """测试无效角色"""
    rs = RoleSystem()
    try:
        rs.switch("不存在的角色")
        assert False, "应拒绝无效角色"
    except RoleSystemError as e:
        assert "未知角色" in str(e) or "可用角色" in str(e)
    print("✅ 测试8 拒绝无效角色: 通过")


def test_list_roles():
    """测试列出角色"""
    rs = RoleSystem()
    result = rs.list_roles()
    for name in ["分析师", "设计师", "执行者", "审查者"]:
        assert name in result, f"列表中应有{name}"
    assert "建议切换顺序" in result, f"应有建议: {result}"
    print("✅ 测试9 列出角色: 通过")


def test_checklist():
    """测试检查清单"""
    rs = RoleSystem()
    rs.switch("审查者")
    result = rs.checklist()
    assert "审查者" in result, f"应有审查者: {result}"
    assert "✓" in result, f"应有勾选项: {result}"
    print("✅ 测试10 检查清单: 通过")


def test_role_actions():
    """测试各角色动作"""
    rs = RoleSystem()

    # analyze
    result = rs.analyze("测试问题", "测试上下文")
    assert "分析师" in result, f"analyze应有分析师: {result}"
    assert "测试问题" in result, f"analyze应有任务: {result}"
    assert "测试上下文" in result, f"analyze应有上下文: {result}"
    print("✅ 测试11 analyze: 通过")

    # design
    result = rs.design("设计方案", "")
    assert "设计师" in result, f"design应有设计师: {result}"
    assert "设计方案" in result, f"design应有任务: {result}"
    print("✅ 测试12 design: 通过")

    # execute
    result = rs.execute("执行任务", "")
    assert "执行者" in result, f"execute应有执行者: {result}"
    assert "执行任务" in result, f"execute应有任务: {result}"
    print("✅ 测试13 execute: 通过")

    # review
    result = rs.review("审查结果", "")
    assert "审查者" in result, f"review应有审查者: {result}"
    assert "审查结果" in result, f"review应有任务: {result}"
    print("✅ 测试14 review: 通过")


def test_history():
    """测试角色切换历史"""
    rs = RoleSystem()
    rs.switch("设计师")
    rs.switch("执行者")
    rs.switch("审查者")

    result = rs.history()
    assert "分析师" in result, f"历史中应有分析师: {result}"
    assert "设计师" in result, f"历史中应有设计师: {result}"
    assert "执行者" in result, f"历史中应有执行者: {result}"
    assert "审查者" in result, f"历史中应有审查者: {result}"
    print("✅ 测试15 切换历史: 通过")


def test_reset():
    """测试重置"""
    rs = RoleSystem()
    rs.switch("执行者")
    rs.reset()

    result = rs.current()
    assert "分析师" in result, f"重置后应为分析师: {result}"
    result = rs.history()
    assert "暂无" in result or "0 次" in result, f"历史应清空: {result}"
    print("✅ 测试16 重置: 通过")


def test_full_sequence():
    """测试完整序列"""
    rs = RoleSystem()

    sequence = []
    for role_name in DEFAULT_ROLE_SEQUENCE:
        rs.switch(role_name)
        result = rs.current()
        assert role_name in result, f"切换失败: {role_name}"
        sequence.append(role_name)

    assert sequence == DEFAULT_ROLE_SEQUENCE
    print("✅ 测试17 完整序列: 通过")


def test_tool_entry():
    """测试工具入口函数"""
    from tools.role_system import execute_role_tool

    # current
    result = execute_role_tool({"action": "current"})
    assert "角色" in result, f"current 应返回角色: {result}"
    print("✅ 测试18 工具入口 current: 通过")

    # list_roles
    result = execute_role_tool({"action": "list_roles"})
    assert "分析师" in result, f"list_roles应有角色: {result}"
    print("✅ 测试19 工具入口 list_roles: 通过")

    # switch
    result = execute_role_tool({"action": "switch", "role": "设计师"})
    assert "设计师" in result, f"switch应成功: {result}"
    print("✅ 测试20 工具入口 switch: 通过")

    # checklist
    result = execute_role_tool({"action": "checklist"})
    assert "设计师" in result, f"checklist应有角色: {result}"
    print("✅ 测试21 工具入口 checklist: 通过")

    # analyze
    result = execute_role_tool({"action": "analyze", "task": "测试分析"})
    assert "分析师" in result, f"analyze应切换角色: {result}"
    print("✅ 测试22 工具入口 analyze: 通过")

    # 未知操作
    result = execute_role_tool({"action": "unknown"})
    assert "未知" in result, f"未知操作应提示: {result}"
    print("✅ 测试23 工具入口 未知操作: 通过")

    # 无效角色
    result = execute_role_tool({"action": "switch", "role": "invalid"})
    assert "错误" in result, f"无效角色应报错: {result}"
    print("✅ 测试24 工具入口 无效角色: 通过")

    # history
    result = execute_role_tool({"action": "history"})
    assert "分析师" in result, f"history应有记录: {result}"
    print("✅ 测试25 工具入口 history: 通过")

    # reset
    result = execute_role_tool({"action": "reset"})
    assert "重置" in result, f"reset应成功: {result}"
    print("✅ 测试26 工具入口 reset: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Role System 单元测试")
    print("=" * 50)
    test_role_library()
    print()
    test_default_sequence()
    print()
    test_switch_role()
    print()
    test_invalid_role()
    print()
    test_list_roles()
    print()
    test_checklist()
    print()
    test_role_actions()
    print()
    test_history()
    print()
    test_reset()
    print()
    test_full_sequence()
    print()
    test_tool_entry()
    print()
    print("=" * 50)
    print("🎉 所有 Role System 测试通过！")
    print("=" * 50)
