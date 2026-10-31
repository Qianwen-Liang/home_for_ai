import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.search_router import federated_search
from tools.search_sources import _http_get

# 1) 看错误详情
for q in ["sentence-transformers CrossEncoder rerank python", "Model Context Protocol specification"]:
    r = federated_search(q, 5, use_cache=False)
    print("=" * 66)
    print("Q:", q)
    print("  sources_used:", r["sources_used"])
    print("  errors:", r["errors"])
    print("  raw:", r["raw_count"])

# 2) llms.txt 里 specification 路径的真实格式
print()
print("=" * 66)
print("llms.txt 中 specification 路径样本：")
txt = _http_get("https://modelcontextprotocol.io/llms.txt", accept="text/plain")
spec_lines = [l for l in txt.splitlines() if "/specification/" in l][:8]
for l in spec_lines:
    print("  ", l[:110])
print(f"\n  含 /specification/ 的行数: {sum(1 for l in txt.splitlines() if '/specification/' in l)}")
print(f"  含 /docs/ 的行数: {sum(1 for l in txt.splitlines() if '/docs/' in l)}")
