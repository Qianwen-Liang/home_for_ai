"""audit_log 可读性测试（T2842）。

修复的真实问题：
  audit_log 长期**只写不读**。self_healing / self_improver 调 log 与
  update_outcome 持续累积（实测 94 条），但 query/report/stats 仅服务
  工具接口，而该工具在 LEGACY_TOOLS 中 —— LLM 看不见，也无人读取。
  「不可变性 / 完整性 / 可追溯」三条设计原则里，可追溯性实际没有消费者。

修复：把最近审计摘要并入 run_multi_cycles 的返回（零 schema 成本），
使每轮改进循环结束时都能回看历史决策。

另记录一处文档与实现不符：
  docstring 宣称「不可变性：已记录的条目不可修改」，但 update_outcome
  会直接改写 outcome / actual_effect / health_after 等字段。
  准确说法是「决策内容不可改，结果字段可事后补填」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evolver.audit_log as AL  # noqa: E402
import evolver.self_improver as SI  # noqa: E402


@pytest.fixture()
def audit(monkeypatch, tmp_path):
    """隔离审计文件，避免污染生产 audit_log.json。"""
    monkeypatch.setattr(AL, "AUDIT_FILE", tmp_path / "audit_log.json")
    a = AL.AuditLog()
    monkeypatch.setattr(AL, "_audit", a)
    return a


# ── 1. 摘要读取结构 ────────────────────────────────────

def test_trail_structure(audit) -> None:
    audit.log(decision="测试决策", rationale="理由", strategy_mode="conservative", tags=["t"])
    d = SI._recent_audit_trail(days=1)
    for key in ("recent_days", "recent_count", "total_entries", "entries"):
        assert key in d, f"摘要缺少字段 {key}"


def test_trail_reports_total_even_when_recent_is_zero(audit) -> None:
    """回归：只报「最近 0 条」会被误读为「没有审计记录」。

    实际可能是「有历史记录，但近期没有新决策」（生产库实测 94 条 / 近期 0 条）。
    """
    audit.log(decision="历史决策", rationale="理由", strategy_mode="conservative")
    for e in audit._entries.values():
        e.timestamp = "2020-01-01T00:00:00"      # 人为做旧
    d = SI._recent_audit_trail(days=1)
    assert d["recent_count"] == 0
    assert d["total_entries"] == 1, "近期为 0 时必须给出总量，否则会被误读"


def test_trail_lists_recent_entries(audit) -> None:
    for i in range(3):
        audit.log(decision=f"决策{i}", rationale="理由", strategy_mode="conservative")
    d = SI._recent_audit_trail(days=1)
    assert d["recent_count"] == 3
    assert len(d["entries"]) == 3
    assert all("decision" in e and "outcome" in e for e in d["entries"])


def test_trail_caps_entries_at_limit(audit) -> None:
    for i in range(10):
        audit.log(decision=f"决策{i}", rationale="理由", strategy_mode="conservative")
    d = SI._recent_audit_trail(days=1, limit=3)
    assert len(d["entries"]) == 3


# ── 2. 不可用时优雅降级 ────────────────────────────────

def test_trail_degrades_when_audit_unavailable(monkeypatch) -> None:
    """审计不可用不能中断改进循环，应返回 error 字段。"""
    def boom(*a, **k):
        raise RuntimeError("audit exploded")

    class _Broken:
        _entries: dict = {}

        def query(self, *a, **k):
            raise RuntimeError("audit exploded")

    monkeypatch.setattr(AL, "_audit", _Broken())
    d = SI._recent_audit_trail()
    assert "error" in d


# ── 3. 接入点（防止将来再次只写不读） ────────────────────

def test_multi_cycles_result_contains_audit_trail() -> None:
    """回归：审计摘要必须进入多轮总结，否则仍是只写不读。"""
    import inspect
    src = inspect.getsource(SI.SelfImprover.run_multi_cycles)
    assert "audit_trail" in src, "run_multi_cycles 未输出审计摘要，历史决策仍无人阅读"
    assert "_recent_audit_trail" in src


def test_audit_is_written_by_improver() -> None:
    """写入侧仍然存在（不能让可读性修复把写入搞丢）。"""
    src = (ROOT / "evolver" / "self_improver.py").read_text(encoding="utf-8")
    assert "_audit" in src
