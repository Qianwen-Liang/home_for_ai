"""评测新架构 federated_search，并与 Bing 基线对比。"""
import sys, json, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent))
sys.path.insert(0, str(BASE))

from tools.search_router import federated_search
from runner import load_queries, score_result


def eval_federated(mode: str = "full", k: int = 5, start: int = 0, end: int | None = None) -> dict:
    """mode: full=全功能 / no_rewrite / no_noise_filter / no_cache"""
    qs = load_queries()[start:end]
    per, t_total = [], 0.0
    for spec in qs:
        kw = {}
        if mode == "no_rewrite":
            kw["use_rewrite"] = False
        if mode == "no_noise_filter":
            kw["drop_noise"] = False
        t0 = time.time()
        try:
            res = federated_search(spec["query"], k, use_cache=False, **kw)
            hits = res["hits"]
            err = ""
        except Exception as e:  # noqa: BLE001
            hits, err = [], f"{type(e).__name__}: {e}"
        cost = time.time() - t0
        t_total += cost

        scores = [score_result(h, spec) for h in hits[:k]]
        top = scores[:k]
        p = (sum(1 for s in top if s > 0) / len(top)) if top else 0.0
        nz = (sum(1 for s in top if s < 0) / len(top)) if top else 0.0
        mrr = next((1.0 / i for i, s in enumerate(scores, 1) if s >= 1.0), 0.0)
        per.append({"id": spec["id"], "query": spec["query"], "p@k": round(p, 3),
                    "noise@k": round(nz, 3), "mrr": round(mrr, 3),
                    "ms": round(cost * 1000), "err": err, "n": len(hits)})

    n = len(per) or 1
    return {"mode": mode, "agg": {
        "queries": n,
        "P@k": round(sum(q["p@k"] for q in per) / n, 4),
        "Noise@k": round(sum(q["noise@k"] for q in per) / n, 4),
        "MRR": round(sum(q["mrr"] for q in per) / n, 4),
        "Hit@k": round(sum(1 for q in per if q["mrr"] > 0) / n, 4),
        "avg_ms": round(t_total / n * 1000),
        "errors": sum(1 for q in per if q["err"]),
    }, "per_query": per}


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else "full"
    start = int(args[1]) if len(args) > 1 else 0
    end = int(args[2]) if len(args) > 2 else None
    print(f"\n>>> 评测模式: {mode} | 查询范围: [{start}, {end})")
    r = eval_federated(mode, start=start, end=end)
    a = r["agg"]
    print(f"  P@5={a['P@k']:.3f} Noise@5={a['Noise@k']:.3f} MRR={a['MRR']:.3f} "
          f"Hit@5={a['Hit@k']:.3f} 均耗时={a['avg_ms']}ms 错误={a['errors']}")
    tag = f"{mode}_{start}_{end if end is not None else 'all'}"
    (BASE / f"part_{tag}.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"分批结果已写入 part_{tag}.json")
