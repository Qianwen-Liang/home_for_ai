"""双模式对比：fast / deep / auto"""
import sys, json, time
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent))
sys.path.insert(0, str(BASE))

from tools.search_router import federated_search, _CACHE
from runner import load_queries, score_result

try:
    _CACHE._data.clear(); _CACHE._save()
except Exception:
    pass

qs = load_queries()[:10]   # 前 10 个查询（含最难的 T01-T03）
rows = []
for mode in ["fast", "deep", "auto"]:
    print(f"\n{'='*66}\n模式: {mode}\n{'='*66}")
    tot_ms = 0; p_sum = 0; modes_used = {}
    for spec in qs:
        t0 = time.time()
        r = federated_search(spec["query"], 5, mode=mode, use_cache=False)
        cost = (time.time() - t0) * 1000
        tot_ms += cost
        hits = r["hits"][:5]
        scores = [score_result(h, spec) for h in hits]
        p = (sum(1 for s in scores if s > 0) / len(scores)) if scores else 0.0
        p_sum += p
        modes_used[r["mode"]] = modes_used.get(r["mode"], 0) + 1
    n = len(qs)
    print(f"  P@5={p_sum/n:.3f} | 均耗时={tot_ms/n:.0f}ms | 实际模式分布={modes_used}")
    rows.append({"mode": mode, "P@5": round(p_sum/n, 3), "avg_ms": round(tot_ms/n),
                 "distribution": modes_used})

print("\n" + "=" * 66)
print("汇总")
print("=" * 66)
print(f"{'模式':<8}{'P@5':>8}{'均耗时':>10}{'模式分布':>26}")
for r in rows:
    print(f"{r['mode']:<8}{r['P@5']:>8.3f}{r['avg_ms']:>9}ms{str(r['distribution']):>26}")
(BASE / "double_mode_test.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
