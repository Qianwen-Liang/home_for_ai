import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.web_search import _search_bing_rss, _search_duckduckgo_html, WebSearchError
from runner import parse_results, score_result, load_queries

qs = {q["id"]: q for q in load_queries()}
TESTS = ["T01", "T10", "T13", "T18"]

def probe(fn, label, qid, n):
    spec = qs[qid]
    try:
        rs = parse_results(fn(spec["query"], n))
    except WebSearchError as e:
        print(f"  {label:24} FAIL {e}")
        return None
    sc = [score_result(r, spec) for r in rs]
    good = sum(1 for s in sc if s >= 1)
    bad = sum(1 for s in sc if s < 0)
    print(f"  {label:24} 共{len(rs)}条 | 相关{good} 噪音{bad} | 最佳score={max(sc) if sc else 0:+.1f}")
    return rs, sc

for qid in TESTS:
    print("=" * 68)
    print(f"[{qid}] {qs[qid]['query']}")
    print("=" * 68)
    probe(_search_bing_rss, "Bing n=8", qid, 8)
    probe(_search_bing_rss, "Bing n=25(扩大召回)", qid, 25)
    probe(_search_duckduckgo_html, "DuckDuckGo n=8", qid, 8)
    # 查询改写实验：加领域约束
    spec = qs[qid]
    rw = spec["query"] + " anthropic llm paper"
    print(f"  改写后查询: {rw}")
    probe(_search_bing_rss, "Bing(改写) n=8", qid, 8) if False else None
    try:
        rs = parse_results(_search_bing_rss(rw, 8))
        sc = [score_result(r, spec) for r in rs]
        good = sum(1 for s in sc if s >= 1); bad = sum(1 for s in sc if s < 0)
        print(f"  {'Bing改写 n=8':24} 共{len(rs)}条 | 相关{good} 噪音{bad} | 最佳score={max(sc) if sc else 0:+.1f}")
    except WebSearchError as e:
        print("  改写 FAIL", e)
    print()
