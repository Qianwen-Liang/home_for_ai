import json, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
d = json.loads((BASE / "part_full_14_28.json").read_text(encoding="utf-8"))
print("失败查询：")
for q in d["per_query"]:
    if q["p@k"] < 0.8 or q["noise@k"] > 0:
        print(f"  [{q['id']}] {q['query'][:46]:48} P@5={q['p@k']:.2f} "
              f"Noise={q['noise@k']:.2f} MRR={q['mrr']:.2f} n={q['n']}")

# 复查这几个查询的实际结果
sys.path.insert(0, str(BASE.parent.parent))
sys.path.insert(0, str(BASE))
from tools.search_router import federated_search
from tools.search_sources import GitHubSource
from runner import load_queries, score_result

print("\nGitHub 熔断状态:", "冷却中" if __import__("time").time() < GitHubSource._cooldown_until else "正常")

qs = {q["id"]: q for q in load_queries()}
bad = [q["id"] for q in d["per_query"] if q["p@k"] < 0.8 or q["noise@k"] > 0][:3]
for qid in bad:
    spec = qs[qid]
    r = federated_search(spec["query"], 5, use_cache=False)
    print("=" * 68)
    print(f"[{qid}] {spec['query']}")
    print(f"  源: {r['sources_used']} | 错误: {r['errors']}")
    for h in r["hits"][:5]:
        sc = score_result(h, spec)
        flag = "✅" if sc >= 1 else ("🔴" if sc < 0 else "⚪")
        print(f"   {flag} {sc:+.1f} [{h['source']:12}] {h['title'][:58]}")
