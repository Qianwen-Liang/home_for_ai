"""
Agent Profile 单元测试
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.agent_profile import (
    AgentProfileManager, AgentProfile, PermissionConfig,
    AgentProfileError, TOOL_DEFINITION,
)


def test_permission_config():
    """PermissionConfig 数据模型"""
    # 默认值
    pc = PermissionConfig()
    assert pc.read_paths == []
    assert pc.write_paths == []
    assert pc.forbidden_paths == []
    assert pc.allow_run_command is False
    assert pc.allow_network is False
    assert pc.max_tool_steps == 100

    # 自定义值
    pc2 = PermissionConfig(
        read_paths=["agent-sandbox/**"],
        write_paths=["agent-sandbox/memory/**"],
        forbidden_paths=["**/.env"],
        allow_run_command=True,
        allow_network=True,
        max_tool_steps=50,
        note="测试",
    )
    assert pc2.read_paths == ["agent-sandbox/**"]
    assert pc2.allow_run_command is True
    assert pc2.max_tool_steps == 50

    # to_dict / from_dict 往返
    d = pc2.to_dict()
    pc3 = PermissionConfig.from_dict(d)
    assert pc3.read_paths == pc2.read_paths
    assert pc3.max_tool_steps == pc2.max_tool_steps
    print("✅ 测试1 PermissionConfig: 通过")


def test_agent_profile_dataclass():
    """AgentProfile 数据模型"""
    p = AgentProfile(
        agent_id="test_agent",
        name="测试Agent",
        role="测试角色",
        system_prompt="你是一个测试智能体",
        allowed_tools=["read_file", "knowledge"],
        capabilities=["research", "testing"],
        permissions=PermissionConfig(
            read_paths=["agent-sandbox/**"],
            allow_run_command=False,
        ),
        priority="高",
        status="active",
        inherit_tools_from="agent1",
    )

    # 基本属性
    assert p.agent_id == "test_agent"
    assert p.name == "测试Agent"
    assert p.priority == "高"
    assert p.status == "active"
    assert len(p.allowed_tools) == 2

    # to_dict / from_dict 往返
    d = p.to_dict()
    p2 = AgentProfile.from_dict(d)
    assert p2.agent_id == p.agent_id
    assert p2.allowed_tools == p.allowed_tools
    assert p2.permissions.read_paths == p.permissions.read_paths
    print("✅ 测试2 AgentProfile 数据模型: 通过")


def test_path_permission_check():
    """路径权限检查"""
    p = AgentProfile(
        agent_id="test",
        name="Test",
        permissions=PermissionConfig(
            read_paths=["agent-sandbox/**", "supervision/*"],
            write_paths=["agent-sandbox/memory/**"],
            forbidden_paths=["**/.env", "**/secret.txt"],
        ),
    )

    # 读取权限
    assert p.check_read_permission("agent-sandbox/file.txt") is True
    assert p.check_read_permission("supervision/notes.md") is True
    assert p.check_read_permission("/etc/passwd") is False
    assert p.check_read_permission("agent-sandbox/.env") is False  # forbidden
    assert p.check_read_permission("supervision/secret.txt") is False  # forbidden

    # 写入权限
    assert p.check_write_permission("agent-sandbox/memory/test.json") is True
    assert p.check_write_permission("agent-sandbox/other.txt") is False
    assert p.check_write_permission("agent-sandbox/memory/.env") is False

    # 空权限（允许所有）
    p2 = AgentProfile(agent_id="open", name="Open")
    assert p2.check_read_permission("anything") is True
    assert p2.check_write_permission("anything") is True
    assert p2.check_read_permission(".env") is True  # 无 forbidden 限制

    print("✅ 测试3 路径权限检查: 通过")


def test_get_summary():
    """摘要生成"""
    p = AgentProfile(
        agent_id="summarizer",
        name="摘要测试Agent",
        role="测试摘要生成",
        system_prompt="你是一个用于测试摘要生成的智能体，"
                      "拥有较长的系统提示词，用于验证截断逻辑。",
        allowed_tools=["read_file", "knowledge", "web_search",
                       "write_file", "monitor", "self_check",
                       "test_runner", "file_utils", "calculate",
                       "safety_net"],
        capabilities=["research", "analysis"],
        permissions=PermissionConfig(
            read_paths=["agent-sandbox/**"],
            write_paths=["agent-sandbox/memory/**"],
            forbidden_paths=["**/.env"],
            allow_run_command=True,
        ),
        status="active",
        priority="高",
        inherit_tools_from="agent1",
        created_at="2025-01-01 00:00:00",
    )

    summary = p.get_summary()
    assert "🟢" in summary, "active 状态应有 🟢"
    assert "summarizer" in summary
    assert "摘要测试Agent" in summary
    assert "+" in summary or "…" in summary, "工具过多应有省略"
    assert "继承" in summary or "agent1" in summary
    print("✅ 测试4 摘要生成: 通过")


def test_manager_initialization():
    """管理器初始化"""
    mgr = AgentProfileManager()
    # 应该有默认配置
    profiles = mgr.list_profiles()
    assert "agent1" in profiles, "应有 agent1 默认配置"
    assert "researcher" in profiles or "暂无" not in profiles

    # 获取 agent1
    result = mgr.get_profile("agent1")
    assert "agent1" in result
    assert "Orchestrator" in result or "主智能体" in result
    print("✅ 测试5 管理器初始化: 通过")


def test_manager_set_get_delete():
    """CRUD 操作"""
    mgr = AgentProfileManager()

    # 创建新配置
    result = mgr.set_profile(
        agent_id="crud_test",
        name="CRUD测试Agent",
        role="CRUD测试",
        system_prompt="用于CRUD测试",
        allowed_tools='["read_file","knowledge"]',
        capabilities='["testing","debugging"]',
        read_paths='["agent-sandbox/**"]',
        write_paths='["agent-sandbox/memory/**"]',
        priority="中",
        allow_network=True,
        max_tool_steps=50,
    )
    assert "创建" in result or "更新" in result

    # 获取
    result = mgr.get_profile("crud_test")
    assert "CRUD测试Agent" in result
    assert "read_file" in result
    assert "50" in result or "50" in result.lower()

    # 更新
    result = mgr.set_profile(
        agent_id="crud_test",
        name="CRUD测试Agent-改",
        allowed_tools='["knowledge"]',
    )
    assert "更新" in result

    result = mgr.get_profile("crud_test")
    assert "CRUD测试Agent-改" in result

    # 停用
    result = mgr.deactivate("crud_test")
    assert "停用" in result

    # 删除
    result = mgr.delete_profile("crud_test")
    assert "已删除" in result

    # 确认删除
    try:
        mgr.get_profile("crud_test")
        assert False, "应该抛出异常"
    except AgentProfileError:
        pass

    print("✅ 测试6 CRUD 操作: 通过")


def test_manager_activate_deactivate_suspend():
    """状态管理"""
    mgr = AgentProfileManager()

    # 创建测试 agent
    mgr.set_profile(
        agent_id="state_test", name="状态测试",
        system_prompt="test",
        allowed_tools='["read_file"]',
        capabilities='["testing"]',
    )

    # 激活
    result = mgr.activate("state_test")
    assert "已激活" in result

    # 挂起
    result = mgr.suspend("state_test")
    assert "已挂起" in result

    # 挂起后激活会失败
    try:
        mgr.activate("state_test")
        assert False, "挂起后应拒绝激活"
    except AgentProfileError:
        pass

    # 清理（先停用再删除... 但已挂起无法直接删除）
    # 先通过重新激活绕过... 实际上需要先 deactivate 再 delete
    # 但 suspend 后无法 activate，需要特殊处理
    # 这里直接清理内部状态
    try:
        mgr._profiles["state_test"].status = "inactive"
        mgr.delete_profile("state_test")
    except AgentProfileError:
        mgr._profiles.pop("state_test", None)
        mgr._save()

    # 清理 activate 时自动注册到 agent_manager 的 state_test，避免污染后续测试
    try:
        from tools.agent_manager import _manager as am
        am.unregister("state_test")
    except Exception:
        pass

    print("✅ 测试7 状态管理: 通过")


def test_manager_agent1_protection():
    """Agent 1 保护"""
    mgr = AgentProfileManager()

    # 不能挂起 agent1
    try:
        mgr.suspend("agent1")
        assert False, "应拒绝挂起 agent1"
    except AgentProfileError:
        pass

    # 不能删除活跃的 agent1
    try:
        mgr.delete_profile("agent1")
        assert False, "应拒绝删除活跃 agent1"
    except AgentProfileError:
        pass

    print("✅ 测试8 Agent 1 保护: 通过")


def test_manager_export_import():
    """导出导入"""
    mgr = AgentProfileManager()

    # 导出全部
    result = mgr.export_profile()
    assert "已导出" in result

    # 导出单个
    result = mgr.export_profile("agent1")
    assert "已导出" in result

    print("✅ 测试9 导出: 通过")


def test_manager_compare():
    """配置比较"""
    mgr = AgentProfileManager()

    result = mgr.compare("researcher", "writer")
    assert "researcher" in result
    assert "writer" in result
    assert "⚡" in result or "✅" in result

    # 无效比较
    try:
        mgr.compare("nonexistent", "writer")
        assert False
    except AgentProfileError:
        pass

    print("✅ 测试10 配置比较: 通过")


def test_resolve_effective_tools():
    """工具继承解析"""
    mgr = AgentProfileManager()

    # researcher 继承自 agent1
    effective = mgr.resolve_effective_tools("researcher")
    assert len(effective) > len(["web_search", "knowledge", "read_file", "file_utils"])
    assert "web_search" in effective
    assert "knowledge" in effective
    # 继承来的
    assert "monitor" in effective or "task_tracker" in effective

    # agent1 不继承
    effective_a1 = mgr.resolve_effective_tools("agent1")
    assert len(effective_a1) > 10

    # 不存在的 agent
    assert mgr.resolve_effective_tools("nonexistent") == []

    print("✅ 测试11 工具继承: 通过")


def test_check_permission():
    """权限检查 API"""
    mgr = AgentProfileManager()

    result = mgr.check_permission("agent1", "agent-sandbox/test.txt", "read")
    assert "允许" in result

    result = mgr.check_permission("agent1", "agent-sandbox/test.txt", "write")
    assert "允许" in result

    result = mgr.check_permission("agent1", ".env", "read")
    assert "拒绝" in result

    result = mgr.check_permission("writer", "agent-sandbox/test.md", "write")
    assert "允许" in result or "拒绝" in result

    try:
        mgr.check_permission("nonexistent", "path", "read")
        assert False
    except AgentProfileError:
        pass

    print("✅ 测试12 权限检查 API: 通过")


def test_help():
    """帮助信息"""
    help_text = AgentProfileManager.help()
    assert "配置管理" in help_text or "Agent Profile" in help_text
    assert "list" in help_text.lower()
    print("✅ 测试13 帮助信息: 通过")


def test_tool_definition():
    """工具定义结构"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "agent_profile"
    props = TOOL_DEFINITION["function"]["parameters"]["properties"]
    assert "action" in props
    assert props["action"]["type"] == "string"
    print("✅ 测试14 工具定义: 通过")


def test_execute_tool():
    """工具入口函数"""
    from tools.agent_profile import execute_agent_profile_tool

    # help
    result = execute_agent_profile_tool({"action": "help"})
    assert "配置管理" in result or "Agent Profile" in result

    # list
    result = execute_agent_profile_tool({"action": "list"})
    assert "agent1" in result

    # get
    result = execute_agent_profile_tool({"action": "get", "agent_id": "agent1"})
    assert "agent1" in result

    # get nonexistent
    result = execute_agent_profile_tool({"action": "get", "agent_id": "no_such"})
    assert "错误" in result or "未找到" in result

    # 无效操作
    result = execute_agent_profile_tool({"action": "invalid"})
    assert "未知" in result

    print("✅ 测试15 工具入口: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Agent Profile 单元测试")
    print("=" * 50)
    test_permission_config()
    test_agent_profile_dataclass()
    test_path_permission_check()
    test_get_summary()
    test_manager_initialization()
    test_manager_set_get_delete()
    test_manager_activate_deactivate_suspend()
    test_manager_agent1_protection()
    test_manager_export_import()
    test_manager_compare()
    test_resolve_effective_tools()
    test_check_permission()
    test_help()
    test_tool_definition()
    test_execute_tool()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
