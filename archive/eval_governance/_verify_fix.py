import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_router import federated_search, format_results, _CACHE

try:
    _CACHE._data.clear(); _CACHE._save()
    print("缓存已清空\n")
except Exception:
    pass

for q in ["tool search progressive discovery agent context",
          "context compaction agent memory long running"]:
    r = federated_search(q, 4, mode="auto", use_cache=False)
    print("=" * 74)
    print(format_results(r)[:1500])
    print()
