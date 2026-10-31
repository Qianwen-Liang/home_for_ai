"""任务创建时的知识复用测试（T2821）。

背景：知识库长期"只积不用"——`decision_engine.advise` 里的边界卡片注入
几乎从不被调用（agent 基本不用 advise）。把注入挂到 task_tracker.create
这个高频入口，让经验在任务开始时可见。

本测试锁定三件事：
  1. 真相关的任务标题能命中边界卡片
  2. 无意义标题**不得**返回任何提示（假阳性比漏报更糟）
  3. create 的返回确实包含提示，且不显著拖慢
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.task_tracker import TaskTracker, _related_boundaries  # noqa: E402


# ── 1. 命中真实边界 ──────────────────────────────────────

@pytest.fixture()
def kb_with_boundary(monkeypatch, tmp_path):
    """构造只含一条 boundary 卡片的隔离知识库。

    不能依赖生产知识库内容——conftest 已把 _store 替换为空库（这是对的），
    测试需要自己提供可预期的语料。
    """
    import tools.knowledge_store as K

    store = K.KnowledgeStore(path=tmp_path / "kb.json")
    store.store(
        title="测试污染生产数据",
        content="跑压测会把生产 monitor 数据清空，必须用临时路径隔离。",
        category="lesson",
        tags="污染,测试,monitor",
        kind="boundary",
    )
    monkeypatch.setattr(K, "_store", store)
    return store


def test_matches_known_boundary(kb_with_boundary) -> None:
    """与卡片标题高度重叠的任务标题应命中该卡片。"""
    hits = _related_boundaries("测试污染生产数据治理")
    assert hits, "已知相关的任务标题未命中任何边界卡片"
    assert any("测试污染生产数据" in h for h in hits)
    assert len(hits) <= 2, "返回条数超出 limit"


def test_returns_at_most_limit(kb_with_boundary) -> None:
    hits = _related_boundaries("测试污染生产数据治理", limit=1)
    assert len(hits) <= 1


# ── 2. 假阳性防护（最重要） ──────────────────────────────

@pytest.mark.parametrize("junk", [
    "xyzzynothinghere",
    "qqqqwwww",
    "zzzzzzzzzz",
])
def test_no_false_positive_on_meaningless_title(junk: str) -> None:
    """无意义标题必须返回空。

    首版用 2-3 字片段子串匹配，'xyzzynothinghere' 会撞上英文片段
    （the/there）返回无关卡片；改用 search + 分数阈值后消除。
    错误的提示比没有提示更糟——它会误导后续判断。
    """
    assert _related_boundaries(junk) == [], f"无意义标题 '{junk}' 产生了假阳性"


def test_empty_title_safe() -> None:
    assert _related_boundaries("") == []
    assert _related_boundaries("   ") == []


# ── 3. create 集成 ───────────────────────────────────────

def test_create_includes_hint_when_relevant(kb_with_boundary, tmp_path: Path) -> None:
    tracker = TaskTracker(path=tmp_path / "tasks.json")
    out = tracker.create("测试污染生产数据治理")
    assert "已创建任务" in out
    # 命中时应带出提示段落
    assert "失效边界" in out or "⚠️" in out


def test_create_without_hint_for_unrelated(tmp_path: Path) -> None:
    tracker = TaskTracker(path=tmp_path / "tasks.json")
    out = tracker.create("qqqqwwww")
    assert "已创建任务" in out
    assert "失效边界" not in out, "无关任务不应附带边界提示"


# ── 4. 性能护栏 ─────────────────────────────────────────

def test_hint_latency_acceptable() -> None:
    """单次提示检索应远低于 100ms（批量建任务时不至于明显拖慢）。"""
    t0 = time.perf_counter()
    for _ in range(5):
        _related_boundaries("测试污染生产数据")
    elapsed = (time.perf_counter() - t0) / 5
    assert elapsed < 0.1, f"单次提示耗时 {elapsed*1000:.1f}ms，超过 100ms 护栏"


def test_bulk_create_not_too_slow(tmp_path: Path) -> None:
    """批量创建 20 个任务的总耗时应可控（防止提示逻辑放大成性能问题）。"""
    tracker = TaskTracker(path=tmp_path / "tasks.json")
    t0 = time.perf_counter()
    for i in range(20):
        tracker.create(f"批量任务 {i}")
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"20 个任务耗时 {elapsed:.2f}s，提示逻辑过重"
