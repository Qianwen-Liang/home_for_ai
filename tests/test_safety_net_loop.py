"""safety_net 检测闭环测试（T2833）。

修复的真实缺陷：
  agent1 调用了 record_event，但 check() **从未被任何代码调用**。
  连续错误 / 重复错误 / 工具循环 三套检测规则全部存在，却从不执行——
  安全网只记录不判断，等于没有安全网。

新增 record_and_check()：记录后立即判定，触发严重阈值时返回告警，
由 agent1 附加到工具结果里，让模型能看见（对齐 MCP SEP-1303）。

注意：本测试全部使用临时文件，绝不触碰生产 memory/safety_data.json
（该文件已累积数百条历史事件，会干扰阈值判定）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.safety_net as SN  # noqa: E402


@pytest.fixture()
def net(monkeypatch, tmp_path):
    """隔离到临时文件：生产 safety_data.json 有累积事件，会污染阈值判定。"""
    monkeypatch.setattr(SN, "SAFETY_FILE", tmp_path / "safety.json")
    return SN.SafetyNet()


# ── 1. 正常情况不打扰 ───────────────────────────────────

def test_no_alert_below_threshold(net) -> None:
    """未达阈值时不得返回告警（避免刷屏）。"""
    assert net.record_and_check("error", "single-boom", "run_command") == ""


def test_no_alert_for_tool_call_events(net) -> None:
    assert net.record_and_check("tool_call", "ok", "read_file") == ""


# ── 2. 三类检测确实会触发 ───────────────────────────────

def test_repeated_same_error_triggers(net) -> None:
    """同一错误在窗口内达到阈值必须告警。"""
    alerts = [
        net.record_and_check("error", "same-boom", "run_command")
        for _ in range(SN.MAX_SAME_ERROR_IN_WINDOW)
    ]
    assert alerts[-1] != "", f"重复错误未触发告警: {alerts}"
    assert "重复错误" in alerts[-1]


def test_consecutive_errors_trigger(net) -> None:
    """连续错误达到阈值必须告警。"""
    alerts = [
        net.record_and_check("error", f"boom-{i}", "run_command")
        for i in range(SN.MAX_CONSECUTIVE_ERRORS)
    ]
    assert alerts[-1] != "", f"连续错误未触发告警: {alerts}"
    assert "连续" in alerts[-1]


def test_tool_loop_triggers(net) -> None:
    """最近若干次调用只用极少数工具，应判为循环。"""
    alert = ""
    for i in range(SN.MAX_REPEATED_TOOL_CALLS):
        alert = net.record_and_check("tool_call", f"step-{i}", "run_command")
    assert alert != "", "工具循环未触发告警"
    assert "循环" in alert


# ── 3. 告警内容可用性 ───────────────────────────────────

def test_alert_is_short_summary_not_full_report(net) -> None:
    """告警应只含问题摘要行，不能把整份报告塞进工具结果。"""
    for _ in range(SN.MAX_SAME_ERROR_IN_WINDOW):
        alert = net.record_and_check("error", "same", "run_command")
    assert alert
    assert "🚨" in alert
    assert "安全网状态检查" not in alert, "告警混入了完整报告标题"

    # 每一行都是问题摘要
    for line in alert.splitlines():
        assert line.strip().startswith(("🔴", "🟡", "🚨")), f"非摘要行: {line}"


def test_alert_mentions_threshold_values(net) -> None:
    for _ in range(SN.MAX_CONSECUTIVE_ERRORS):
        alert = net.record_and_check("error", "e", "t")
    assert str(SN.MAX_CONSECUTIVE_ERRORS) in alert


# ── 4. 记录本身仍然生效 ─────────────────────────────────

def test_record_still_happens(net) -> None:
    """record_and_check 必须保留原 record_event 的全部副作用。"""
    before = net._data["total_events"]
    net.record_and_check("error", "x", "run_command")
    assert net._data["total_events"] == before + 1
    assert net._data["tool_call_sequence"][-1] == "run_command"
    assert net._data["last_event_type"] == "error"


def test_check_failure_does_not_break_recording(monkeypatch, net) -> None:
    """检测抛异常时，记录仍须成功且不向上传播。"""
    def _boom():
        raise RuntimeError("check exploded")

    monkeypatch.setattr(SN.SafetyNet, "check", lambda self: _boom())
    before = net._data["total_events"]
    assert net.record_and_check("error", "y", "t") == ""
    assert net._data["total_events"] == before + 1


# ── 5. 闭环：agent1 会调用它 ────────────────────────────

def test_agent1_uses_record_and_check() -> None:
    """回归：agent1 必须调用 record_and_check，而不是只 record_event。

    这正是本次缺陷的核心——检测规则存在但从不执行。
    """
    src = (ROOT / "agent1.py").read_text(encoding="utf-8")
    assert "record_and_check" in src, "agent1 未接入检测，安全网仍是只记录不判断"
    assert "安全网告警" in src, "告警未附加到工具结果，模型看不到"
