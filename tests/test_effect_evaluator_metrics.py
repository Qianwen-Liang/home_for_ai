"""effect_evaluator 度量口径测试（T2840）。

修复的真实问题：
  它用 `before.avg - after.avg` 作为「性能改进量」。均值被长尾主导，
  这个差值实际反映的是「期间有几次超时」，而不是「命令变快了多少」。
  更隐蔽的是：评分逻辑里**又独立算了一遍均值差**，
  所以即使改了 delta 口径，评分仍被长尾支配——改口径却没改判定，等于白改。

外部一致性：与 health_dashboard 采用同一口径（最慢工具 p95）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evolver.effect_evaluator as EE  # noqa: E402


@pytest.fixture()
def ev(monkeypatch):
    """构造评估器，并把重采集源全部替换成常量。

    snapshot() 内部会依次触发 health_dashboard.aggregate() → self_check
    （导入并检查全部 42 个模块），单测里必须屏蔽，否则每个用例都要跑全量自检。
    """
    e = EE.EffectEvaluator()

    class _FakeDashboard:
        def aggregate(self):
            return None

        def score(self):
            return 100

        def label(self):
            return "优"

    class _FakeChecker:
        results: list = []

    class _FakeKStore:
        _data: dict = {}

    class _FakeDecision:
        _decisions: list = []

    import evolver.health_dashboard as HD
    import tools.decision_engine as DE
    import tools.knowledge_store as KS
    import tools.self_check as SC

    monkeypatch.setattr(HD, "_dashboard", _FakeDashboard())
    monkeypatch.setattr(SC, "_checker", _FakeChecker())
    monkeypatch.setattr(KS, "_store", _FakeKStore())
    monkeypatch.setattr(DE, "_engine", _FakeDecision())

    monkeypatch.setattr(EE.EffectEvaluator, "_measure_module_import_time", lambda self: None)
    monkeypatch.setattr(EE.EffectEvaluator, "_measure_pytest", lambda self: None)
    monkeypatch.setattr(EE.EffectEvaluator, "_run_smoke_test", lambda self: None)
    return e


def _patch_after(monkeypatch, snap: "EE.MetricSnapshot") -> None:
    monkeypatch.setattr(EE.EffectEvaluator, "snapshot", lambda self: snap)


# ── 1. snapshot 采集 p95 ────────────────────────────────

def test_snapshot_collects_p95(ev, monkeypatch) -> None:
    fake_data = {
        "total_calls": 100, "total_errors": 0,
        "tools": {
            "run_command": {"total_calls": 100, "total_duration": 700.0,
                            "p95_ms": 15000.0},
            "read_file": {"total_calls": 10, "total_duration": 0.1,
                          "p95_ms": 12.0},
        },
    }
    import tools.monitor as MON
    monkeypatch.setattr(
        MON, "_monitor",
        type("M", (), {"_data": fake_data, "summary": lambda self: ""})(),
    )
    snap = ev.snapshot()
    assert snap.p95_ms == 15000.0, "未取到最慢工具的 p95"


# ── 2. perf_delta 口径 ─────────────────────────────────

def test_perf_delta_prefers_p95(ev, monkeypatch) -> None:
    """有 p95 时必须用 p95 —— 均值会把 30 秒改进压成 99ms。"""
    _patch_after(monkeypatch, EE.MetricSnapshot(
        p95_ms=0.99, avg_response_ms=1.0, health_score=90))
    before = EE.MetricSnapshot(p95_ms=30000.0, avg_response_ms=100.0, health_score=90)

    r = ev.evaluate(before, "p95 口径")
    assert r.perf_basis == "p95"
    assert r.perf_delta_ms == pytest.approx(29999.01, abs=0.1), \
        f"p95 改进被低估: {r.perf_delta_ms}"


def test_perf_delta_falls_back_to_avg(ev, monkeypatch) -> None:
    """无 p95 数据时回退均值，并如实标注。"""
    _patch_after(monkeypatch, EE.MetricSnapshot(p95_ms=0.0, avg_response_ms=1.0, health_score=90))
    before = EE.MetricSnapshot(p95_ms=0.0, avg_response_ms=100.0, health_score=90)

    r = ev.evaluate(before, "avg 回退")
    assert r.perf_basis == "avg"
    assert r.perf_delta_ms == pytest.approx(99.0, abs=0.5)


# ── 3. 评分与 delta 必须同口径（核心回归） ──────────────

def test_scoring_uses_same_basis_as_delta(ev, monkeypatch) -> None:
    """回归：评分逻辑曾独立再算一遍均值差，导致改了口径但评分不变。

    构造：均值几乎没变（100→99），但 p95 从 30s 降到 1s。
    若评分用均值 → perf 维度接近 0 分；用 p95 → 应拿到接近满额的 0.10。
    """
    _patch_after(monkeypatch, EE.MetricSnapshot(
        p95_ms=1000.0, avg_response_ms=99.0, health_score=90,
        consecutive_errors=0, rescue_activated=False))
    before = EE.MetricSnapshot(
        p95_ms=30000.0, avg_response_ms=100.0, health_score=90,
        consecutive_errors=0, rescue_activated=False)

    r = ev.evaluate(before, "评分同口径")
    assert r.perf_basis == "p95"
    # 仅性能维度就会贡献约 +0.10（权重 0.10 × 归一化接近 1.0）
    assert r.overall_score >= 0.09, (
        f"评分未采用 p95 口径（score={r.overall_score}），"
        f"很可能仍在用均值算"
    )


def test_avg_only_change_is_negligible_under_p95_basis(ev, monkeypatch) -> None:
    """反向验证：p95 不变、均值大幅变化时，不应被判为大改进。

    这正是修复前的误判来源——均值波动被当成真实改进。
    """
    _patch_after(monkeypatch, EE.MetricSnapshot(
        p95_ms=1000.0, avg_response_ms=10.0, health_score=90,
        consecutive_errors=0, rescue_activated=False))
    before = EE.MetricSnapshot(
        p95_ms=1000.0, avg_response_ms=3000.0, health_score=90,
        consecutive_errors=0, rescue_activated=False)

    r = ev.evaluate(before, "均值波动")
    assert r.perf_delta_ms == pytest.approx(0.0, abs=0.1), "p95 未变却报出性能变化"
    assert r.overall_score < 0.09, f"均值波动被误判为改进: {r.overall_score}"


# ── 4. 序列化兼容 ──────────────────────────────────────

def test_report_roundtrip_keeps_basis(ev, monkeypatch) -> None:
    _patch_after(monkeypatch, EE.MetricSnapshot(p95_ms=0.99, avg_response_ms=1.0, health_score=90))
    before = EE.MetricSnapshot(p95_ms=30000.0, avg_response_ms=100.0, health_score=90)
    r = ev.evaluate(before, "序列化")

    restored = EE.EffectReport.from_dict(r.to_dict())
    assert restored.perf_basis == "p95"
    assert restored.perf_delta_ms == pytest.approx(r.perf_delta_ms)
