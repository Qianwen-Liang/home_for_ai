import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_router import federated_search, format_results

QUERIES = [
    "hypothesis property based testing",
    "json schema validation python",
    "LLM tool function calling validation reliability",
]
for q in QUERIES:
    r = federated_search(q, 4, mode="auto", use_cache=False)
    print("=" * 74)
    print(format_results(r)[:1300])
