"""
decision_engine 单元测试
覆盖: advise, record_decision, history, stats, similar_problems, execute 入口及错误处理
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.decision_engine import (
    DecisionError,
    DecisionEngine,
    TOOL_DEFINITION,
    execute_decision_engine_tool,
)


# ── 辅助：每个测试前后重置引擎状态 ────────────────────────

def _fresh_engine() -> DecisionEngine:
    """创建干净引擎实例用于测试。"""
    engine = DecisionEngine()
    engine._decisions = []  # 清空决策记录
    return engine


# ── 测试：工具定义 ────────────────────────────────────────

def test_tool_definition():
    """工具定义完整性"""
    assert "function" in TOOL_DEFINITION
    func = TOOL_DEFINITION["function"]
    assert func["name"] == "decision_engine"
    props = func["parameters"]["properties"]
    assert "action" in props
    assert "problem" in props
    assert "decision" in props
    assert "outcome" in props
    # action 枚举覆盖全部操作
    actions = props["action"]["enum"]
    assert "advise" in actions
    assert "record_decision" in actions
    assert "history" in actions
    assert "stats" in actions
    assert "similar_problems" in actions


# ── 测试：advise ──────────────────────────────────────────

def test_advise_empty_problem():
    """空问题描述抛出异常"""
    engine = _fresh_engine()
    try:
        engine.advise("")
        assert False, "应抛出异常"
    except DecisionError as e:
        assert "不能为空" in str(e)


def test_advise_known_keyword():
    """已知关键词返回匹配建议"""
    engine = _fresh_engine()
    result = engine.advise("搜索功能怎么用？")
    assert "搜索" in result or "search" in result.lower() or "建议" in result


def test_advise_known_keyword_english():
    """英文关键词匹配"""
    engine = _fresh_engine()
    result = engine.advise("how to import module?")
    assert "import" in result.lower() or "导入" in result or "建议" in result


def test_advise_no_match():
    """无匹配返回通用建议"""
    engine = _fresh_engine()
    result = engine.advise("xyzabc123不存在的功能")
    # 应包含通用建议
    assert "self_check" in result or "建议" in result


def test_advise_with_context():
    """带上下文的建议查询"""
    engine = _fresh_engine()
    result = engine.advise("文件丢失了", context="需要备份")
    assert isinstance(result, str)
    assert len(result) > 0


def test_advise_max_results():
    """max_results 限制返回条数"""
    engine = _fresh_engine()
    result = engine.advise("计算 测试 check 监控 导入 搜索", max_results=2)
    # 应该只显示前2条
    lines = result.split("\n")
    suggestion_count = sum(1 for l in lines if "建议" in l and "匹配度" in l)
    assert suggestion_count <= 2, f"应最多2条建议，实际 {suggestion_count}"


# ── 测试：record_decision ─────────────────────────────────

def test_record_decision_empty():
    """空决策描述抛出异常"""
    engine = _fresh_engine()
    try:
        engine.record_decision("")
        assert False, "应抛出异常"
    except DecisionError as e:
        assert "不能为空" in str(e)


def test_record_decision():
    """正常记录决策"""
    engine = _fresh_engine()
    result = engine.record_decision("使用 self_check 诊断模块")
    assert "已记录" in result
    assert "D" in result  # ID 格式


def test_record_decision_with_outcome():
    """记录决策及结果"""
    engine = _fresh_engine()
    engine.record_decision("使用 self_check", outcome="成功修复")
    assert len(engine._decisions) == 1
    assert engine._decisions[0]["outcome"] == "成功修复"


# ── 测试：history ─────────────────────────────────────────

def test_history_empty():
    """无记录时返回提示"""
    engine = _fresh_engine()
    result = engine.history()
    assert "暂无" in result


def test_history_with_records():
    """有记录时展示"""
    engine = _fresh_engine()
    engine.record_decision("决策1")
    engine.record_decision("决策2")
    result = engine.history()
    assert "决策1" in result
    assert "决策2" in result


def test_history_max_results():
    """只返回最近的 N 条"""
    engine = _fresh_engine()
    for i in range(5):
        engine.record_decision(f"决策{i}")
    result = engine.history(max_results=2)
    # 应只显示最近2条
    assert "决策3" in result
    assert "决策4" in result


# ── 测试：stats ───────────────────────────────────────────

def test_stats_empty():
    """无记录统计"""
    engine = _fresh_engine()
    result = engine.stats()
    assert "暂无" in result


def test_stats_with_records():
    """有记录的统计"""
    engine = _fresh_engine()
    engine.record_decision("成功决策", outcome="成功完成")
    engine.record_decision("失败决策", outcome="失败 ❌")
    engine.record_decision("待评估决策")
    result = engine.stats()
    assert "3" in result  # 总数
    assert "成功" in result


# ── 测试：similar_problems ────────────────────────────────

def test_similar_problems_empty():
    """空问题抛出异常"""
    engine = _fresh_engine()
    try:
        engine.similar_problems("")
        assert False, "应抛出异常"
    except DecisionError as e:
        assert "不能为空" in str(e)


def test_similar_problems_no_match():
    """无相似历史"""
    engine = _fresh_engine()
    result = engine.similar_problems("完全不相关的问题xyz")
    assert "未找到" in result


def test_similar_problems_with_match():
    """有相似历史"""
    engine = _fresh_engine()
    engine.record_decision("处理导入错误的问题")
    result = engine.similar_problems("导入错误")
    assert "导入错误" in result or "导入" in result


# ── 测试：execute 入口函数 ────────────────────────────────

def test_execute_advise():
    """通过入口函数调用 advise"""
    result = execute_decision_engine_tool({
        "action": "advise",
        "problem": "如何搜索文件",
        "context": "代码库",
        "max_results": 3,
    })
    assert isinstance(result, str)
    assert len(result) > 0


def test_execute_record_decision():
    """通过入口函数记录决策"""
    result = execute_decision_engine_tool({
        "action": "record_decision",
        "decision": "使用入口函数记录",
        "outcome": "成功",
    })
    assert "已记录" in result


def test_execute_history():
    """通过入口函数查看历史"""
    result = execute_decision_engine_tool({
        "action": "history",
        "max_results": 5,
    })
    assert isinstance(result, str)


def test_execute_stats():
    """通过入口函数查看统计"""
    result = execute_decision_engine_tool({"action": "stats"})
    assert isinstance(result, str)


def test_execute_similar_problems():
    """通过入口函数查找相似"""
    result = execute_decision_engine_tool({
        "action": "similar_problems",
        "problem": "导入模块",
    })
    assert isinstance(result, str)


def test_execute_unknown_action():
    """未知操作"""
    result = execute_decision_engine_tool({"action": "nonexistent"})
    assert "未知" in result


# ── 测试：异常 ────────────────────────────────────────────

def test_decision_error():
    """自定义异常"""
    try:
        raise DecisionError("测试错误")
    except DecisionError as e:
        assert "测试错误" in str(e)


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Decision Engine 单元测试")
    print("=" * 50)

    tests = [
        ("工具定义", test_tool_definition),
        ("advise 空问题", test_advise_empty_problem),
        ("advise 已知关键词", test_advise_known_keyword),
        ("advise 英文关键词", test_advise_known_keyword_english),
        ("advise 无匹配", test_advise_no_match),
        ("advise 带上下文", test_advise_with_context),
        ("advise max_results", test_advise_max_results),
        ("record 空决策", test_record_decision_empty),
        ("record 正常记录", test_record_decision),
        ("record 带结果", test_record_decision_with_outcome),
        ("history 空", test_history_empty),
        ("history 有记录", test_history_with_records),
        ("history max_results", test_history_max_results),
        ("stats 空", test_stats_empty),
        ("stats 有记录", test_stats_with_records),
        ("similar 空问题", test_similar_problems_empty),
        ("similar 无匹配", test_similar_problems_no_match),
        ("similar 有匹配", test_similar_problems_with_match),
        ("execute advise", test_execute_advise),
        ("execute record", test_execute_record_decision),
        ("execute history", test_execute_history),
        ("execute stats", test_execute_stats),
        ("execute similar", test_execute_similar_problems),
        ("execute 未知操作", test_execute_unknown_action),
        ("自定义异常", test_decision_error),
    ]

    passed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")

    print()
    print("=" * 50)
    print(f"🎉 Decision Engine: {passed}/{len(tests)} 通过")
    print("=" * 50)
