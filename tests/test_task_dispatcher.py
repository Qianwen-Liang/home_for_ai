"""
Task Dispatcher 单元测试
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.task_dispatcher import (
    TaskDispatcher, DispatchError,
    Subtask, Pipeline, SubtaskStatus, PipelineStatus,
    DECOMPOSITION_TEMPLATES,
    TOOL_DEFINITION, _dispatcher,
)


def test_enums():
    """枚举值"""
    assert SubtaskStatus.PENDING.value == "pending"
    assert SubtaskStatus.ASSIGNED.value == "assigned"
    assert SubtaskStatus.RUNNING.value == "running"
    assert SubtaskStatus.DONE.value == "done"
    assert SubtaskStatus.FAILED.value == "failed"
    assert SubtaskStatus.SKIPPED.value == "skipped"

    assert PipelineStatus.CREATED.value == "created"
    assert PipelineStatus.RUNNING.value == "running"
    assert PipelineStatus.PARTIAL.value == "partial"
    assert PipelineStatus.DONE.value == "done"
    assert PipelineStatus.FAILED.value == "failed"
    print("✅ 测试1 枚举: 通过")


def test_dataclasses():
    """数据模型"""
    st = Subtask(
        task_id="S1",
        description="测试子任务",
        required_capability="research",
        preferred_agent_type="researcher",
    )
    assert st.task_id == "S1"
    assert st.status == "pending"
    assert st.depends_on == []

    pipeline = Pipeline(
        pipeline_id="PL_test",
        name="测试流水线",
        description="一个测试",
        subtasks=[st],
    )
    assert pipeline.pipeline_id == "PL_test"
    assert len(pipeline.subtasks) == 1
    print("✅ 测试2 数据模型: 通过")


def test_templates():
    """分解模板"""
    # 检查所有预定义模板
    for keyword, steps in DECOMPOSITION_TEMPLATES.items():
        assert len(steps) >= 2, f"模板 {keyword} 至少需要2步: {len(steps)}"
        for step in steps:
            assert "description" in step
            assert "capability" in step
            assert "agent" in step
    print("✅ 测试3 模板完整性: 通过")


def test_template_matching():
    """模板匹配"""
    dispatcher = TaskDispatcher()

    # 游戏匹配
    assert dispatcher._match_template("开发一个文字冒险游戏") == "游戏"
    assert dispatcher._match_template("create a game") == "game"

    # 文章匹配
    assert dispatcher._match_template("写一篇关于AI的文章") == "文章"
    assert dispatcher._match_template("write an article about AI") == "article"

    # 报告匹配
    assert dispatcher._match_template("生成系统分析报告") == "报告"

    # 数据匹配
    assert dispatcher._match_template("分析销售数据") == "数据"
    assert dispatcher._match_template("data analysis") == "data"

    # 默认匹配
    assert dispatcher._match_template("随便什么任务") == "通用"

    print("✅ 测试4 模板匹配: 通过")


def test_decompose_game():
    """游戏分解"""
    result = _dispatcher.decompose(
        task="开发一个文字冒险游戏",
        template="游戏",
    )
    assert "分解完成" in result
    assert "PL_" in result
    assert "researcher" in result.lower() or "research" in result.lower()
    assert "designer" in result.lower() or "design" in result.lower()
    assert "writer" in result.lower() or "writing" in result.lower()
    assert "reviewer" in result.lower() or "review" in result.lower()
    print("✅ 测试5 游戏分解: 通过")


def test_decompose_article():
    """文章分解"""
    result = _dispatcher.decompose(
        task="写一篇深度技术文章",
        template="article",
    )
    assert "分解完成" in result
    assert "子任务: 4" in result or "4 个" in result
    print("✅ 测试6 文章分解: 通过")


def test_decompose_custom():
    """自定义子任务分解"""
    custom = json.dumps([
        {"description": "自定义步骤1", "capability": "research", "agent": "researcher"},
        {"description": "自定义步骤2", "capability": "analysis", "agent": "analyst"},
    ])
    result = _dispatcher.decompose(
        task="自定义任务",
        custom_subtasks=custom,
    )
    assert "分解完成" in result
    assert "自定义步骤1" in result
    assert "自定义步骤2" in result
    print("✅ 测试7 自定义分解: 通过")


def test_decompose_auto_match():
    """自动模板匹配"""
    result = _dispatcher.decompose(task="分析这份数据并生成报告")
    assert "分解完成" in result
    print("✅ 测试8 自动匹配: 通过")


def test_decompose_empty():
    """空任务"""
    try:
        _dispatcher.decompose(task="")
        assert False
    except DispatchError:
        pass
    print("✅ 测试9 空任务拒绝: 通过")


def test_decompose_invalid_custom():
    """无效自定义子任务"""
    try:
        _dispatcher.decompose(
            task="test",
            custom_subtasks="not json",
        )
        assert False
    except DispatchError:
        pass
    print("✅ 测试10 无效 JSON 拒绝: 通过")


def test_dispatch_nonexistent_pipeline():
    """调度不存在的流水线"""
    try:
        _dispatcher.dispatch(pipeline_id="PL_nonexistent")
        assert False
    except DispatchError:
        pass
    print("✅ 测试11 不存在的流水线: 通过")


def test_status():
    """状态查看"""
    result = _dispatcher.status()
    # 之前创建的流水线应该可见
    assert isinstance(result, str)
    print("✅ 测试12 状态查看: 通过")


def test_list_pipelines():
    """列出流水线"""
    result = _dispatcher.list_pipelines()
    assert isinstance(result, str)
    print("✅ 测试13 列出流水线: 通过")


def test_templates_list():
    """模板列表"""
    result = _dispatcher.templates()
    assert "可用" in result or "模板" in result
    assert "游戏" in result or "game" in result
    assert "文章" in result or "article" in result
    print("✅ 测试14 模板列表: 通过")


def test_cancel_pipeline():
    """取消流水线"""
    # 先创建一个
    result = _dispatcher.decompose(task="待取消的任务", template="通用")
    pipeline_id = ""
    for line in result.split("\n"):
        if "流水线 [" in line:
            start = line.find("[") + 1
            end = line.find("]", start)
            pipeline_id = line[start:end]
            break

    assert pipeline_id

    result = _dispatcher.cancel(pipeline_id)
    assert "已取消" in result

    # 验证状态
    pipeline = _dispatcher._pipelines.get(pipeline_id)
    if pipeline:
        assert pipeline.status == PipelineStatus.FAILED.value

    print("✅ 测试15 取消流水线: 通过")


def test_collect():
    """收集结果"""
    result = _dispatcher.decompose(task="收集测试", template="通用")
    pipeline_id = ""
    for line in result.split("\n"):
        if "流水线 [" in line:
            start = line.find("[") + 1
            end = line.find("]", start)
            pipeline_id = line[start:end]
            break

    # 手动模拟完成任务
    pipeline = _dispatcher._pipelines.get(pipeline_id)
    if pipeline:
        for st in pipeline.subtasks:
            st.status = SubtaskStatus.DONE.value
            st.result = f"{st.description} - 完成"

    result = _dispatcher.collect(pipeline_id)
    assert "结果" in result or "收集" in result
    print("✅ 测试16 收集结果: 通过")


def test_tool_definition():
    """工具定义"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "task_dispatcher"
    actions = TOOL_DEFINITION["function"]["parameters"]["properties"]["action"]["enum"]
    assert "decompose" in actions
    assert "dispatch" in actions
    assert "dispatch_all" in actions
    assert "collect" in actions
    assert "status" in actions
    assert "list_pipelines" in actions
    assert "cancel" in actions
    assert "templates" in actions
    print("✅ 测试17 工具定义: 通过")


