"""
Experience Learner 单元测试
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.experience_learner import (
    ExperienceLearner, ExperienceLearnerError,
    TOOL_DEFINITION, _learner,
)

import pytest


@pytest.fixture(autouse=True)
def _isolate_knowledge_writes(monkeypatch, tmp_path):
    """★T2795-5.1：隔离知识库写入。

    experience_learner 在记录经验时会顺带写入 knowledge_store.json。
    原实现直接写生产知识库，每跑一次测试就留下"[经验] xxx 成功"类脏数据。
    """
    import tools.experience_learner as _el

    monkeypatch.setattr(_el, "KNOWLEDGE_DIR", tmp_path / "experience_kb")


def test_keyword_extraction():
    """关键词提取"""
    learner = ExperienceLearner()

    # 基本提取
    kw = learner._extract_keywords("使用 web_search 搜索 AI 智能体")
    assert len(kw) > 0, "应有至少一个关键词"
    assert "web_search" in kw or "ai" in kw or "智能体" in kw

    # 空文本
    kw = learner._extract_keywords("")
    assert kw == []

    # 停用词过滤
    kw = learner._extract_keywords("的 了 在 是 我 the a an")
    assert len(kw) == 0, "停用词应全部被过滤"

    print("✅ 测试1 关键词提取: 通过")


def test_record_success():
    """记录成功经验"""
    learner = ExperienceLearner()

    result = learner.record_success(
        tool_name="web_search",
        task="搜索AI最新进展",
        result="找到了5篇相关文章",
        lesson="使用英文关键词可以获得更准确的搜索结果",
    )
    assert "已记录" in result
    assert "EXP-" in result
    assert "web_search" in result

    # 验证内部状态
    assert len(learner._experiences) >= 1
    entry = learner._experiences[-1]
    assert entry["type"] == "success"
    assert entry["tool"] == "web_search"

    print("✅ 测试2 记录成功经验: 通过")


def test_record_failure():
    """记录失败教训"""
    learner = ExperienceLearner()

    result = learner.record_failure(
        tool_name="read_file",
        task="读取配置文件",
        result="FileNotFoundError: 文件不存在",
        lesson="读取前应先检查文件是否存在",
    )
    assert "已记录" in result or "教训" in result
    assert "read_file" in result

    entry = learner._experiences[-1]
    assert entry["type"] == "failure"
    assert entry["tool"] == "read_file"

    print("✅ 测试3 记录失败教训: 通过")


def test_record_short_lesson():
    """过短的教训不存入知识库"""
    learner = ExperienceLearner()

    result = learner.record_success(
        tool_name="calculate",
        task="简单计算",
        result="42",
        lesson="ok",  # 太短
    )
    assert "已记录" in result
    # 太短不应该存入知识库
    entry = learner._experiences[-1]
    assert entry.get("stored_to_knowledge") is not True

    print("✅ 测试4 短教训不存知识库: 通过")


def test_review():
    """经验回顾"""
    learner = ExperienceLearner()

    # 先加几条记录
    for i in range(3):
        learner.record_success(
            tool_name=f"tool_{i}",
            task=f"任务{i}",
            lesson=f"经验{i}: 这是一个足够长的经验教训总结文字",
        )
    learner.record_failure(
        tool_name="bad_tool",
        task="失败任务",
        lesson="教训: 这是一个足够长的教训总结，避免再次犯错",
    )

    result = learner.review(max_results=10)
    assert "经验回顾" in result
    assert "总经验" in result
    assert "常用工具" in result

    # 空记录时
    learner2 = ExperienceLearner()
    learner2._experiences = []
    result = learner2.review()
    assert "暂无" in result or "无经验" in result or "暂无经验"

    print("✅ 测试5 经验回顾: 通过")


def test_recommend():
    """经验推荐"""
    learner = ExperienceLearner()

    # 加一些特定关键词的经验
    learner.record_success(
        tool_name="web_search",
        task="搜索Python性能优化",
        lesson="使用cProfile进行性能分析是一个好方法",
    )
    learner.record_success(
        tool_name="knowledge",
        task="查询Python最佳实践",
        lesson="PEP 8是Python代码风格指南",
    )

    # 相关推荐
    result = learner.recommend(task="Python性能问题", max_results=3)
    assert "推荐" in result or "相关" in result

    # 不相关推荐
    result = learner.recommend(task="Rust编程")
    # 应返回不相关或推荐其他内容

    # 空任务推荐
    result = learner.recommend(task="", max_results=3)
    assert "最近" in result or "暂无" in result

    print("✅ 测试6 经验推荐: 通过")


def test_recent():
    """最近经验"""
    learner = ExperienceLearner()

    result = learner.recent(max_results=5)
    assert "最近" in result or "暂无" in result

    # 空经验
    learner2 = ExperienceLearner()
    learner2._experiences = []
    result = learner2.recent()
    assert "暂无" in result

    print("✅ 测试7 最近经验: 通过")


def test_stats():
    """学习统计"""
    learner = ExperienceLearner()

    result = learner.stats()
    assert "学习统计" in result
    assert "总经验" in result

    # 空统计
    learner2 = ExperienceLearner()
    learner2._experiences = []
    result = learner2.stats()
    assert "暂无" in result or "暂无学习数据"

    print("✅ 测试8 学习统计: 通过")


def test_reset():
    """重置"""
    learner = ExperienceLearner()
    learner.record_success(tool_name="test", lesson="test lesson for reset")
    assert len(learner._experiences) > 0

    result = learner.reset()
    assert "已重置" in result
    assert len(learner._experiences) == 0

    print("✅ 测试9 重置: 通过")


def test_tool_definition():
    """工具定义"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "experience_learner"
    actions = TOOL_DEFINITION["function"]["parameters"]["properties"]["action"]["enum"]
    assert "record_success" in actions
    assert "record_failure" in actions
    assert "review" in actions
    assert "recommend" in actions
    assert "stats" in actions
    print("✅ 测试10 工具定义: 通过")


