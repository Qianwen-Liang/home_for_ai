"""T2795 5.1 改造等价性校验。

把改造前的评审逻辑（legacy）完整内联到此，改造后逐条比对关键词分数，
要求**完全相等**（不只是 top-N 相同），确保性能优化不改变任何排序结果。

用法:
    python scripts/verify_knowledge_equiv.py
"""
from __future__ import annotations

import math
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.knowledge_store as K  # noqa: E402


# ── legacy 实现（改造前逐字复制，作为判决基准） ──────────────────


def legacy_best_fuzzy_score(text: str, query_terms: list[str]) -> float:
    if not query_terms or not text:
        return 0.0
    text_lower = text.lower()
    best = 0.0
    for term in query_terms:
        if not term:
            continue
        if term in text_lower:
            best = max(best, 1.0)
        else:
            score = SequenceMatcher(None, text_lower, term).ratio()
            best = max(best, score * 0.7)
    return best


def legacy_compute_tfidf(
    text: str, query_terms: list[str], total_docs: int, docs_with_term_counts: dict[str, int]
) -> float:
    score = 0.0
    for term in query_terms:
        tf = 1 + math.log(text.lower().count(term) + 1)
        idf = math.log(total_docs / max(docs_with_term_counts.get(term, 1), 1))
        score += tf * idf
    return score


def legacy_score_entry(
    entry: dict,
    query: str,
    query_terms: list[str],
    total_docs: int,
    docs_with_term_counts: dict[str, int],
) -> float:
    keyword_score = 0.0
    query_lower = query.lower()
    title = entry.get("title", "")
    content = entry.get("content", "")
    tags = " ".join(entry.get("tags", []))
    category = entry.get("category", "")

    title_lower = title.lower()
    if query_lower in title_lower:
        keyword_score += 4.0
    for term in query_terms:
        if term and term in title_lower:
            keyword_score += 2.0
    keyword_score += legacy_best_fuzzy_score(title, query_terms) * 2.0

    tags_lower = tags.lower()
    if query_lower in tags_lower:
        keyword_score += 3.0
    for term in query_terms:
        if term and term in tags_lower:
            keyword_score += 1.5

    category_lower = category.lower()
    if query_lower in category_lower:
        keyword_score += 2.0
    for term in query_terms:
        if term and term in category_lower:
            keyword_score += 1.0

    keyword_score += (
        legacy_compute_tfidf(content, query_terms, total_docs, docs_with_term_counts) * 1.5
    )
    keyword_score += legacy_best_fuzzy_score(content, query_terms) * 1.0

    if query_lower in content.lower():
        keyword_score += 2.0
    if query_lower in title_lower:
        keyword_score += 3.0
    return keyword_score


def legacy_idf(store: "K.KnowledgeStore", terms: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in terms:
        if not term:
            continue
        c = 0
        for entry in store._data.values():
            search_text = (
                f"{entry['title']} {entry['content']} "
                f"{entry['category']} {' '.join(entry['tags'])}"
            ).lower()
            if term in search_text:
                c += 1
        counts[term] = max(c, 1)
    return counts


QUERIES = [
    "缓存 优化 性能",
    "语义检索",
    "boundary 失效边界",
    "test runner",
    "如何设计契约测试",
    "AI",
    "不存在的词汇xyzzy",
]


def main() -> int:
    store = K.KnowledgeStore()
    se = K._search_enhancer
    total = len(store._data)
    entries = list(store._data.values())

    failures = 0
    checked = 0
    tol = 1e-12

    for query in QUERIES:
        terms = list(set(se.expand_query(query)))

        old_idf = legacy_idf(store, terms)
        new_idf = se.build_idf(terms, store._data) if hasattr(se, "build_idf") else old_idf

        for k in old_idf:
            if old_idf[k] != new_idf.get(k):
                print(f"[IDF MISMATCH] {query!r} term={k!r} old={old_idf[k]} new={new_idf.get(k)}")
                failures += 1

        for entry in entries:
            old = legacy_score_entry(entry, query, terms, total, old_idf)
            new, _ = se.score_entry(entry, query, terms, total, new_idf)
            checked += 1
            if abs(old - new) > tol:
                failures += 1
                if failures <= 10:
                    print(
                        f"[SCORE MISMATCH] q={query!r} id={entry.get('id')} "
                        f"old={old!r} new={new!r} diff={old - new!r}"
                    )

    # ── 端到端：改造后 store.search 的 top-N 是否与 legacy 排序一致 ──
    import re

    e2e_checked = 0
    for query in QUERIES:
        terms = list(set(se.expand_query(query)))
        old_idf = legacy_idf(store, terms)
        legacy_ranked = [
            (legacy_score_entry(e, query, terms, total, old_idf), e.get("id"))
            for e in entries
        ]
        legacy_ranked = [x for x in legacy_ranked if x[0] > 0]
        legacy_ranked.sort(key=lambda x: -x[0])
        legacy_ids = [x[1] for x in legacy_ranked[:10]]

        out = store.search(query, 10, mode="keyword")
        new_ids = re.findall(r"\[(K[0-9A-Za-z_]+)\]", out)
        e2e_checked += 1
        if new_ids[: len(legacy_ids)] != legacy_ids[: len(new_ids)]:
            failures += 1
            print(f"[E2E MISMATCH] q={query!r}")
            print(f"   legacy={legacy_ids}")
            print(f"   new   ={new_ids}")

    print("-" * 58)
    print(f"比对条目分值次数 : {checked}")
    print(f"端到端 top-10 查询: {e2e_checked}")
    print(f"不一致次数       : {failures}")
    print(f"判定             : {'✅ 完全等价' if failures == 0 else '❌ 存在差异'}")
    print("-" * 58)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
