import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

for f in ["tools/search_sources.py", "tools/search_router.py", "tools/web_search.py"]:
    py_compile.compile(str(ROOT / f), doraise=True)
print("✅ 语法校验通过\n")

from tools.search_router import federated_search, format_results

for q in ["reciprocal rank fusion RRF", "context engineering agents",
          "sentence-transformers CrossEncoder rerank python"]:
    print("=" * 70)
    r = federated_search(q, 4, use_cache=False)
    print(format_results(r)[:900])
