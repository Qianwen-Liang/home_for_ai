"""合并分批评测结果 + 与基线对比 + 分项诊断"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def load_parts(mode_prefix="full"):
    # 明确取最新的两批分段（避免历史分批文件重复计入）
    names = ["part_full_0_14.json", "part_full_14_28.json"]
    parts = [BASE / n for n in names if (BASE / n).is_file()]
    if not parts:
        parts = sorted(BASE.glob(f"part_{mode_prefix}_*.json"))
    if not parts:
        return None
    allq = []
    for p in parts:
        d = json.loads(p.read_text(encoding="utf-8"))
        allq.extend(d["per_query"])
    allq.sort(key=lambda q: q["id"])
    n = len(allq) or 1
    return {"queries": n,
            "P@k": round(sum(q["p@k"] for q in allq) / n, 4),
            "Noise@k": round(sum(q["noise@k"] for q in allq) / n, 4),
            "MRR": round(sum(q["mrr"] for q in allq) / n, 4),
            "Hit@k": round(sum(1 for q in allq if q["mrr"] > 0) / n, 4),
            "avg_ms": round(sum(q["ms"] for q in allq) / n),
            "errors": sum(1 for q in allq if q["err"])}, allq

cur, allq = load_parts("full")
if not cur:
    print("无可合并的分批结果")
    raise SystemExit(1)

bl = json.loads((BASE / "baseline_bing.json").read_text(encoding="utf-8"))["agg"]

print("=" * 70)
print("完整对比：Bing 基线 vs 联邦检索（28 查询）")
print("=" * 70)
print(f"{'指标':<12}{'Bing':>10}{'联邦':>10}{'变化':>12}{'结论':>6}")
for key, higher_better in [("P@k", True), ("Noise@k", False), ("MRR", True), ("Hit@k", True)]:
    b, n = bl.get(key, 0), cur.get(key, 0)
    d = n - b
    ok = (d > 0) if higher_better else (d < 0)
    rel = (d / b * 100) if b else 0
    print(f"{key:<12}{b:>10.3f}{n:>10.3f}{d:>+11.3f}{'✅' if ok else '❌':>6}  ({rel:+.0f}%)")
print(f"{'avg_ms':<12}{bl.get('avg_ms',0):>10}{cur['avg_ms']:>10}"
      f"{cur['avg_ms']-bl.get('avg_ms',0):>+11}      ({cur['avg_ms']/max(bl.get('avg_ms',1),1):.1f}x)")

print("\n" + "=" * 70)
print("仍未完美的查询（Hit@5 未命中）")
print("=" * 70)
miss = [q for q in allq if q["mrr"] == 0]
if miss:
    for q in miss:
        print(f"  [{q['id']}] {q['query'][:50]:52} n={q['n']} P@5={q['p@k']:.2f}")
else:
    print("  全部命中")

(BASE / "final_comparison.json").write_text(json.dumps(
    {"baseline": bl, "federated": cur, "missed": miss}, ensure_ascii=False, indent=2),
    encoding="utf-8")
print(f"\n已写入 {BASE/'final_comparison.json'}")
