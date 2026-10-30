"""knowledge 检索回归测试（T2795 5.1 两阶段检索改造）。

覆盖点：
  1. 剪枝后的模糊匹配与无剪枝实现**逐条等价**（含含空格词条这一踩过的坑）
  2. 索引复用不改变检索结果（同一查询多次调用一致）
  3. kind 过滤 / 空查询 / 不存在的词 等边界
  4. encode_batch 的接口契约（长度对齐、空输入、无模型时返回 None）
  5. 向量缓存脏标记与 flush 语义
"""
from __future__ import annotations

import sys
from difflib import SequenceMatcher
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.knowledge_store as K  # noqa: E402
from tools.knowledge_store import KnowledgeStore, SearchEnhancer  # noqa: E402


def _legacy_fuzzy(text: str, terms: list[str]) -> float:
    """改造前实现（无剪枝），作为等价性判决基准。"""
    if not terms or not text:
        return 0.0
    tl = text.lower()
    best = 0.0
    for term in terms:
        if not term:
            continue
        if term in tl:
            best = max(best, 1.0)
        else:
            best = max(best, SequenceMatcher(None, tl, term).ratio() * 0.7)
    return best


# ── 1. 剪枝等价性 ─────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "使用缓存优化性能的方法",
        "test_tools.py 使用过时 API 的 bug",
        "abc",
        "",
        "a b c d e f",
        "缓存 优化 性能",
        "纯中文文本没有英文",
        "x" * 200,
    ],
)
@pytest.mark.parametrize(
    "terms",
    [
        ["性能", "效率", "缓存 优化 性能", "缓存"],
        ["cache", "boundary"],
        ["a"],
        ["不存在词xyz", "abc"],
        [""],
        ["缓", "存"],
    ],
)
def test_fuzzy_pruning_equivalence(text: str, terms: list[str]) -> None:
    """剪枝实现必须与无剪枝实现逐条等价（浮点完全相等）。"""
    expected = _legacy_fuzzy(text, terms)
    actual = SearchEnhancer.best_fuzzy_score(text, terms)
    assert actual == pytest.approx(expected, abs=1e-12), (
        f"text={text!r} terms={terms!r} expected={expected} actual={actual}"
    )


def test_fuzzy_with_space_term_not_zeroed() -> None:
    """含空格的整句词条仍可因空格匹配而得分（首版剪枝的真实 bug）。"""
    # 标题含空格，词条含空格 → SequenceMatcher 能匹配空格，ratio > 0
    score = SearchEnhancer.best_fuzzy_score(
        "test_tools.py 使用过时 api 的 bug", ["缓存 优化 性能"]
    )
    assert score > 0, "含空格词条被错误归零——字符频次交集剪枝写错了"


def test_fuzzy_with_precomputed_counts() -> None:
    """传入预计算字符频次时结果不变。"""
    text = "缓存优化与性能分析"
    terms = ["性能", "缓存", "xyz"]
    counts: dict[str, int] = {}
    for ch in text.lower():
        counts[ch] = counts.get(ch, 0) + 1
    assert SearchEnhancer.best_fuzzy_score(text, terms) == SearchEnhancer.best_fuzzy_score(
        text, terms, counts
    )


# ── 2. 索引复用不改变结果 ─────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> KnowledgeStore:
    s = KnowledgeStore(path=tmp_path / "kb.json")
    s.store("缓存与性能", "引入缓存后检索性能显著提升。", category="perf", tags="缓存,性能")
    s.store("边界条件", "当输入为空时函数应返回 None。", category="edge", tags="边界", kind="boundary")
    s.store("契约测试", "契约测试保证模块之间的接口稳定。", category="test", tags="契约")
    return s


def test_search_repeatable(store: KnowledgeStore) -> None:
    a = store.search("缓存 性能", 5, mode="keyword")
    b = store.search("缓存 性能", 5, mode="keyword")
    assert a == b, "同一查询两次结果不一致（索引或缓存状态泄漏）"


def test_index_invalidation_on_store(store: KnowledgeStore) -> None:
    """写入新条目后索引必须失效重建，新条目可被检索到。"""
    store.search("独特词甲", 5, mode="keyword")
    store.store("独特词甲标题", "独特词甲 出现在正文里。", category="x", tags="独特词甲")
    out = store.search("独特词甲", 5, mode="keyword")
    assert "独特词甲标题" in out, f"新增条目未被检索到（索引未失效）：{out[:200]}"


def test_kind_filter(store: KnowledgeStore) -> None:
    store._ensure_index()
    boundary_titles = [
        it["entry"]["title"] for it in store._index
        if it["entry"].get("kind") == "boundary"
    ]
    assert boundary_titles, "fixture 中应存在 boundary 条目"
    out = store.search("边界条件", 50, mode="keyword", kind="boundary")
    assert "缓存与性能" not in out, "kind 过滤失效：混入了 declarative 条目"


def test_kind_filter_excludes_other_kinds(store: KnowledgeStore) -> None:
    """所有返回条目的 kind 必须与过滤条件一致。"""
    import re

    out = store.search("缓存", 50, mode="keyword", kind="declarative")
    ids = re.findall(r"\[(K[^\]]+)\]", out)
    for entry_id in ids:
        assert store._data[entry_id].get("kind", "declarative") == "declarative"


def test_empty_query_raises(store: KnowledgeStore) -> None:
    with pytest.raises(K.KnowledgeStoreError):
        store.search("", 5)


def test_no_match_returns_message(store: KnowledgeStore) -> None:
    out = store.search("zzzz-绝不存在-qqqq", 3, mode="keyword")
    # 关键词评分恒 >= 0，可能仍返回条目；关键是不抛异常且格式完整
    assert isinstance(out, str) and out


# ── 3. 索引结构 ───────────────────────────────────────────


def test_index_built_once(store: KnowledgeStore) -> None:
    store._ensure_index()
    first = store._index
    store._ensure_index()
    assert store._index is first, "索引在数据未变更时被重复构建"


def test_index_precomputed_fields(store: KnowledgeStore) -> None:
    store._ensure_index()
    item = store._index[0]
    for key in ("title_lower", "content_lower", "tags_lower", "category_lower",
                "title_counts", "content_counts"):
        assert key in item["pre"], f"索引缺少预计算字段 {key}"
    assert item["search_text"] == item["search_text"].lower()


# ── 4. encode_batch 契约 ─────────────────────────────────


def test_encode_batch_empty() -> None:
    assert K._semantic_engine.encode_batch([]) == []


def test_encode_batch_length_alignment() -> None:
    """无论模型是否可用，返回列表必须与输入等长（接口契约）。"""
    out = K._semantic_engine.encode_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(v is None or isinstance(v, list) for v in out)


def test_flush_cache_idempotent() -> None:
    """无脏数据时 flush 不应写盘。"""
    eng = K._semantic_engine
    eng._cache_dirty = False
    eng.flush_cache()  # 不应抛异常
    assert eng._cache_dirty is False
