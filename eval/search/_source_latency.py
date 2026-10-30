"""各权威源延迟剖析"""
import sys, time
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent))

from tools.search_sources import ALL_SOURCES, FALLBACK_SOURCES

Q = "context engineering agents"
print(f"{'源':<16}{'耗时(ms)':>10}{'条数':>8}  状态")
print("-" * 52)
for s in ALL_SOURCES + FALLBACK_SOURCES:
    t0 = time.time()
    try:
        hits = s.search(Q, 3)
        ms = (time.time() - t0) * 1000
        print(f"{s.name:<16}{ms:>10.0f}{len(hits):>8}  {'OK' if hits else '空结果'}")
    except Exception as e:
        ms = (time.time() - t0) * 1000
        print(f"{s.name:<16}{ms:>10.0f}{'—':>8}  {type(e).__name__}: {str(e)[:40]}")
