"""
Workflow Engine 单元测试
"""
import sys
import os
import json

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    # __file__ 在 exec() 沙箱中未定义
    sys.path.insert(0, os.getcwd())

from tools.workflow_engine import (
    WorkflowEngine, WorkflowError,
    Node, Edge, WorkflowDefinition, WorkflowInstance,
    NodeStatus, WorkflowStatus,
    TOOL_DEFINITION, _engine,
)


def test_enums():
    """枚举值"""
    assert NodeStatus.PENDING.value == "待执行"
    assert NodeStatus.RUNNING.value == "执行中"
    assert NodeStatus.DONE.value == "已完成"
    assert NodeStatus.FAILED.value == "失败"
    assert NodeStatus.SKIPPED.value == "已跳过"

    assert WorkflowStatus.PENDING.value == "待开始"
    assert WorkflowStatus.RUNNING.value == "运行中"
    assert WorkflowStatus.PAUSED.value == "已暂停"
    assert WorkflowStatus.DONE.value == "已完成"
    assert WorkflowStatus.FAILED.value == "失败"
    print("✅ 测试1 枚举: 通过")


def test_dataclasses():
    """数据模型"""
    node = Node(name="step1", description="第一步", timeout=60)
    assert node.name == "step1"
    assert node.timeout == 60

    edge = Edge(from_node="step1", to_node="step2", condition="result=ok")
    assert edge.from_node == "step1"
    assert edge.condition == "result=ok"

    wf_def = WorkflowDefinition(
        name="test_wf",
        description="测试工作流",
        nodes=[node],
        edges=[edge],
        start_node="step1",
        end_nodes=["step1"],
    )
    assert wf_def.name == "test_wf"
    assert len(wf_def.nodes) == 1

    print("✅ 测试2 数据模型: 通过")


def test_define_workflow():
    """定义工作流"""
    engine = WorkflowEngine()

    result = engine.define(
        name="测试工作流",
        description="一个测试",
        nodes='[{"name":"step1","description":"第一步"},'
              '{"name":"step2","description":"第二步"},'
              '{"name":"step3","description":"第三步"}]',
        edges='[{"from_node":"step1","to_node":"step2"},'
              '{"from_node":"step2","to_node":"step3"}]',
        start_node="step1",
        end_nodes='["step3"]',
    )
    assert "已定义" in result
    assert "测试工作流" in result
    assert "step1" in result

    # 验证内部
    assert "测试工作流" in engine._definitions
    wf = engine._definitions["测试工作流"]
    assert len(wf.nodes) == 3
    assert len(wf.edges) == 2
    assert wf.start_node == "step1"

    print("✅ 测试3 定义工作流: 通过")


def test_define_empty_name():
    """空名称"""
    engine = WorkflowEngine()
    try:
        engine.define(name="", nodes='[{"name":"x"}]')
        assert False
    except WorkflowError:
        pass
    print("✅ 测试4 空名称拒绝: 通过")


def test_define_no_nodes():
    """无节点"""
    engine = WorkflowEngine()
    try:
        engine.define(name="empty", nodes="[]")
        assert False
    except WorkflowError:
        pass
    print("✅ 测试5 无节点拒绝: 通过")


def test_define_invalid_json():
    """无效 JSON"""
    engine = WorkflowEngine()
    try:
        engine.define(name="bad", nodes="not json")
        assert False
    except WorkflowError:
        pass
    print("✅ 测试6 无效 JSON 拒绝: 通过")


