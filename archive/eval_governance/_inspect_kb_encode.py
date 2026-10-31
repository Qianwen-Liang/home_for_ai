import re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
src = (ROOT / "tools" / "knowledge_store.py").read_text(encoding="utf-8")
lines = src.splitlines()

print("=== 所有 encode( 调用点 ===")
for i, l in enumerate(lines, 1):
    if "encode(" in l and "def encode" not in l:
        print(f"{i:4}| {l.strip()[:110]}")

print("\n=== search 中构造搜索文本的地方 ===")
for i, l in enumerate(lines, 1):
    if "search_text" in l or ("text" in l and "join" in l):
        print(f"{i:4}| {l.strip()[:110]}")

print("\n=== search 中调用语义引擎的位置 ===")
for i, l in enumerate(lines, 1):
    if "_semantic_engine" in l or "_semantic_engine.encode" in l:
        print(f"{i:4}| {l.strip()[:110]}")
