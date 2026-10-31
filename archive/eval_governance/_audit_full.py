"""工具集完整性分级审计（读取 monitor_data.json）"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import agent1

raw = json.loads((ROOT / "memory" / "monitor_data.json").read_text(encoding="utf-8"))
# 兼容多种结构
stats = raw.get("tools") or raw.get("tool_stats") or {}
def count_of(name):
    e = stats.get(name)
    if isinstance(e, dict):
        for k in ("count", "calls", "total_calls"):
            if k in e:
                return int(e[k])
        return 0
    if isinstance(e, (int, float)):
        return int(e)
    return 0

rows = []
for t in agent1.ALL_TOOLS:
    n = t.get("function", {}).get("name", "")
    rows.append((n, count_of(n), len(json.dumps(t, ensure_ascii=False))))
rows.sort(key=lambda r: -r[1])

total = sum(r[2] for r in rows)
TEN = [r for r in rows if r[1] >= 20]
MID = [r for r in rows if 3 <= r[1] < 20]
LOW = [r for r in rows if 1 <= r[1] < 3]
ZERO = [r for r in rows if r[1] == 0]

def summarize(label, group):
    sz = sum(r[2] for r in group)
    print(f"{label:12} {len(group):>3} 个 | {sz:>6} 字符 ≈ {sz//3:>5} tokens | "
          f"占总量 {sz/total*100:5.1f}%")

print(f"42 工具 schema 总计 {total} 字符 ≈ {total//3} tokens\n")
print("分级（按调用次数）:")
summarize("高频 ≥20", TEN)
summarize("中频 3-19", MID)
summarize("低频 1-2", LOW)
summarize("零调用", ZERO)

print("\n【A 级 保留常驻（≥20 次）】")
for n, c, s in TEN:
    print(f"  {n:<20} {c:>4}次  {s:>5}字符")
print(f"  → 小计 {sum(r[2] for r in TEN)//3} tokens，占全量 {sum(r[2] for r in TEN)/total*100:.1f}%")

print("\n【B 级 保留但延迟加载（3-19 次）】")
for n, c, s in MID:
    print(f"  {n:<20} {c:>4}次  {s:>5}字符")

print("\n【C 级 候选删除/合并（≤2 次）】")
for n, c, s in LOW + ZERO:
    print(f"  {n:<20} {c:>4}次  {s:>5}字符")