def test_start_and_step():
    """启动和步进"""
    engine = WorkflowEngine()

    # 先定义
    engine.define(
        name="步进测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )

    # 启动
    result = engine.start("步进测试")
    assert "已启动" in result
    assert "WF-" in result

    # 提取 instance_id
    instance_id = ""
    for line in result.split("\n"):
        if "实例ID:" in line:
            instance_id = line.split("实例ID:")[1].strip()
            break

    assert instance_id.startswith("WF-")

    # 步进 A -> B
    result = engine.step(instance_id, node_result="A完成")
    assert "前进" in result or "下一步" in result
    assert "B" in result

    # 步进 B -> C
    result = engine.step(instance_id, node_result="B完成")
    assert "前进" in result or "下一步" in result
    assert "C" in result

    # 步进 C -> 完成
    result = engine.step(instance_id, node_result="C完成")
    assert "已完成" in result

    print("✅ 测试7 启动步进: 通过")


def test_workflow_pause_resume():
    """暂停恢复"""
    engine = WorkflowEngine()

    engine.define(
        name="暂停测试",
        nodes='[{"name":"X"},{"name":"Y"}]',
        edges='[{"from_node":"X","to_node":"Y"}]',
        start_node="X",
        end_nodes='["Y"]',
    )

    result = engine.start("暂停测试")
    instance_id = ""
    for line in result.split("\n"):
        if "实例ID:" in line:
            instance_id = line.split("实例ID:")[1].strip()
            break

    # 暂停
    result = engine.pause(instance_id)
    assert "已暂停" in result

    # 恢复
    result = engine.resume(instance_id)
    assert "已恢复" in result

    print("✅ 测试8 暂停恢复: 通过")


def test_workflow_status():
    """状态查询"""
    engine = WorkflowEngine()

    engine.define(
        name="状态测试",
        nodes='[{"name":"P"},{"name":"Q"}]',
        start_node="P",
        end_nodes='["Q"]',
    )

    result = engine.start("状态测试")
    instance_id = ""
    for line in result.split("\n"):
        if "实例ID:" in line:
            instance_id = line.split("实例ID:")[1].strip()
            break

    result = engine.get_status(instance_id)
    assert "状态测试" in result or "P" in result
    assert "运行中" in result
    assert "P" in result

    # 不存在
    try:
        engine.get_status("nonexistent")
        assert False
    except WorkflowError:
        pass

    print("✅ 测试9 状态查询: 通过")


def test_workflow_list_delete():
    """列表和删除"""
    engine = WorkflowEngine()

    result = engine.list_workflows()
    assert len(result) > 0

    engine.define(
        name="删除测试",
        nodes='[{"name":"del"}]',
    )

    result = engine.delete("删除测试")
    assert "已删除" in result
    assert "删除测试" not in engine._definitions

    # 删除不存在
    try:
        engine.delete("nonexistent")
        assert False
    except WorkflowError:
        pass

    print("✅ 测试10 列表删除: 通过")


def test_condition_evaluation():
    """条件评估"""
    # 测试静态方法
    engine = WorkflowEngine()

    # 布尔条件
    assert engine._evaluate_condition("ok", {"ok": True}) is True
    assert engine._evaluate_condition("ok", {"ok": False}) is False
    assert engine._evaluate_condition("missing", {}) is False

    # 等值条件
    assert engine._evaluate_condition("status=done", {"status": "done"}) is True
    assert engine._evaluate_condition("status=fail", {"status": "done"}) is False

    # 空条件
    assert engine._evaluate_condition("", {}) is True

    print("✅ 测试11 条件评估: 通过")


def test_start_nonexistent_workflow():
    """启动不存在的工作流"""
    engine = WorkflowEngine()
    try:
        engine.start("nonexistent")
        assert False
    except WorkflowError:
        pass
    print("✅ 测试12 启动不存在工作流: 通过")


def test_tool_definition():
    """工具定义"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "workflow"
    actions = TOOL_DEFINITION["function"]["parameters"]["properties"]["action"]["enum"]
    assert "define" in actions
    assert "start" in actions
    assert "step" in actions
    assert "pause" in actions
    assert "resume" in actions
    assert "status" in actions
    assert "list" in actions
    assert "delete" in actions
    print("✅ 测试13 工具定义: 通过")


def test_execute_tool():
    """工具入口"""
    from tools.workflow_engine import execute_workflow_tool

    # define
    result = execute_workflow_tool({
        "action": "define",
        "workflow_name": "入口测试",
        "nodes": '[{"name":"n1"},{"name":"n2"}]',
        "start_node": "n1",
        "end_nodes": '["n2"]',
    })
    assert "已定义" in result

    # list
    result = execute_workflow_tool({"action": "list"})
    assert len(result) > 0

    # start
    result = execute_workflow_tool({
        "action": "start",
        "workflow_name": "入口测试",
    })
    assert "已启动" in result

    # 无效操作
    result = execute_workflow_tool({"action": "invalid"})
    assert "未知" in result

    # cleanup
    execute_workflow_tool({"action": "delete", "workflow_name": "入口测试"})

    print("✅ 测试14 工具入口: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Workflow Engine 单元测试")
    print("=" * 50)
    test_enums()
    test_dataclasses()
    test_define_workflow()
    test_define_empty_name()
    test_define_no_nodes()
    test_define_invalid_json()
    test_start_and_step()
    test_workflow_pause_resume()
    test_workflow_status()
    test_workflow_list_delete()
    test_condition_evaluation()
    test_start_nonexistent_workflow()
    test_tool_definition()
    test_execute_tool()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
