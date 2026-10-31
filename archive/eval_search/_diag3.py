import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.search_router import federated_search
from tools.search_sources import GitHubSource, _simplify_query, SourceError

q = "reciprocal rank fusion RRF"
print("简化查询:", _simplify_query(q, 3))
print("简化查询(2):", _simplify_query(q, 2))
print()

g = GitHubSource()
for probe in [q, _simplify_query(q, 3), _simplify_query(q, 2), "rag-fusion", "RRF"]:
    try:
        hits = g.search(probe, 3)
        print(f"[GitHub] query='{probe}' -> {len(hits)} hits")
        for h in hits[:2]:
            print("     ", h.title[:70])
    except SourceError as e:
        print(f"[GitHub] query='{probe}' -> SourceError: {e}")

print()
r = federated_search(q, 5, use_cache=False)
print("sources_used:", r["sources_used"])
print("errors:", r["errors"])
print("raw:", r["raw_count"])
for h in r["hits"][:5]:
    print(f"  [{h['source']}] {h['title'][:65]}")
