import sys, json, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ agent1.py 语法通过")

import agent1
tools = agent1.ALL_TOOLS
sz = len(json.dumps(tools, ensure_ascii=False))
names = [t.get("function", {}).get("name", "") for t in tools]
print(f"\nP0 后工具数: {len(tools)}")
print(f"schema: {sz} 字符 ≈ {sz//3} tokens")
orig_sz = 39764
print(f"原始: {orig_sz} 字符 ≈ {orig_sz//3} tokens")
print(f"节省: {(orig_sz-sz)/orig_sz*100:.1f}%")
print(f"\n保留工具: {', '.join(names)}")
print(f"移出注册: {len(agent1.LEGACY_TOOLS)} 个")

# 生成 legacy 映射表
mapping = {
    "_doc": "P0 工具集收敛映射表。这些工具代码保留在 tools/，仅移出 ALL_TOOLS 注册表。",
    "generated": "2026-10-30",
    "plan": "eval/governance/ARCHITECTURE_PLAN.md",
    "kept_count": len(tools),
    "kept": names,
    "legacy": sorted(agent1.LEGACY_TOOLS),
    "restore_hint": "把对应 TOOL_DEFINITION 重新加入 agent1.py 的 ALL_TOOLS 元组即可恢复",
    "schema_before": orig_sz,
    "schema_after": sz,
    "saving_pct": round((orig_sz - sz) / orig_sz * 100, 1),
}
out = ROOT / "eval" / "governance" / "legacy_tools.json"
out.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n映射表已写入 {out}")
