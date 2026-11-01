"""health_dashboard 度量口径对齐测试（T2838）。

修复的真实问题：
  health_dashboard 判断性能健康时只用**均值**（`avg_response_ms < 500`），
  而均值会被长尾完全污染——实测 run_command 均值 7054ms，
  实际中位数只有 83ms，两者差两个数量级。
  monitor 从 B0 起已提供 p50/p95/p99，但这里没接上。

修复后：优先用「最慢工具的 p95」判定，无分位数数据时回退均值，
并在数据里显式标注用了哪个口径（latency_basis），避免读者误解。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evolver.health_dashboard as HD  # noqa: E402


@pytest.fixture()
def dash(monkeypatch):
    """构造一个只含 monitor 数据源的仪表盘，屏蔽 self_check/safety_net 干扰。"""
    d = HD.HealthDashboard()
    monkeypatch.setattr(HD.HealthDashboard, "_collect_self_check", lambda self: {"source": "self_check", "failed": 0, "warnings": 0})
    monkeypatch.setattr(HD.HealthDashboard, "_collect_safety", lambda self: {"source": "safety_net", "consecutive_errors": 0})
    return d


def _fake_monitor(monkeypatch, tools: dict) -> None:
    data = {"total_calls": 100, "total_errors": 0, "tools": tools}
    monkeypatch.setattr(HD.HealthDashboard, "_collect_monitor", lambda self: self._collect_monitor_from(data))


def test_monitor_collects_p95() -> None:
    """采集层必须把 p95 带出来，不能只有均值。"""
    d = HD.HealthDashboard()
    data = {
        "total_calls": 10, "total_errors": 0,
        "tools": {"run_command": {"calls": 10, "total_duration": 70.0,
                                  "p50_ms": 83.0, "p95_ms": 15000.0}},
    }
    r = d._collect_monitor_from(data)
    assert r["p95_ms"] == 15000.0
    assert r["avg_response_ms"] == 7000.0
    assert r["latency_basis"] == "p95", "有分位数时应优先用 p95"


def test_falls_back_to_avg_without_percentiles() -> None:
    """老数据没有 p95 字段时回退均值，并如实标注。"""
    d = HD.HealthDashboard()
    data = {
        "total_calls": 10, "total_errors": 0,
        "tools": {"t": {"calls": 10, "total_duration": 1.0}},
    }
    r = d._collect_monitor_from(data)
    assert r["p95_ms"] is None
    assert r["latency_basis"] == "avg"


def test_high_p95_low_mean_is_flagged() -> None:
    """核心价值：均值看似正常、p95 很高的系统，必须被判为过慢。

    这是修复前后行为差异最大的场景——
    旧逻辑只看均值会放过这类长尾系统。
    """
    d = HD.HealthDashboard()
    data = {
        "total_calls": 100, "total_errors": 0,
        "tools": {"run_command": {"calls": 100, "total_duration": 10.0,
                                  "p50_ms": 50.0, "p95_ms": 30000.0}},
    }
    r = d._collect_monitor_from(data)
    assert r["avg_response_ms"] == 100.0, "构造前提：均值很低"
    assert r["p95_ms"] == 30000.0
    assert r["healthy"] is False, "长尾系统被误判为健康"


def test_low_p95_is_healthy() -> None:
    d = HD.HealthDashboard()
    data = {
        "total_calls": 100, "total_errors": 0,
        "tools": {"t": {"calls": 100, "total_duration": 5.0,
                        "p50_ms": 40.0, "p95_ms": 60.0}},
    }
    r = d._collect_monitor_from(data)
    assert r["healthy"] is True


def test_score_uses_p95_for_latency(monkeypatch) -> None:
    """评分环节也要用 p95：均值 100ms 但 p95 30s，应扣分并写明 P95。"""
    d = HD.HealthDashboard()
    results = [
        {"source": "self_check", "failed": 0, "warnings": 0},
        {"source": "monitor", "error_rate": 0, "avg_response_ms": 100.0,
         "p95_ms": 30000.0, "latency_basis": "p95", "has_data": True},
        {"source": "safety_net", "consecutive_errors": 0},
    ]
    score = d._compute_score(results)
    assert score < 100, "长尾未被扣分"
    assert any("P95" in w or "P95" in i for w in d._warnings + d._issues), \
        f"扣分理由未说明用的是 P95: {d._warnings + d._issues}"


def test_score_falls_back_to_avg_when_no_p95(monkeypatch) -> None:
    d = HD.HealthDashboard()
    results = [
        {"source": "self_check", "failed": 0, "warnings": 0},
        {"source": "monitor", "error_rate": 0, "avg_response_ms": 2000.0,
         "p95_ms": None, "latency_basis": "avg", "has_data": True},
        {"source": "safety_net", "consecutive_errors": 0},
    ]
    score = d._compute_score(results)
    assert score < 100
    assert any("平均响应" in w or "平均响应" in i for w in d._warnings + d._issues)
