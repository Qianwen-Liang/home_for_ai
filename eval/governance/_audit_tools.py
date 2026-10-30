"""工具集审计：调用分布 + schema 成本 + 僵尸识别"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import agent1

# monitor 数据
mon = ROOT / "memory" / "monitor.json"
stats = {}
if mon.is_file():
    try:
        d = json.loads(mon.read_text(encoding="utf-8"))
        stats = d.get("tools", d) if isinstance(d, dict) else {}
    except Exception as e:
        print("monitor 读取失败:", e)

tools = agent1.ALL_TOOLS
rows = []
for t in tools:
    fn = t.get("function", {})
    name = fn.get("name", "")
    sz = len(json.dumps(t, ensure_ascii=False))
    c = 0
    if isinstance(stats, dict):
        e = stats.get(name)
        if isinstance(e, dict):
            c = e.get("count", e.get("calls", 0))
        elif isinstance(e, (int, float)):
            c = int(e)
    rows.append((name, c, sz))

rows.sort(key=lambda r: (-r[1], -r[2]))
total_sz = sum(r[2] for r in rows)
print(f"工具总数: {len(rows)} | schema 总计 {total_sz} 字符 ≈ {total_sz//3} tokens\n")
print(f"{'工具':<22}{'调用次数':>8}{'schema字符':>12}")
print("-" * 44)
for n, c, s in rows:
    tag = "" if c > 0 else "  ← 从未调用"
    print(f"{n:<22}{c:>8}{s:>12}{tag}")

zero = [r for r in rows if r[1] == 0]
low = [r for r in rows if 0 < r[1] <= 2]
print(f"\n统计：从未调用 {len(zero)} 个 | 调用≤2次 {len(low)} 个 | 合计 {len(zero)+len(low)}/{len(rows)} = {(len(zero)+len(low))/len(rows)*100:.0f}%")

core = [r for r in rows if r[1] >= 20]
core_sz = sum(r[2] for r in core)
print(f"高频(≥20次) {len(core)} 个，schema {core_sz} 字符 ≈ {core_sz//3} tokens")
