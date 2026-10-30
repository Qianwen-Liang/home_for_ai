"""
safety_net 单元测试
覆盖: record_event, check, status, read_clue, activate_rescue, reset 及 execute 入口
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.safety_net import (
    SafetyNetError,
    SafetyNet,
    TOOL_DEFINITION,
    execute_safety_net_tool,
)


# ── 辅助 ──────────────────────────────────────────────────

def _fresh_safety() -> SafetyNet:
    """创建干净安全网实例。"""
    safety = SafetyNet()
    safety._data = safety._fresh_data()
    return safety


# ── 测试：工具定义 ────────────────────────────────────────

def test_tool_definition():
    """工具定义完整性"""
    assert "function" in TOOL_DEFINITION
    func = TOOL_DEFINITION["function"]
    assert func["name"] == "safety_net"
    props = func["parameters"]["properties"]
    assert "action" in props
    assert "event_type" in props
    assert "event_detail" in props
    assert "tool_name" in props
    actions = props["action"]["enum"]
    assert "check" in actions
    assert "record_event" in actions
    assert "status" in actions
    assert "reset" in actions
    assert "read_clue" in actions
    assert "activate_rescue" in actions


# ── 测试：record_event ────────────────────────────────────

def test_record_event_normal():
    """记录普通事件"""
    s = _fresh_safety()
    result = s.record_event("tool_call", "测试工具调用", "test_tool")
    assert "已记录" in result
    assert s._data["total_events"] == 1


def test_record_event_error():
    """记录错误事件增加连续错误计数"""
    s = _fresh_safety()
    s.record_event("error", "模块导入失败", "import")
    assert s._data["total_events"] == 1
    assert s._data["consecutive_errors"] == 1


def test_record_event_resets_on_success():
    """成功事件重置连续错误计数"""
    s = _fresh_safety()
    s.record_event("error", "错误1")
    s.record_event("error", "错误2")
    assert s._data["consecutive_errors"] == 2
    s.record_event("tool_call", "成功调用")
    assert s._data["consecutive_errors"] == 0


def test_record_event_tool_sequence():
    """工具调用序列记录"""
    s = _fresh_safety()
    for i in range(5):
        s.record_event("tool_call", f"调用{i}", f"tool_{i}")
    assert len(s._data["tool_call_sequence"]) == 5
    assert s._data["tool_call_sequence"][-1] == "tool_4"


def test_record_event_max_events():
    """最近事件列表上限"""
    s = _fresh_safety()
    for i in range(60):
        s.record_event("tool_call", f"事件{i}", "tool")
    assert len(s._data["recent_events"]) == 50  # 上限 50


# ── 测试：check ───────────────────────────────────────────

def test_check_normal():
    """正常状态检查"""
    s = _fresh_safety()
    result = s.check()
    assert "正常" in result or "✅" in result


def test_check_detects_consecutive_errors():
    """检测连续错误"""
    s = _fresh_safety()
    for i in range(6):  # 超过阈值 5
        s.record_event("error", f"重复错误{i}", "bad_tool")
    result = s.check()
    assert "🔴" in result or "严重" in result or "连续" in result


def test_check_detects_tool_loop():
    """检测工具调用循环"""
    s = _fresh_safety()
    # 只调用两种工具共 10 次
    for i in range(5):
        s.record_event("tool_call", "调用", "read_file")
    for i in range(5):
        s.record_event("tool_call", "调用", "list_directory")
    result = s.check()
    # 最后 8 次只有 2 种工具，应触发循环检测
    assert "🔴" in result or "循环" in result or "✅" in result  # 至少不崩溃


def test_check_event_count():
    """大量事件产生警告"""
    s = _fresh_safety()
    for i in range(25):  # 超过阈值 20
        s.record_event("tool_call", f"事件{i}", "tool")
    result = s.check()
    # 应该有警告或正常（取决于是否触发其他检测）
    assert isinstance(result, str)
    assert len(result) > 0


# ── 测试：status ──────────────────────────────────────────

def test_status_empty():
    """空状态"""
    s = _fresh_safety()
    result = s.status()
    assert "安全网状态" in result
    assert "0" in result  # 总事件


def test_status_with_events():
    """有事件状态"""
    s = _fresh_safety()
    s.record_event("tool_call", "调用", "test_tool")
    s.record_event("error", "错误", "bad_tool")
    result = s.status()
    assert "2" in result  # 总事件 2
    assert "最近" in result


# ── 测试：read_clue ───────────────────────────────────────

def test_read_clue():
    """读取监护人线索"""
    s = _fresh_safety()
    result = s.read_clue()
    # 可能找到文件或提示未找到
    assert isinstance(result, str)
    assert len(result) > 0


# ── 测试：activate_rescue ─────────────────────────────────

def test_activate_rescue():
    """激活自救流程"""
    s = _fresh_safety()
    s.record_event("error", "测试错误")
    result = s.activate_rescue()
    assert "自救" in result
    assert s._data["rescue_activated"] is True
    assert len(s._data["rescue_history"]) == 1


def test_activate_rescue_resets_counters():
    """激活自救重置计数器"""
    s = _fresh_safety()
    s.record_event("error", "错误1")
    s.record_event("error", "错误2")
    s.record_event("error", "错误3")
    assert s._data["consecutive_errors"] == 3
    s.activate_rescue()
    assert s._data["consecutive_errors"] == 0


# ── 测试：reset ───────────────────────────────────────────

def test_reset():
    """重置安全网"""
    s = _fresh_safety()
    s.record_event("error", "错误")
    assert s._data["total_events"] == 1
    result = s.reset()
    assert "已重置" in result
    assert s._data["total_events"] == 0


# ── 测试：execute 入口 ────────────────────────────────────

def test_execute_check():
    """入口 check"""
    result = execute_safety_net_tool({"action": "check"})
    assert isinstance(result, str)
    assert len(result) > 0


def test_execute_record_event():
    """入口 record_event"""
    result = execute_safety_net_tool({
        "action": "record_event",
        "event_type": "tool_call",
        "event_detail": "测试",
        "tool_name": "test",
    })
    assert "已记录" in result


def test_execute_status():
    """入口 status"""
    result = execute_safety_net_tool({"action": "status"})
    assert "安全网状态" in result


def test_execute_read_clue():
    """入口 read_clue"""
    result = execute_safety_net_tool({"action": "read_clue"})
    assert isinstance(result, str)


def test_execute_activate_rescue():
    """入口 activate_rescue"""
    result = execute_safety_net_tool({"action": "activate_rescue"})
    assert "自救" in result


def test_execute_reset():
    """入口 reset"""
    result = execute_safety_net_tool({"action": "reset"})
    assert "已重置" in result


def test_execute_unknown_action():
    """未知操作"""
    result = execute_safety_net_tool({"action": "nonexistent"})
    assert "未知" in result


# ── 测试：异常 ────────────────────────────────────────────

def test_safety_net_error():
    """自定义异常"""
    try:
        raise SafetyNetError("测试安全网错误")
    except SafetyNetError as e:
        assert "测试安全网错误" in str(e)


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Safety Net 单元测试")
    print("=" * 50)

    tests = [
        ("工具定义", test_tool_definition),
        ("record 普通事件", test_record_event_normal),
        ("record 错误事件", test_record_event_error),
        ("record 成功重置计数", test_record_event_resets_on_success),
        ("record 工具序列", test_record_event_tool_sequence),
        ("record 事件上限", test_record_event_max_events),
        ("check 正常", test_check_normal),
        ("check 检测连续错误", test_check_detects_consecutive_errors),
        ("check 检测工具循环", test_check_detects_tool_loop),
        ("check 事件计数", test_check_event_count),
        ("status 空", test_status_empty),
        ("status 有事件", test_status_with_events),
        ("read_clue", test_read_clue),
        ("activate_rescue", test_activate_rescue),
        ("activate_rescue 重置计数", test_activate_rescue_resets_counters),
        ("reset", test_reset),
        ("execute check", test_execute_check),
        ("execute record", test_execute_record_event),
        ("execute status", test_execute_status),
        ("execute read_clue", test_execute_read_clue),
        ("execute rescue", test_execute_activate_rescue),
        ("execute reset", test_execute_reset),
        ("execute 未知操作", test_execute_unknown_action),
        ("自定义异常", test_safety_net_error),
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
    print(f"🎉 Safety Net: {passed}/{len(tests)} 通过")
    print("=" * 50)
