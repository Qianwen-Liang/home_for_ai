import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_sources import ArxivSource

queries = [
    'all:"tool retrieval" AND all:LLM',
    'all:"tool selection" AND all:agent',
    'all:"context compression" AND all:agent',
]
for q in queries:
    print("=" * 72)
    print("arXiv:", q)
    print("=" * 72)
    try:
        # ArxivSource.search 内部用 all:{clean}，这里直接给关键词
        src = ArxivSource()
        kw = q.replace('all:', '').replace('AND', ' ').replace('"', '')
        hits = src.search(kw, 3)
        for h in hits:
            print(f"  • {h.title[:88]}")
            print(f"    {h.url}")
            if h.snippet:
                print(f"    {h.snippet[:110]}")
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:90])
    print()
