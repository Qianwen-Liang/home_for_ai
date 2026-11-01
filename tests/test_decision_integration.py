"""decision_engine 恢复注册与接入测试（T2829）。

背景：decision_engine 持有 6 条「已知死路」清单（如"18 次参数变异全部 REJECT"）
+ 边界卡片注入 + 历史失败决策匹配，是防止重复撞墙的核心资产。
但它在 P0 工具集收敛（42→16）时被移出注册表 → LLM 完全看不见 → 从不被调用。

本次两层修复：
  1. 恢复注册（可见）——schema 成本 289 tokens，总量 3155，仍在 3500 预算内
  2. task_tracker 建任务时复用其死路匹配（自动使用）
     ——「可见」不等于「会被用」，这是本项目反复出现的模式。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent1  # noqa: E402
import tools.decision_engine as de  # noqa: E402
from tools.task_tracker import TaskTracker, _related_boundaries  # noqa: E402

SCHEMA_BUDGET_TOKENS = 3500


# ── 1. 恢复注册 ─────────────────────────────────────────

def test_decision_engine_registered() -> None:
    names = [t["function"]["name"] for t in agent1.ALL_TOOLS]
    assert "decision_engine" in names, "decision_engine 未恢复注册"


def test_not_in_legacy_list() -> None:
    assert "decision_engine" not in agent1.LEGACY_TOOLS, "仍在 legacy 列表会导致语义矛盾"


def test_schema_within_budget() -> None:
    chars = len(json.dumps(agent1.ALL_TOOLS, ensure_ascii=False))
    tokens = chars / 3.6
    assert tokens <= SCHEMA_BUDGET_TOKENS, f"schema {tokens:.0f} tokens 超出预算 {SCHEMA_BUDGET_TOKENS}"


def test_tool_count_is_17() -> None:
    """工具集从 16 恢复为 17，需显式记录以免被无声改动。"""
    assert len(agent1.ALL_TOOLS) == 17


def test_registry_matches_all_tools() -> None:
    """字节稳定断言：注册表装配结果必须与 ALL_TOOLS 一致。

    agent1 模块级已有此检查（不一致会拒绝启动），这里再显式断言一次，
    让测试失败信息更直接。
    """
    payload = agent1.REGISTRY.fingerprint(agent1.REGISTRY.names())
    expected = json.dumps(agent1.ALL_TOOLS, ensure_ascii=False, separators=(",", ":"))
    assert payload == expected, "注册表与 ALL_TOOLS 存在字节漂移"


# ── 2. 死路匹配 ─────────────────────────────────────────

def test_match_dead_ends_hits() -> None:
    hits = de.match_dead_ends("单点参数变异调参 restart rephase")
    assert hits, "已知死路未命中"
    entry, matched = hits[0]
    assert entry["category"] in ("已知死路", "方法教训", "开放问题")
    assert matched


def test_match_dead_ends_clean_text() -> None:
    assert de.match_dead_ends("qqqqwwww") == []


def test_gate_uses_shared_matcher() -> None:
    """gate 必须复用 match_dead_ends，而不是各写一套。"""
    import inspect
    src = inspect.getsource(de.DecisionEngine.gate)
    assert "match_dead_ends" in src, "gate 未复用 match_dead_ends，存在逻辑重复风险"


# ── 3. task_tracker 自动使用 ────────────────────────────

def test_task_hint_includes_dead_end() -> None:
    """建任务时的提示应包含死路结论——这是「自动使用」的关键。"""
    hits = _related_boundaries("单点参数变异调参优化")
    assert any("[死路]" in h for h in hits), f"死路未出现在任务提示中: {hits}"


def test_task_hint_no_false_positive_on_junk() -> None:
    """无意义标题不得产生**死路**误报。

    注意不能断言整体为空：conftest 会把知识库替换成只含种子卡片的临时库，
    种子卡片可能对无意义词产生低分模糊匹配。这里只约束死路部分——
    死路是精确的关键词集合匹配，不该误报。
    """
    hits = _related_boundaries("xyzzy nothing here")
    dead = [h for h in hits if "[死路]" in h]
    assert dead == [], f"无意义标题触发了死路误报: {dead}"


def test_task_hint_still_reports_knowledge_boundary(monkeypatch, tmp_path) -> None:
    """原有知识库边界提示不能被死路逻辑挤掉。"""
    import tools.knowledge_store as K

    store = K.KnowledgeStore(path=tmp_path / "kb.json")
    store.store(
        title="测试污染生产数据",
        content="跑压测会把生产 monitor 数据清空，必须用临时路径隔离。",
        category="lesson", tags="污染,测试,monitor", kind="boundary",
    )
    monkeypatch.setattr(K, "_store", store)

    hits = _related_boundaries("测试污染生产数据治理")
    assert any("测试污染生产数据" in h for h in hits), f"知识库边界提示丢失: {hits}"


def test_create_surfaces_dead_end(monkeypatch, tmp_path: Path) -> None:
    import tools.knowledge_store as K

    monkeypatch.setattr(K, "_store", K.KnowledgeStore(path=tmp_path / "kb.json"))
    tracker = TaskTracker(path=tmp_path / "tasks.json")
    out = tracker.create("单点参数变异调参优化")
    assert "已创建任务" in out
    assert "死路" in out, f"create 未透出死路提示: {out}"
