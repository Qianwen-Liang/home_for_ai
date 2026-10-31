"""探测 16 个已注册工具的 schema 结构，作为契约规范设计依据"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import agent1

print(f"{'工具':<20}{'必填':<22}{'可选参数'}")
print("-" * 88)
for t in agent1.ALL_TOOLS:
    fn = t.get("function", {})
    name = fn.get("name", "")
    params = fn.get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    req = params.get("required", []) or []
    opt = [k for k in props if k not in req]
    types = {k: (v.get("type", "?") if isinstance(v, dict) else "?") for k, v in props.items()}
    print(f"{name:<20}{','.join(req)[:20]:<22}{','.join(opt)[:40]}")
    print(f"{'':20}types={types}")

print("\n工具总数:", len(agent1.ALL_TOOLS))
# 检测 schema 合规性（MCP 标准：name 1-128，只允许 A-Za-z0-9_-.）
import re
bad = [t["function"]["name"] for t in agent1.ALL_TOOLS
       if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,128}", t["function"]["name"])]
print("命名不合规:", bad or "无")
# 是否有 outputSchema / annotations
has_out = sum(1 for t in agent1.ALL_TOOLS if "outputSchema" in t.get("function", {}))
has_ann = sum(1 for t in agent1.ALL_TOOLS if "annotations" in t.get("function", {}))
print(f"含 outputSchema: {has_out}/{len(agent1.ALL_TOOLS)}；含 annotations: {has_ann}/{len(agent1.ALL_TOOLS)}")