def test_execute_tool():
    """工具入口"""
    from tools.task_dispatcher import execute_task_dispatcher_tool

    # templates
    result = execute_task_dispatcher_tool({"action": "templates"})
    assert "模板" in result or "可用" in result

    # decompose
    result = execute_task_dispatcher_tool({
        "action": "decompose",
        "task": "入口测试",
        "template": "通用",
    })
    assert "分解完成" in result

    # status
    result = execute_task_dispatcher_tool({"action": "status"})
    assert len(result) > 0

    # list_pipelines
    result = execute_task_dispatcher_tool({"action": "list_pipelines"})
    assert len(result) > 0

    # 无效操作
    result = execute_task_dispatcher_tool({"action": "invalid"})
    assert "未知" in result

    # 空 dispatch（工具入口返回友好错误字符串，而非抛异常）
    result = execute_task_dispatcher_tool({"action": "dispatch"})
    assert "请指定" in result or "错误" in result

    print("✅ 测试18 工具入口: 通过")


def test_find_best_agent():
    """查找最佳 Agent"""
    dispatcher = TaskDispatcher()

    # 当没有 agent 注册时
    result = dispatcher._find_best_agent("research", "researcher")
    # 应该返回偏好类型作为回退
    assert result == "researcher"

    print("✅ 测试19 查找最佳 Agent: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Task Dispatcher 单元测试")
    print("=" * 50)
    test_enums()
    test_dataclasses()
    test_templates()
    test_template_matching()
    test_decompose_game()
    test_decompose_article()
    test_decompose_custom()
    test_decompose_auto_match()
    test_decompose_empty()
    test_decompose_invalid_custom()
    test_dispatch_nonexistent_pipeline()
    test_status()
    test_list_pipelines()
    test_templates_list()
    test_cancel_pipeline()
    test_collect()
    test_tool_definition()
    test_execute_tool()
    test_find_best_agent()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
