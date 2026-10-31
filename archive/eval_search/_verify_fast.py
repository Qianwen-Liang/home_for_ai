import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.search_router import federated_search, format_results, _CACHE

# 清空缓存（含历史空结果）
try:
    _CACHE._data.clear(); _CACHE._save()
    print("缓存已清空\n")
except Exception as e:
    print("清缓存失败:", e)

for mode in ["fast", "deep", "auto"]:
    r = federated_search("reciprocal rank fusion RRF", 3, mode=mode, use_cache=False)
    print("=" * 66)
    print(format_results(r)[:700])
