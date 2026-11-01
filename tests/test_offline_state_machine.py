"""offline_runner 状态机与幂等测试（T2837）。

修复的两个真实缺陷：
  1. cancel() 把状态设为 "paused" 却返回「已取消」——
     「取消」实际等于「暂停」，用户仍可用 resume 把任务捡回来，属语义欺骗。
  2. execute() 只拦截 running，未拦截 done / cancelled ——
     已完成的任务可被重复执行，结果被覆盖。

状态机合法跃迁：
  pending → running → done/failed
  running ↔ paused
  任意非 done → cancelled（终态，不可恢复）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.offline_runner as OF  # noqa: E402


@pytest.fixture()
def mgr(monkeypatch, tmp_path):
    monkeypatch.setattr(OF, "OFFLINE_DIR", tmp_path / "offline")
    return OF.OfflineTaskManager()


def _submit(mgr, title="t", **kw) -> str:
    import re
    out = mgr.submit(title=title, phases=["a", "b"], **kw)
    return re.search(r"OT-[\w-]+", out).group()


# ── 1. cancel 是终态，不是暂停 ──────────────────────────

def test_cancel_sets_cancelled_not_paused(mgr) -> None:
    """回归：cancel 曾把状态设为 paused，导致「取消」可被 resume 撤销。"""
    tid = _submit(mgr)
    mgr.cancel(tid)
    assert mgr._tasks[tid].status == "cancelled", \
        f"取消后状态是 {mgr._tasks[tid].status}，与「已取消」文案不符"


def test_cancelled_task_cannot_resume(mgr) -> None:
    """取消是终态：不能被恢复。"""
    tid = _submit(mgr)
    mgr.cancel(tid)
    out = mgr.resume(tid)
    assert "无法恢复" in out, f"已取消任务被恢复: {out[:120]}"
    assert mgr._tasks[tid].status == "cancelled"


def test_cancelled_task_cannot_execute(mgr) -> None:
    tid = _submit(mgr)
    mgr.cancel(tid)
    out = mgr.execute(tid)
    assert "已取消" in out, f"已取消任务被执行: {out[:120]}"
    assert mgr._tasks[tid].status == "cancelled"


def test_done_task_cannot_cancel(mgr) -> None:
    tid = _submit(mgr)
    mgr.execute(tid)
    assert mgr._tasks[tid].status == "done"
    out = mgr.cancel(tid)
    assert "无法取消" in out


# ── 2. execute 拦截终态 ────────────────────────────────

def test_done_task_cannot_rereun(mgr) -> None:
    """回归：已完成任务曾被允许重复执行，结果被覆盖。"""
    tid = _submit(mgr)
    mgr.execute(tid)
    first_done = mgr._tasks[tid].completed_at

    out = mgr.execute(tid)
    assert "已完成" in out, f"已完成任务被重跑: {out[:120]}"
    assert mgr._tasks[tid].completed_at == first_done, "重跑覆盖了完成时间"


def test_pending_task_can_execute(mgr) -> None:
    tid = _submit(mgr)
    out = mgr.execute(tid)
    assert mgr._tasks[tid].status == "done", f"正常任务未能执行: {out[:120]}"


def test_paused_task_resume_then_execute(mgr) -> None:
    """暂停 → 恢复 → 执行 这条合法路径必须畅通。

    pause() 只允许 running 状态暂停（不能暂停尚未开始的任务），
    因此这里直接构造 running 前置状态——execute() 是同步的，
    无法在其执行中途插入 pause。
    """
    tid = _submit(mgr)
    mgr._tasks[tid].status = "running"
    assert "已暂停" in mgr.pause(tid)
    assert mgr._tasks[tid].status == "paused"

    assert "已恢复" in mgr.resume(tid)
    assert mgr._tasks[tid].status == "pending", "resume 应回到待执行状态"

    mgr.execute(tid)
    assert mgr._tasks[tid].status == "done"


def test_cannot_pause_task_not_running(mgr) -> None:
    """未开始的任务不能暂停（否则会出现「没跑却已暂停」的怪状态）。"""
    tid = _submit(mgr)
    out = mgr.pause(tid)
    assert "无法暂停" in out
    assert mgr._tasks[tid].status == "pending"


# ── 3. 幂等 ───────────────────────────────────────────

def test_idempotency_key_dedupes(mgr) -> None:
    first = _submit(mgr, title="同样的事", idempotency_key="K1")
    out = mgr.submit(title="同样的事", phases=["a"], idempotency_key="K1")
    assert "幂等检测" in out, f"幂等键未生效: {out[:120]}"
    assert first in out, "幂等响应未指向已有任务"
    assert len(mgr._tasks) == 1, "重复提交创建了多余任务"


def test_different_keys_create_distinct_tasks(mgr) -> None:
    _submit(mgr, title="A", idempotency_key="K1")
    _submit(mgr, title="B", idempotency_key="K2")
    assert len(mgr._tasks) == 2


def test_no_key_allows_duplicates(mgr) -> None:
    """不带幂等键时允许重复提交（这是当前设计边界）。"""
    _submit(mgr, title="同名")
    _submit(mgr, title="同名")
    assert len(mgr._tasks) == 2


# ── 4. 参数契约 ───────────────────────────────────────

def test_empty_title_raises(mgr) -> None:
    with pytest.raises(OF.OfflineError):
        mgr.submit(title="   ")


def test_unknown_task_raises(mgr) -> None:
    with pytest.raises(OF.OfflineError):
        mgr.execute("NOT_EXIST")
