import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.web_search import _search_bing_rss
from runner import parse_results, score_result, load_queries

qs = {q["id"]: q for q in load_queries()}
for qid in ["T01", "T10", "T13", "T18"]:
    spec = qs[qid]
    print("=" * 70)
    print(f"[{qid}] {spec['query']}")
    print("=" * 70)
    try:
        raw = _search_bing_rss(spec["query"], 6)
        rs = parse_results(raw)
        for i, r in enumerate(rs, 1):
            sc = score_result(r, spec)
            flag = "✅" if sc >= 1 else ("🔴噪声" if sc < 0 else "⚪无关")
            print(f" {i}. {flag} score={sc:+.1f} | {r['title'][:60]}")
            print(f"    {r['url'][:88]}")
    except Exception as e:
        print("FAIL:", e)
    print()
