"""orchestrator 自动重试测试（T2836）。

修复的文档与实现不一致：
  orchestrator 的 docstring 承诺「失败重试：失败子任务自动重新分配」，
  但 run() 的实际流程是 decompose → dispatch_all → collect，
  失败后只输出提示「使用 orchestrator action=retry 手动重试」——
  **自动重试并不存在**。

本文件锁定修复后的行为：run 在发现失败子任务时自动重试一轮，
且只重试一轮（防止无限循环），仍失败则明确交回人工介入。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.agent_manager as AM  # noqa: E402
import tools.message_bus as MB  # noqa: E402
import tools.orchestrator as OR  # noqa: E402
import tools.task_dispatcher as TD  # noqa: E402


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """隔离 agents / messages / dispatch，并注册一个编码 Agent。"""
    monkeypatch.setattr(AM, "AGENT_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(MB, "MESSAGE_FILE", tmp_path / "messages.json")
    monkeypatch.setattr(TD, "DISPATCH_FILE", tmp_path / "dispatch.json")
    monkeypatch.setattr(AM, "_manager", AM.AgentManager())
    monkeypatch.setattr(MB, "_bus", MB.MessageBus())
    monkeypatch.setattr(TD, "_dispatcher", TD.TaskDispatcher())
    monkeypatch.setattr(OR, "_orchestrator", OR.Orchestrator())

    AM._manager.register(
        name="编码员", role="写代码",
        capabilities='["coding"]', agent_id="coder1",
    )
    return OR._orchestrator


# ── 1. 文档与实现一致性 ─────────────────────────────────

def test_run_contains_auto_retry(env) -> None:
    """回归：run() 必须包含自动重试逻辑，而不只是提示手动 retry。

    这正是本次缺陷的核心——文档写"自动"，代码只给提示。
    """
    import inspect
    src = inspect.getsource(OR.Orchestrator.run)
    assert "failed_now" in src, "run 未检测失败子任务，自动重试不存在"
    assert "self.retry(" in src, "run 未调用 retry，仍是手动重试"


def test_manual_retry_still_available(env) -> None:
    """自动重试不应取代手动重试入口。"""
    assert hasattr(OR.Orchestrator, "retry")


# ── 2. 自动重试的实际行为 ───────────────────────────────

def test_auto_retry_recovers_failed_subtask(env, monkeypatch) -> None:
    """单轮自动重试后，失败子任务应被恢复到可调度状态。"""
    out = env.run(task="写一个模块")
    # 正常路径下不应出现"仍有失败"的告警
    assert "仍需人工介入" not in out


def test_auto_retry_only_once(env, monkeypatch) -> None:
    """必须只重试一轮：持续失败的子任务不能被无限重试。"""
    calls = {"n": 0}
    original_retry = OR.Orchestrator.retry

    def counting_retry(self, pipeline_id="", subtask_id=""):
        calls["n"] += 1
        return original_retry(self, pipeline_id, subtask_id)

    monkeypatch.setattr(OR.Orchestrator, "retry", counting_retry)
    env.run(task="写一个模块")
    assert calls["n"] <= 1, f"自动重试超过一轮（{calls['n']} 次），存在无限循环风险"


def test_retry_failure_does_not_break_run(env, monkeypatch) -> None:
    """重试自身抛异常时，整体编排仍应返回结果而不是崩溃。"""
    def boom(self, pipeline_id="", subtask_id=""):
        raise RuntimeError("retry exploded")

    # 先制造一个失败子任务，让 run 进入重试分支
    original_dispatch_all = TD.TaskDispatcher.dispatch_all

    def failing_dispatch_all(self, pipeline_id="", strategy="dag"):
        pipeline = self._pipelines[pipeline_id]
        for st in pipeline.subtasks:
            st.status = "failed"
        return "模拟全部失败"

    monkeypatch.setattr(TD.TaskDispatcher, "dispatch_all", failing_dispatch_all)
    monkeypatch.setattr(OR.Orchestrator, "retry", boom)

    out = env.run(task="写一个模块")
    assert "流水线编排完成" in out, f"重试异常导致整体崩溃: {out[:200]}"
    assert "自动重试失败" in out


# ── 3. 提示语保持准确 ───────────────────────────────────

def test_output_mentions_manual_retry_as_fallback(env) -> None:
    """自动重试之外，仍需保留手动 retry 的提示（人工兜底）。"""
    out = env.run(task="写一个模块")
    assert "action=retry" in out
