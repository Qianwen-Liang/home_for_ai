import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_router import federated_search, _select_sources, rewrite_query
from tools.search_sources import (ALL_SOURCES, GitHubSource, HuggingFaceSource,
                                  StackOverflowSource, WikipediaSource, _simplify_query)

for q in ["tool search progressive discovery agent context",
          "context compaction agent memory long running"]:
    print("=" * 74)
    print("Q:", q)
    print("  _simplify_query(3):", _simplify_query(q, 3))
    print("  _simplify_query(2):", _simplify_query(q, 2))
    scores = [(s.name, round(s.match_score(q), 2)) for s in ALL_SOURCES]
    print("  trigger 命中:", [(n, sc) for n, sc in scores if sc > 0] or "无")
    sel = _select_sources(q, 3, exclude_slow=True)
    print("  fast 选中源:", [s.name for s in sel])
    print("  冷却状态: GitHub剩余 %.0fs" % max(0, GitHubSource._cooldown_until - __import__("time").time()))

    # 逐个源实测
    for cls in [GitHubSource, HuggingFaceSource, StackOverflowSource, WikipediaSource]:
        try:
            h = cls().search(q, 2)
            print(f"    {cls.name:14} -> {len(h)} 条")
        except Exception as e:
            print(f"    {cls.name:14} -> {type(e).__name__}: {str(e)[:60]}")
    print()
