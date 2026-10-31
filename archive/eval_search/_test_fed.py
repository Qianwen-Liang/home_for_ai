import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.search_router import federated_search, format_results, _CACHE

# 清空缓存确保测的是新逻辑
try:
    _CACHE._data.clear()
    _CACHE._save()
except Exception:
    pass

for q in ["context engineering agents",
          "sentence-transformers CrossEncoder rerank python",
          "Model Context Protocol specification",
          "reciprocal rank fusion RRF",
          "检索增强生成 混合检索 BM25"]:
    print("=" * 72)
    r = federated_search(q, 5, use_cache=False)
    print(format_results(r)[:1200])