def test_execute_tool():
    """工具入口"""
    from tools.experience_learner import execute_experience_learner_tool

    # record_success
    result = execute_experience_learner_tool({
        "action": "record_success",
        "tool_name": "test_tool",
        "lesson": "这是一个足够长的测试经验",
    })
    assert "已记录" in result

    # record_failure
    result = execute_experience_learner_tool({
        "action": "record_failure",
        "tool_name": "bad_tool",
        "lesson": "这是一个足够长的测试教训",
    })
    assert "已记录" in result or "教训" in result

    # review
    result = execute_experience_learner_tool({"action": "review"})
    assert "回顾" in result or "暂无" in result

    # recommend
    result = execute_experience_learner_tool({
        "action": "recommend",
        "task": "测试",
    })
    assert len(result) > 0

    # recent
    result = execute_experience_learner_tool({"action": "recent"})
    assert "最近" in result or "暂无" in result

    # stats
    result = execute_experience_learner_tool({"action": "stats"})
    assert "统计" in result or "暂无" in result

    # 无效操作
    result = execute_experience_learner_tool({"action": "invalid"})
    assert "未知" in result

    # reset
    result = execute_experience_learner_tool({"action": "reset"})
    assert "已重置" in result

    print("✅ 测试11 工具入口: 通过")


def test_learner_state_persistence():
    """状态持久化（内存中）"""
    learner = ExperienceLearner()
    initial_count = len(learner._experiences)

    # 添加多条
    for i in range(5):
        learner.record_success(
            tool_name=f"persist_tool_{i}",
            lesson=f"持久化测试经验{i} - 足够长的文字来通过长度检查",
        )

    assert len(learner._experiences) >= initial_count + 5

    # 统计正确
    result = learner.stats()
    assert "总经验" in result

    print("✅ 测试12 状态持久化: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Experience Learner 单元测试")
    print("=" * 50)
    test_keyword_extraction()
    test_record_success()
    test_record_failure()
    test_record_short_lesson()
    test_review()
    test_recommend()
    test_recent()
    test_stats()
    test_reset()
    test_tool_definition()
    test_execute_tool()
    test_learner_state_persistence()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
