"""knowledge 检索性能基准 v2（T2795 5.1）。

与 v1 的区别：
  * 阶段拆解走**生产路径**（复用 KnowledgeStore 索引的预计算字段）
  * 统计 SequenceMatcher 实际调用次数，量化剪枝效果
  * 对比「改造前算法」与「改造后算法」的端到端耗时

用法:
    python scripts/bench_knowledge_search.py
    python scripts/bench_knowledge_search.py --json
"""
from __future__ import annotations

import difflib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.knowledge_store as K  # noqa: E402

QUERIES = ["缓存 优化 性能", "语义检索", "boundary 失效边界", "如何设计契约测试"]

_SM_CALLS = {"n": 0}
_ORIG_SM = difflib.SequenceMatcher


class _CountingSM(_ORIG_SM):
    def __init__(self, *a, **kw):
        _SM_CALLS["n"] += 1
        super().__init__(*a, **kw)


def _install_counter() -> None:
    K.SequenceMatcher = _CountingSM


def _remove_counter() -> None:
    K.SequenceMatcher = _ORIG_SM


# ── 改造前的评分逻辑（用于耗时对比，逻辑逐字复制） ──────────────


def legacy_idf(store, terms):
    counts = {}
    for term in terms:
        if not term:
            continue
        c = 0
        for e in store._data.values():
            st = (
                f"{e['title']} {e['content']} {e['category']} {' '.join(e['tags'])}"
            ).lower()
            if term in st:
                c += 1
        counts[term] = max(c, 1)
    return counts


def legacy_pipeline(store, query: str, max_results: int = 5) -> None:
    """改造前的完整关键词检索流水线（无索引、无剪枝、逐条 rebuild 文本）。"""
    se = K._search_enhancer
    total = len(store._data)
    terms = list(set(se.expand_query(query)))
    df = legacy_idf(store, terms)
    results = []
    for entry in store._data.values():
        score = 0.0
        ql = query.lower()
        tl = entry.get("title", "").lower()
        cl = entry.get("content", "").lower()
        tgl = " ".join(entry.get("tags", [])).lower()
        ctl = entry.get("category", "").lower()
        if ql in tl:
            score += 4.0
        for t in terms:
            if t and t in tl:
                score += 2.0
        # 逐条 fuzzy（无剪枝）
        best = 0.0
        for t in terms:
            if not t:
                continue
            if t in tl:
                best = max(best, 1.0)
            else:
                best = max(best, K.SequenceMatcher(None, tl, t).ratio() * 0.7)
        score += best * 2.0
        if ql in tgl:
            score += 3.0
        for t in terms:
            if t and t in tgl:
                score += 1.5
        if ql in ctl:
            score += 2.0
        for t in terms:
            if t and t in ctl:
                score += 1.0
        tfidf = 0.0
        for t in terms:
            tfidf += (1 + math.log(cl.count(t) + 1)) * math.log(total / max(df.get(t, 1), 1))
        score += tfidf * 1.5
        best2 = 0.0
        for t in terms:
            if not t:
                continue
            if t in cl:
                best2 = max(best2, 1.0)
            else:
                best2 = max(best2, K.SequenceMatcher(None, cl, t).ratio() * 0.7)
        score += best2
        if ql in cl:
            score += 2.0
        if ql in tl:
            score += 3.0
        if score > 0:
            results.append((score, entry))
    results.sort(key=lambda x: -x[0])
    return results[:max_results]


def main() -> None:
    as_json = "--json" in sys.argv
    report: dict = {}

    t0 = time.perf_counter()
    store = K.KnowledgeStore()
    report["load_s"] = round(time.perf_counter() - t0, 4)
    report["n_docs"] = len(store._data)

    # 索引构建成本（一次性）
    t = time.perf_counter()
    store._index_version = -1
    store._ensure_index()
    report["index_build_s"] = round(time.perf_counter() - t, 4)

    # 改造前 vs 改造后端到端（keyword 模式）
    legacy_times, new_times = {}, {}
    for q in QUERIES:
        ts = []
        for _ in range(3):
            t = time.perf_counter()
            legacy_pipeline(store, q)
            ts.append(time.perf_counter() - t)
        ts.sort()
        legacy_times[q] = round(ts[1], 4)

        ts = []
        for _ in range(3):
            t = time.perf_counter()
            store.search(q, 5, mode="keyword")
            ts.append(time.perf_counter() - t)
        ts.sort()
        new_times[q] = round(ts[1], 4)

    report["legacy_keyword_s"] = legacy_times
    report["new_keyword_s"] = new_times

    # SequenceMatcher 调用次数对比
    q = QUERIES[0]
    _SM_CALLS["n"] = 0
    _install_counter()
    try:
        legacy_pipeline(store, q)
    finally:
        _remove_counter()
    legacy_calls = _SM_CALLS["n"]

    _SM_CALLS["n"] = 0
    _install_counter()
    try:
        store.search(q, 5, mode="keyword")
    finally:
        _remove_counter()
    new_calls = _SM_CALLS["n"]

    report["seqmatcher_calls"] = {
        "legacy": legacy_calls,
        "new": new_calls,
        "reduction_pct": round((1 - new_calls / legacy_calls) * 100, 1) if legacy_calls else 0.0,
    }

    # 语义稳态
    sem = {}
    for q in QUERIES[:2]:
        try:
            t = time.perf_counter()
            store.search(q, 5, mode="semantic")
            sem[q] = round(time.perf_counter() - t, 4)
        except Exception as exc:  # noqa: BLE001
            sem[q] = f"error: {exc}"
    report["semantic_warm_s"] = sem
    report["vector_cache"] = len(K._semantic_engine._vector_cache)

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 62)
    print("knowledge 检索基准 v2 — T2795 5.1 两阶段检索")
    print("=" * 62)
    print(f"文档数 / 加载 / 索引构建 : {report['n_docs']} / "
          f"{report['load_s']:.4f}s / {report['index_build_s']:.4f}s")
    print("-" * 62)
    print(f"{'查询':<22}{'改造前':>10}{'改造后':>10}{'加速':>10}")
    for q in QUERIES:
        a, b = legacy_times[q], new_times[q]
        speed = f"{a / b:.1f}x" if b else "-"
        print(f"{q:<22}{a:>9.4f}s{b:>9.4f}s{speed:>10}")
    print("-" * 62)
    sc = report["seqmatcher_calls"]
    print(f"SequenceMatcher 调用 : {sc['legacy']} → {sc['new']} "
          f"(-{sc['reduction_pct']}%)")
    print("-" * 62)
    print("语义检索（warm）:")
    for q, v in sem.items():
        print(f"  {v}  {q}")
    print(f"向量缓存条目 : {report['vector_cache']}")
    print("=" * 62)


if __name__ == "__main__":
    main()
