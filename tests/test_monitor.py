"""
monitor 单元测试
覆盖: record, summary, report, top_tools, slow_tools, errors, reset 及 execute 入口
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.monitor import (
    MonitorError,
    Monitor,
    TOOL_DEFINITION,
    execute_monitor_tool,
)


# ── 辅助：每个测试前后重置监控状态 ────────────────────────

def _fresh_monitor() -> Monitor:
    """创建干净监控实例。

    ★必须使用临时路径。原实现用 Monitor()（默认=生产文件 memory/monitor_data.json），
    test_reset 调用 reset() 时会把生产数据写空——2026-10-31 实测因此丢失了
    1,832 次调用、约 1.5 个月的运行统计。
    """
    import tempfile

    path = Path(tempfile.mkdtemp(prefix="mon_test_")) / "monitor.json"
    monitor = Monitor(path=path)
    monitor._data = monitor._fresh_data()
    return monitor


# ── 测试：工具定义 ────────────────────────────────────────

def test_tool_definition():
    """工具定义完整性"""
    assert "function" in TOOL_DEFINITION
    func = TOOL_DEFINITION["function"]
    assert func["name"] == "monitor"
    props = func["parameters"]["properties"]
    assert "action" in props
    assert "tool_name" in props
    assert "duration" in props
    assert "success" in props
    assert "limit" in props
    actions = props["action"]["enum"]
    assert "record" in actions
    assert "report" in actions
    assert "summary" in actions
    assert "top_tools" in actions
    assert "slow_tools" in actions
    assert "errors" in actions
    assert "reset" in actions


# ── 测试：record ──────────────────────────────────────────

def test_record_empty_name():
    """空工具名抛出异常"""
    m = _fresh_monitor()
    try:
        m.record("")
        assert False, "应抛出异常"
    except MonitorError as e:
        assert "不能为空" in str(e)


def test_record_success():
    """记录成功调用"""
    m = _fresh_monitor()
    result = m.record("read_file", duration=0.05, success=True)
    assert "已记录" in result
    assert m._data["total_calls"] == 1
    assert m._data["tools"]["read_file"]["calls"] == 1


def test_record_failure():
    """记录失败调用"""
    m = _fresh_monitor()
    m.record("web_search", duration=2.0, success=False)
    assert m._data["total_calls"] == 1
    assert m._data["total_errors"] == 1
    assert m._data["tools"]["web_search"]["errors"] == 1


def test_record_multiple_tools():
    """记录多个不同工具"""
    m = _fresh_monitor()
    m.record("read_file", duration=0.01)
    m.record("web_search", duration=1.5)
    m.record("read_file", duration=0.02)
    assert m._data["total_calls"] == 3
    assert m._data["tools"]["read_file"]["calls"] == 2
    assert m._data["tools"]["web_search"]["calls"] == 1


def test_record_duration_stats():
    """验证耗时统计"""
    m = _fresh_monitor()
    m.record("tool_a", duration=0.1)
    m.record("tool_a", duration=0.5)
    t = m._data["tools"]["tool_a"]
    assert t["total_duration"] == 0.6
    assert t["max_duration"] == 0.5
    assert t["min_duration"] == 0.1


def test_record_last_called():
    """验证最后调用时间记录"""
    m = _fresh_monitor()
    m.record("test_tool", duration=0.01)
    assert m._data["tools"]["test_tool"]["last_called"] != ""


# ── 测试：summary ─────────────────────────────────────────

def test_summary_empty():
    """空状态摘要"""
    m = _fresh_monitor()
    result = m.summary()
    assert "运行时间" in result
    assert "总调用次数" in result
    assert "0" in result  # 0 调用


def test_summary_with_data():
    """有数据的摘要"""
    m = _fresh_monitor()
    m.record("tool_a", duration=0.1)
    m.record("tool_b", duration=0.2)
    result = m.summary()
    assert "2" in result  # 总调用
    assert "活跃工具数" in result


# ── 测试：report ──────────────────────────────────────────

def test_report_empty():
    """空报告"""
    m = _fresh_monitor()
    result = m.report()
    assert "性能监控报告" in result
    assert "总调用" in result


def test_report_with_data():
    """有数据的报告"""
    m = _fresh_monitor()
    m.record("read_file", duration=0.03)
    m.record("web_search", duration=1.2)
    result = m.report()
    assert "read_file" in result
    assert "web_search" in result


# ── 测试：top_tools ───────────────────────────────────────

def test_top_tools_empty():
    """无数据排行"""
    m = _fresh_monitor()
    result = m.top_tools()
    assert "暂无" in result


def test_top_tools_with_data():
    """有数据排行"""
    m = _fresh_monitor()
    m.record("tool_a", duration=0.01)
    m.record("tool_a", duration=0.01)
    m.record("tool_b", duration=0.01)
    result = m.top_tools(5)
    assert "tool_a" in result
    assert "2" in result  # tool_a 调用2次


def test_top_tools_limit():
    """限制返回数量"""
    m = _fresh_monitor()
    for i in range(5):
        m.record(f"tool_{i}", duration=0.01)
    result = m.top_tools(limit=2)
    # 应该有排名1和2
    assert "1" in result
    assert "2" in result


# ── 测试：slow_tools ──────────────────────────────────────

def test_slow_tools_empty():
    """无数据慢工具"""
    m = _fresh_monitor()
    result = m.slow_tools()
    assert "暂无" in result


def test_slow_tools_with_data():
    """有数据慢工具"""
    m = _fresh_monitor()
    m.record("fast_tool", duration=0.01)
    m.record("slow_tool", duration=5.0)
    result = m.slow_tools(5)
    assert "slow_tool" in result


# ── 测试：errors ──────────────────────────────────────────

def test_errors_no_errors():
    """无错误"""
    m = _fresh_monitor()
    result = m.errors()
    assert "没有" in result or "🎉" in result


def test_errors_with_errors():
    """有错误"""
    m = _fresh_monitor()
    m.record("bad_tool", duration=0.1, success=False)
    result = m.errors()
    assert "bad_tool" in result
    assert "1" in result


# ── 测试：reset ───────────────────────────────────────────

def test_reset():
    """重置监控数据"""
    m = _fresh_monitor()
    m.record("some_tool", duration=0.1)
    assert m._data["total_calls"] == 1
    result = m.reset()
    assert "已重置" in result
    assert m._data["total_calls"] == 0


# ── 测试：execute 入口 ────────────────────────────────────

def test_execute_record():
    """入口函数 record"""
    result = execute_monitor_tool({
        "action": "record",
        "tool_name": "test_tool",
        "duration": 0.05,
        "success": True,
    })
    assert "已记录" in result


def test_execute_summary():
    """入口函数 summary"""
    result = execute_monitor_tool({"action": "summary"})
    assert "运行时间" in result


def test_execute_report():
    """入口函数 report"""
    result = execute_monitor_tool({"action": "report"})
    assert "报告" in result


def test_execute_top_tools():
    """入口函数 top_tools"""
    result = execute_monitor_tool({"action": "top_tools", "limit": 5})
    assert isinstance(result, str)


def test_execute_slow_tools():
    """入口函数 slow_tools"""
    result = execute_monitor_tool({"action": "slow_tools", "limit": 5})
    assert isinstance(result, str)


def test_execute_errors():
    """入口函数 errors"""
    result = execute_monitor_tool({"action": "errors"})
    assert isinstance(result, str)


def test_execute_reset():
    """入口函数 reset"""
    result = execute_monitor_tool({"action": "reset"})
    assert "已重置" in result


def test_execute_unknown_action():
    """未知操作"""
    result = execute_monitor_tool({"action": "nonexistent"})
    assert "未知" in result


# ── 测试：异常 ────────────────────────────────────────────

def test_monitor_error():
    """自定义异常"""
    try:
        raise MonitorError("测试监控错误")
    except MonitorError as e:
        assert "测试监控错误" in str(e)


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Monitor 单元测试")
    print("=" * 50)

    tests = [
        ("工具定义", test_tool_definition),
        ("record 空名称", test_record_empty_name),
        ("record 成功", test_record_success),
        ("record 失败", test_record_failure),
        ("record 多工具", test_record_multiple_tools),
        ("record 耗时统计", test_record_duration_stats),
        ("record 最后调用", test_record_last_called),
        ("summary 空", test_summary_empty),
        ("summary 有数据", test_summary_with_data),
        ("report 空", test_report_empty),
        ("report 有数据", test_report_with_data),
        ("top_tools 空", test_top_tools_empty),
        ("top_tools 有数据", test_top_tools_with_data),
        ("top_tools limit", test_top_tools_limit),
        ("slow_tools 空", test_slow_tools_empty),
        ("slow_tools 有数据", test_slow_tools_with_data),
        ("errors 无错误", test_errors_no_errors),
        ("errors 有错误", test_errors_with_errors),
        ("reset", test_reset),
        ("execute record", test_execute_record),
        ("execute summary", test_execute_summary),
        ("execute report", test_execute_report),
        ("execute top_tools", test_execute_top_tools),
        ("execute slow_tools", test_execute_slow_tools),
        ("execute errors", test_execute_errors),
        ("execute reset", test_execute_reset),
        ("execute 未知操作", test_execute_unknown_action),
        ("自定义异常", test_monitor_error),
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
    print(f"🎉 Monitor: {passed}/{len(tests)} 通过")
    print("=" * 50)
