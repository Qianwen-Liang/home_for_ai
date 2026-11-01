"""agent_manager 心跳新鲜度测试（T2832）。

修复的真实缺陷：
  heartbeat() 只更新 last_heartbeat，**从不判定是否过期**。
  report() 汇总层按「5 分钟内」算健康数，明细层却只要有过心跳就报「✅ 健康」
  —— 一年前的心跳也显示健康；崩溃的 Agent 状态永远停在 busy/idle，
  仍会被 discover 发现、被 assign_task 分配任务。

外部依据：服务注册中心（Consul / etcd lease）都以 TTL 判定健康，
超时即视为不可用并从可调度集合中摘除。
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.agent_manager as AM  # noqa: E402


def _hb(delta_seconds: int) -> str:
    t = datetime.datetime.now() - datetime.timedelta(seconds=delta_seconds)
    return t.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def mgr(monkeypatch, tmp_path):
    """隔离到临时文件，绝不触碰生产 memory/agents.json。"""
    monkeypatch.setattr(AM, "AGENT_FILE", tmp_path / "agents.json")
    m = AM.AgentManager()
    return m


def _register(mgr, agent_id="a1", capability=AM.AgentCapability.RESEARCH.value):
    mgr.register(
        name="测试员",
        role="用于测试",
        capabilities='["%s"]' % capability,
        agent_id=agent_id,
    )
    return mgr._agents[agent_id]


# ── 1. is_stale 判定 ────────────────────────────────────

def test_newly_registered_is_not_stale(mgr) -> None:
    """新注册的 Agent 注册即写入心跳时间，应判为新鲜。"""
    a = _register(mgr)
    assert a.last_heartbeat != ""
    assert mgr.is_stale(a) is False


def test_absent_heartbeat_is_not_stale(mgr) -> None:
    """last_heartbeat 为空时不判过期（避免误杀尚未上报的实例）。"""
    a = AM.AgentRegistration(agent_id="nohb", name="n", role_description="d")
    a.last_heartbeat = ""
    assert mgr.is_stale(a) is False


def test_fresh_heartbeat_not_stale(mgr) -> None:
    a = _register(mgr)
    a.last_heartbeat = _hb(10)
    assert mgr.is_stale(a) is False


def test_expired_heartbeat_is_stale(mgr) -> None:
    a = _register(mgr)
    a.last_heartbeat = _hb(mgr.HEARTBEAT_TTL_SECONDS + 60)
    assert mgr.is_stale(a) is True


def test_long_expired_heartbeat_is_stale(mgr) -> None:
    """回归：一年前的心跳必须判为过期（原实现会显示「✅ 健康」）。"""
    a = _register(mgr)
    a.last_heartbeat = _hb(365 * 24 * 3600)
    assert mgr.is_stale(a) is True


def test_corrupted_timestamp_is_stale(mgr) -> None:
    a = _register(mgr)
    a.last_heartbeat = "not-a-timestamp"
    assert mgr.is_stale(a) is True


def test_ttl_is_five_minutes(mgr) -> None:
    """TTL 与 report 汇总层口径一致（5 分钟），改动需同步两处。"""
    assert mgr.HEARTBEAT_TTL_SECONDS == 300


# ── 2. report 明细层口径 ────────────────────────────────

def test_report_marks_expired_heartbeat(mgr) -> None:
    a = _register(mgr)
    a.last_heartbeat = _hb(365 * 24 * 3600)
    out = mgr.report()
    assert "心跳过期" in out, f"过期心跳未在报告中标注: {out[-400:]}"
    assert "✅ 健康" not in out.split(a.agent_id)[1][:200]


def test_report_shows_healthy_for_fresh(mgr) -> None:
    a = _register(mgr)
    a.last_heartbeat = _hb(10)
    out = mgr.report()
    seg = out.split(a.agent_id)[1][:200]
    assert "✅ 健康" in seg


# ── 3. discover 排除过期 Agent ──────────────────────────

def test_discover_excludes_stale_agent(mgr) -> None:
    """崩溃（心跳过期）的 Agent 不应被发现为可用。"""
    a = _register(mgr, "stale1")
    a.last_heartbeat = _hb(mgr.HEARTBEAT_TTL_SECONDS + 60)
    out = mgr.discover(AM.AgentCapability.RESEARCH.value)
    assert "stale1" not in out, f"过期 Agent 仍被发现: {out}"


def test_discover_includes_fresh_agent(mgr) -> None:
    a = _register(mgr, "fresh1")
    a.last_heartbeat = _hb(10)
    out = mgr.discover(AM.AgentCapability.RESEARCH.value)
    assert "fresh1" in out


def test_discover_includes_never_heartbeat_agent(mgr) -> None:
    """未发过心跳的新 Agent 仍可被发现（不误杀）。"""
    _register(mgr, "newbie")
    out = mgr.discover(AM.AgentCapability.RESEARCH.value)
    assert "newbie" in out


# ── 4. assign_task 拒绝过期 Agent ───────────────────────

def test_assign_task_refuses_stale_agent(mgr) -> None:
    a = _register(mgr, "stale2")
    a.last_heartbeat = _hb(mgr.HEARTBEAT_TTL_SECONDS + 60)
    out = mgr.assign_task(agent_id="stale2", task_description="做点事")
    assert "心跳已过期" in out, f"过期 Agent 仍被派活: {out}"
    assert a.status != AM.AgentStatus.BUSY.value, "拒绝派活后不应变成 busy"


def test_assign_task_allows_fresh_agent(mgr) -> None:
    a = _register(mgr, "fresh2")
    a.last_heartbeat = _hb(5)
    out = mgr.assign_task(agent_id="fresh2", task_description="做点事")
    assert a.status == AM.AgentStatus.BUSY.value, f"正常 Agent 应被派活: {out}"
