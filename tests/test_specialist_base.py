"""
Specialist Base 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.specialist_base import (
    SpecialistRegistry, SpecialistError, SpecialistType,
    TaskInput, TaskResult,
    ResearcherAgent, WriterAgent, AnalystAgent,
    ReviewerAgent, MonitorAgent, DesignerAgent,
)


def test_create_all_types():
    """测试创建所有类型的 Specialist"""
    types = [
        ("researcher", ResearcherAgent),
        ("writer", WriterAgent),
        ("analyst", AnalystAgent),
        ("reviewer", ReviewerAgent),
        ("monitor", MonitorAgent),
        ("designer", DesignerAgent),
    ]

    for type_name, expected_class in types:
        agent = SpecialistRegistry.create(type_name)
        assert isinstance(agent, expected_class), f"{type_name} 类型不匹配"
        assert agent.specialist_type == type_name, f"specialist_type 应为 {type_name}"
        print(f"✅ 测试1 创建 {type_name}: 通过")


def test_process_task():
    """测试任务处理"""
    researcher = ResearcherAgent()

    # 正常任务
    task = TaskInput(
        task_id="T001",
        description="搜索AI最新进展",
        params={"query": "AI 2026", "sources": ["web", "knowledge"]},
    )
    result = researcher.process_task(task)
    assert result.status == "done", f"状态应为 done: {result.status}"
    assert result.task_id == "T001", f"task_id 应一致"
    assert result.duration >= 0, f"耗时应非负"
    print("✅ 测试2 任务处理: 通过")

    # 检查输出
    output = result.output
    assert "query" in output, f"输出中应有 query"
    print("✅ 测试3 输出内容: 通过")


def test_task_history():
    """测试任务历史记录"""
    writer = WriterAgent()

    # 处理多个任务
    for i in range(3):
        task = TaskInput(
            task_id=f"T00{i+1}",
            description=f"写作任务{i+1}",
            params={"topic": f"主题{i+1}"},
        )
        writer.process_task(task)

    # 检查报告
    report = writer.report_result()
    assert "执行报告" in report, f"报告格式不对: {report[:50]}"
    print("✅ 测试4 执行报告: 通过")

    # 检查状态摘要
    summary = writer.get_status_summary()
    assert str(writer.name) in summary, f"摘要中应有名称"
    assert "3次" in summary or "3/3" in summary, f"摘要中应有任务数: {summary}"
    print("✅ 测试5 状态摘要: 通过")


def test_all_specialists():
    """测试所有 Specialist 都能正确处理任务"""
    types = ["researcher", "writer", "analyst", "reviewer", "monitor", "designer"]

    for type_name in types:
        agent = SpecialistRegistry.create(type_name)
        task = TaskInput(
            task_id=f"T_{type_name}",
            description=f"测试{type_name}",
            params={"query": type_name, "topic": type_name},
        )
        result = agent.process_task(task)
        assert result.status == "done", f"{type_name} 处理失败: {result.status}"
        assert result.summary, f"{type_name} 应有摘要"
        assert result.duration >= 0, f"{type_name} 应有耗时"
        print(f"✅ 测试6-{type_name}: 通过")


def test_invalid_type():
    """测试无效类型"""
    try:
        SpecialistRegistry.create("nonexistent")
        assert False, "应拒绝无效类型"
    except SpecialistError:
        pass
    print("✅ 测试7 拒绝无效类型: 通过")


def test_empty_task():
    """测试空任务"""
    researcher = ResearcherAgent()
    task = TaskInput(task_id="T999", description="", params={})
    result = researcher.process_task(task)
    # 默认实现不验证空描述，但应返回结果
    assert result.status in ["done", "failed"], f"应返回有效状态"
    print("✅ 测试8 空任务处理: 通过")


def test_specialist_list():
    """测试类型列表"""
    result = SpecialistRegistry.list_types()
    assert "researcher" in result, f"列表中应有 researcher"
    assert "writer" in result, f"列表中应有 writer"
    assert "analyst" in result, f"列表中应有 analyst"
    print("✅ 测试9 类型列表: 通过")


def test_get_help():
    """测试帮助信息"""
    help_text = SpecialistRegistry.get_help()
    assert "使用指南" in help_text, f"帮助信息格式不对"
    assert "researcher" in help_text.lower(), f"帮助中应有使用示例"
    print("✅ 测试10 帮助信息: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Specialist Base 单元测试")
    print("=" * 50)
    test_create_all_types()
    print()
    test_process_task()
    print()
    test_task_history()
    print()
    test_all_specialists()
    print()
    test_invalid_type()
    print()
    test_empty_task()
    print()
    test_specialist_list()
    print()
    test_get_help()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
