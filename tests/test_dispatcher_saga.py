"""task_dispatcher Saga 补偿测试（T2835）。

修复的真实缺陷：
  dispatch() 里 `_manager.assign_task()` 会把 Agent 置为 busy，
  之后的步骤（_save / message_bus 发送 / 状态写入）任一处抛异常，
  except 分支原本只 `return f'❌ 调度失败: {exc}'`，**不做任何补偿**。
  结果：Agent 永久卡在 busy，_find_best_agent 再也不选它 —— 典型的部分失败脏状态。

外部依据：Saga 模式要求每个正向操作都有对应补偿，失败时逆序执行。
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
import tools.task_dispatcher as TD  # noqa: E402


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """全套隔离：agents / messages / dispatch 都指向临时文件。"""
    monkeypatch.setattr(AM, "AGENT_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(MB, "MESSAGE_FILE", tmp_path / "messages.json")
    monkeypatch.setattr(TD, "DISPATCH_FILE", tmp_path / "dispatch.json")
    monkeypatch.setattr(AM, "_manager", AM.AgentManager())
    monkeypatch.setattr(MB, "_bus", MB.MessageBus())

    AM._manager.register(
        name="编码员", role="写代码",
        capabilities='["coding"]', agent_id="coder1",
    )
    d = TD.TaskDispatcher()
    r = d.decompose(
        custom_subtasks=json.dumps([{"description": "写代码", "capability": "coding"}])
    )
    import re
    pid = re.search(r"PL_[0-9a-f]+", r).group()
    return {"dispatcher": d, "pipeline": pid, "manager": AM._manager}


# ── 1. 正常路径 ─────────────────────────────────────────

def test_successful_dispatch_marks_agent_busy(env) -> None:
    out = env["dispatcher"].dispatch(pipeline_id=env["pipeline"])
    assert "已调度" in out, out[:200]
    agent = env["manager"]._agents["coder1"]
    assert agent.status == "busy"
    assert agent.current_task


def test_successful_dispatch_sets_subtask_assigned(env) -> None:
    env["dispatcher"].dispatch(pipeline_id=env["pipeline"])
    st = env["dispatcher"]._pipelines[env["pipeline"]].subtasks[0]
    assert st.status == "assigned"
    assert st.assigned_agent == "coder1"


# ── 2. 失败补偿（核心） ─────────────────────────────────

def test_failure_rolls_back_agent_to_idle(env) -> None:
    """dispatch 中途失败必须把 Agent 从 busy 恢复，杜绝脏状态。"""
    d = env["dispatcher"]
    d._save = lambda: (_ for _ in ()).throw(RuntimeError("模拟写入失败"))

    out = d.dispatch(pipeline_id=env["pipeline"])
    assert "调度失败" in out
    assert "已回滚" in out, f"返回未说明回滚: {out[:200]}"

    agent = env["manager"]._agents["coder1"]
    assert agent.status == "idle", f"Agent 卡在 {agent.status}，脏状态未清理"
    assert agent.current_task == ""


def test_failure_records_agent_fail_count(env) -> None:
    d = env["dispatcher"]
    d._save = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    d.dispatch(pipeline_id=env["pipeline"])
    assert env["manager"]._agents["coder1"].fail_count == 1


def test_failure_resets_subtask_to_pending(env) -> None:
    d = env["dispatcher"]
    d._save = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    d.dispatch(pipeline_id=env["pipeline"])

    st = d._pipelines[env["pipeline"]].subtasks[0]
    assert st.status == "pending", f"子任务停留在 {st.status}"
    assert st.assigned_agent == ""
    assert st.started_at == ""


def test_agent_is_reusable_after_rollback(env) -> None:
    """补偿后 Agent 应可被再次调度（这才是回滚的真实意义）。"""
    d = env["dispatcher"]
    original_save = d._save
    d._save = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    d.dispatch(pipeline_id=env["pipeline"])

    d._save = original_save
    out = d.dispatch(pipeline_id=env["pipeline"])
    assert "已调度" in out, f"补偿后无法重新调度: {out[:200]}"
    assert env["manager"]._agents["coder1"].status == "busy"


# ── 3. 补偿失败不掩盖原始错误 ───────────────────────────

def test_rollback_failure_does_not_mask_original_error(env, monkeypatch) -> None:
    d = env["dispatcher"]
    d._save = lambda: (_ for _ in ()).throw(RuntimeError("原始错误"))

    def broken_failed(**kwargs):
        raise RuntimeError("补偿也失败")

    monkeypatch.setattr(AM.AgentManager, "task_failed", broken_failed)
    out = d.dispatch(pipeline_id=env["pipeline"])
    assert "原始错误" in out, f"补偿失败掩盖了原始错误: {out[:200]}"
