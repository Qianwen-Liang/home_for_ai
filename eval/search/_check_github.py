import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_sources import GitHubSource, HuggingFaceSource

print("GitHub 冷却剩余: %.0fs" % max(0, GitHubSource._cooldown_until - time.time()))
for cls, name in [(GitHubSource, "GitHub"), (HuggingFaceSource, "HF")]:
    try:
        h = cls().search("reciprocal rank fusion RRF", 3)
        print(f"{name} 返回 {len(h)} 条")
        for x in h[:2]:
            print("   ", x.title[:60])
    except Exception as e:
        print(f"{name} 错误: {str(e)[:110]}")
