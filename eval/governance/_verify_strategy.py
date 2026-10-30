import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
for f in ["tools/search_sources.py", "tools/search_router.py"]:
    py_compile.compile(str(ROOT / f), doraise=True)
print("✅ 语法通过\n")

from tools.search_router import federated_search, format_results, _CACHE
try:
    _CACHE._data.clear(); _CACHE._save()
except Exception:
    pass

for q in ["JIT tool schema injection token bloat reduction agent",
          "agent tool registry lazy loading MCP gateway",
          "context compaction agent memory long running"]:
    r = federated_search(q, 4, mode="auto", use_cache=False)
    print("=" * 76)
    print(format_results(r)[:1200])
    print()
