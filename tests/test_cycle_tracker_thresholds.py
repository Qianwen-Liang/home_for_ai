"""cycle_tracker 退化检测阈值测试（T2841）。

调研结论（实测 + 代码审查）：
  1. 阈值 HEALTH_DROP_THRESHOLD=5 是否拍脑袋？
     → 实测 health_score 连续 6 次测量**完全稳定**（均为 75，极差 0），
       噪声带为 0，阈值 5 有充足余量，不会误判。
  2. 检测后是否真的触发动作？
     → self_improver 确实调用 should_pause() 与 check_degradation()，接入完整。
  3. 口径是否与 effect_evaluator 同源问题（均值长尾）？
     → CycleSnapshot 虽然记录 avg_response_ms，但**判定逻辑不用它**
       （只用 health_score / rolled_back / verdict），故无长尾误判风险。

因此本模块**不改代码**，只补回归测试锁定阈值与判定边界，
防止将来被随意改动而失去保护能力。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evolver.cycle_tracker as CT  # noqa: E402


@pytest.fixture()
def tracker(monkeypatch, tmp_path):
    """隔离持久化文件，避免污染生产 cycle_tracker 数据。"""
    t = CT.CycleTracker()
    monkeypatch.setattr(t, "_save", lambda: None)
    return t


def _snap(tracker, cid: str, health: int, verdict: str = "", rolled: bool = False):
    """直接构造快照并注入追踪器。

    不走 record_cycle()：那个接口要求 cycle_data 使用 `health_after` 等字段名
    （面向 SelfImprover.CycleLog），与本测试要验证的判定逻辑无关。
    这里直接构造 CycleSnapshot，让测试聚焦于 check_degradation 的阈值行为。
    """
    snap = CT.CycleSnapshot(
        cycle_id=cid, timestamp="2026-11-01T00:00:00",
        improvement_name=cid, health_score=health,
        effect_verdict=verdict, rolled_back=rolled,
    )
    tracker._snapshots.append(snap)
    return snap


# ── 1. 阈值依据 ────────────────────────────────────────

def test_health_threshold_above_measured_noise() -> None:
    """阈值必须大于 health_score 的实测噪声（实测为 0）。

    实测方法见 memory/cmd_output/health_noise.py：连续 6 次均为 75。
    若将来 health_score 的计算方式改变、噪声增大，这条断言应被复查。
    """
    assert CT.CycleTracker.HEALTH_DROP_THRESHOLD >= 5, "阈值过小，会把健康分波动当退化"


def test_thresholds_are_documented() -> None:
    assert CT.CycleTracker.CONSECUTIVE_DROP_LIMIT == 3
    assert CT.CycleTracker.ROLLBACK_RATIO_LIMIT == 0.5


# ── 2. 单轮退化检测 ────────────────────────────────────

def test_single_drop_below_threshold_no_alert(tracker) -> None:
    """下降 3 点 < 阈值 5 → 不告警。"""
    _snap(tracker, "c1", 80)
    _snap(tracker, "c2", 77)
    assert tracker.check_degradation() is None


def test_single_drop_at_threshold_alerts(tracker) -> None:
    """下降正好 5 点 → 必须告警（边界包含）。"""
    _snap(tracker, "c1", 80)
    _snap(tracker, "c2", 75)
    alert = tracker.check_degradation()
    assert alert is not None
    assert alert.degradation_type == CT.DegradationType.SINGLE_DROP


def test_large_drop_is_high_severity(tracker) -> None:
    """下降 ≥10 → 严重级别应为 high。"""
    _snap(tracker, "c1", 90)
    _snap(tracker, "c2", 70)
    alert = tracker.check_degradation()
    assert alert is not None
    assert alert.severity == "high"


def test_health_increase_no_alert(tracker) -> None:
    _snap(tracker, "c1", 70)
    _snap(tracker, "c2", 85)
    assert tracker.check_degradation() is None


# ── 3. 连续退化触发暂停 ────────────────────────────────

def test_consecutive_drops_trigger_pause(tracker) -> None:
    """连续 3 轮下降且累计 ≥ HEALTH_DROP_THRESHOLD*2（即 ≥10）→ 暂停。

    注意调用顺序：先 check_degradation()（这里才会置 PAUSED），
    再 should_pause() 读取状态。这正是修复后的自改进主循环顺序。
    """
    for i, h in enumerate([100, 95, 90, 85]):   # 最后三轮回降 10 点
        _snap(tracker, f"c{i}", h)
    tracker.check_degradation()
    paused, reason = tracker.should_pause()
    assert paused is True, f"连续退化未触发暂停: {reason}"


def test_consecutive_small_drops_do_not_pause(tracker) -> None:
    """连续下降但累计不足 10 → 只告警不暂停（避免过度反应）。"""
    for i, h in enumerate([90, 88, 85, 82]):   # 累计降 6 点
        _snap(tracker, f"c{i}", h)
    tracker.check_degradation()
    paused, _ = tracker.should_pause()
    assert paused is False


def test_self_improver_detects_before_pausing() -> None:
    """回归：self_improver 必须先 check_degradation 再 should_pause。

    原顺序相反导致 should_pause 读到的是上一轮的 status，
    「连续退化触发暂停」要等下一轮才生效 —— 系统会多跑一轮带病改进。
    """
    src = (ROOT / "evolver" / "self_improver.py").read_text(encoding="utf-8")
    i_check = src.find("alert = tracker.check_degradation()")
    i_pause = src.find("should_pause, reason = tracker.should_pause()")
    assert i_check != -1 and i_pause != -1
    assert i_check < i_pause, "退化检测在暂停判断之后执行，会延迟一轮才停"


def test_non_monotonic_does_not_pause(tracker) -> None:
    for i, h in enumerate([90, 88, 89, 87]):
        _snap(tracker, f"c{i}", h)
    paused, _ = tracker.should_pause()
    assert paused is False


# ── 4. 回滚率检测 ──────────────────────────────────────

def test_high_rollback_rate_pauses(tracker) -> None:
    """最近 5 轮回滚 ≥3 次 → 暂停。"""
    for i in range(5):
        _snap(tracker, f"c{i}", 80, rolled=(i < 3))
    paused, reason = tracker.should_pause()
    assert paused is True
    assert "回滚" in reason


def test_low_rollback_rate_does_not_pause(tracker) -> None:
    for i in range(5):
        _snap(tracker, f"c{i}", 80, rolled=(i < 2))
    paused, _ = tracker.should_pause()
    assert paused is False


# ── 5. 波动检测 ────────────────────────────────────────

def test_oscillation_triggers(tracker) -> None:
    """4 轮中方向切换 ≥3 次 → 波动告警。"""
    for i, v in enumerate(["improved", "degraded", "improved", "degraded"]):
        _snap(tracker, f"c{i}", 80, verdict=v)
    alert = tracker.check_degradation()
    assert alert is not None
    assert alert.degradation_type == CT.DegradationType.OSCILLATING


def test_single_oscillation_does_not_trigger(tracker) -> None:
    for i, v in enumerate(["improved", "improved", "degraded", "degraded"]):
        _snap(tracker, f"c{i}", 80, verdict=v)
    alert = tracker.check_degradation()
    if alert is not None:
        assert alert.degradation_type != CT.DegradationType.OSCILLATING


# ── 6. 接入点存在（防止将来断开） ───────────────────────

def test_self_improver_actually_calls_tracker() -> None:
    """回归：检测必须真的被执行，而不是只存在于模块里。

    这是 safety_net 的教训——record 有、check 无，安全网等于摆设。
    """
    src = (ROOT / "evolver" / "self_improver.py").read_text(encoding="utf-8")
    assert "should_pause(" in src, "self_improver 未调用 should_pause，退化检测不会生效"
    assert "check_degradation(" in src, "self_improver 未调用 check_degradation"
    assert "record_cycle(" in src, "self_improver 未记录轮次，追踪数据为空"
