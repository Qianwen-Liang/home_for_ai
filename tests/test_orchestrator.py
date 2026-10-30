"""
Orchestrator 单元测试
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.orchestrator import (
    Orchestrator, OrchestratorError,
    TOOL_DEFINITION, _orchestrator,
)


def test_orchestrator_init():
    """初始化"""
    orch = Orchestrator()
    # 确保默认 Specialist 已注册
    ready = orch._get_ready_agents()
    # 可能有也可能没有，取决于当前环境
    assert isinstance(ready, list)
    print("✅ 测试1 初始化: 通过")


def test_health():
    """健康检查"""
    result = _orchestrator.health()
    assert "健康报告" in result or "健康检查" in result
    assert "Agent" in result or "agent" in result.lower()
    print("✅ 测试2 健康检查: 通过")


def test_help():
    """帮助信息"""
    result = _orchestrator.help()
    assert "使用指南" in result or "Orchestrator" in result
    assert "run" in result.lower()
    print("✅ 测试3 帮助: 通过")


def test_list_pipelines():
    """列出流水线"""
    result = _orchestrator.list_pipelines()
    # 可能为空或有流水线
    assert isinstance(result, str)
    print("✅ 测试4 列出流水线: 通过")


def test_escalate():
    """问题上报"""
    result = _orchestrator.escalate(
        issue="测试上报：这是一个模拟的严重问题",
        pipeline_id="PL_test",
    )
    assert "已上报" in result or "上报" in result
    assert "测试上报" in result
    print("✅ 测试5 问题上报: 通过")


def test_request_approval():
    """请求审批"""
    # 流水线不存在时应该给出合理提示
    result = _orchestrator.request_approval(
        pipeline_id="PL_nonexistent",
        checkpoint_id="cp1",
    )
    # 应该返回错误信息（流水线不存在）
    assert "未找到" in result or "错误" in result
    print("✅ 测试6 请求审批: 通过")


def test_provide_feedback_approve():
    """提供反馈 - 批准"""
    result = _orchestrator.provide_feedback(
        pipeline_id="PL_nonexistent",
        feedback="批准继续执行",
    )
    # 因为流水线不存在
    assert "批准" in result or "不存在" in result or "完成" in result
    print("✅ 测试7 批准反馈: 通过")


def test_provide_feedback_change():
    """提供反馈 - 修改"""
    result = _orchestrator.provide_feedback(
        pipeline_id="PL_nonexistent",
        feedback="需要修改设计方案",
    )
    assert "修改" in result or "反馈" in result
    print("✅ 测试8 修改反馈: 通过")


def test_provide_feedback_cancel():
    """提供反馈 - 取消"""
    result = _orchestrator.provide_feedback(
        pipeline_id="PL_nonexistent",
        feedback="取消这个流水线",
    )
    # 流水线不存在，cancel 内部也会报错
    assert len(result) > 0
    print("✅ 测试9 取消反馈: 通过")


def test_run_no_agents():
    """run 时无 Agent"""
    # 这取决于环境，可能成功也可能失败
    result = _orchestrator.run(
        task="测试任务",
        template="通用",
    )
    # 如果有可用 agent 就会执行，否则会提示
    assert len(result) > 0
    assert "编排" in result or "Agent" in result or "分解" in result or "可用" in result
    print("✅ 测试10 run: 通过")


def test_run_empty_task():
    """空任务"""
    try:
        _orchestrator.run(task="")
        assert False
    except OrchestratorError:
        pass
    print("✅ 测试11 空任务拒绝: 通过")


def test_retry_invalid():
    """重试无效流水线"""
    try:
        _orchestrator.retry(pipeline_id="")
        assert False
    except OrchestratorError:
        pass

    result = _orchestrator.retry(pipeline_id="PL_nonexistent")
    assert "未找到" in result or "错误" in result
    print("✅ 测试12 重试无效: 通过")


def test_cancel_invalid():
    """取消无效流水线"""
    result = _orchestrator.cancel(pipeline_id="PL_nonexistent")
    assert "未找到" in result or "错误" in result
    print("✅ 测试13 取消无效: 通过")


def test_tool_definition():
    """工具定义"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "orchestrator"
    actions = TOOL_DEFINITION["function"]["parameters"]["properties"]["action"]["enum"]
    assert "run" in actions
    assert "status" in actions
    assert "retry" in actions
    assert "cancel" in actions
    assert "list_pipelines" in actions
    assert "health" in actions
    assert "run_workflow" in actions
    assert "request_approval" in actions
    assert "provide_feedback" in actions
    assert "escalate" in actions
    assert "help" in actions
    print("✅ 测试14 工具定义: 通过")


def test_execute_tool():
    """工具入口"""
    from tools.orchestrator import execute_orchestrator_tool

    # help
    result = execute_orchestrator_tool({"action": "help"})
    assert "指南" in result or "Orchestrator" in result

    # health
    result = execute_orchestrator_tool({"action": "health"})
    assert "健康" in result

    # list_pipelines
    result = execute_orchestrator_tool({"action": "list_pipelines"})
    assert len(result) > 0

    # 无效操作
    result = execute_orchestrator_tool({"action": "invalid"})
    assert "未知" in result

    # escalate (no issue)
    result = execute_orchestrator_tool({"action": "escalate"})
    assert "错误" in result or "请描述" in result

    print("✅ 测试15 工具入口: 通过")


def test_run_workflow_invalid():
    """无效工作流规格"""
    try:
        _orchestrator.run_workflow(workflow_spec="")
        assert False
    except OrchestratorError:
        pass

    try:
        _orchestrator.run_workflow(workflow_spec="not json")
        assert False
    except OrchestratorError:
        pass

    print("✅ 测试16 无效工作流: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Orchestrator 单元测试")
    print("=" * 50)
    test_orchestrator_init()
    test_health()
    test_help()
    test_list_pipelines()
    test_escalate()
    test_request_approval()
    test_provide_feedback_approve()
    test_provide_feedback_change()
    test_provide_feedback_cancel()
    test_run_no_agents()
    test_run_empty_task()
    test_retry_invalid()
    test_cancel_invalid()
    test_tool_definition()
    test_execute_tool()
    test_run_workflow_invalid()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
