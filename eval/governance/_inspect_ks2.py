import re
from pathlib import Path
p = Path(__file__).resolve().parent.parent.parent / "tools" / "knowledge_store.py"
lines = p.read_text(encoding="utf-8").splitlines()
print("总行数:", len(lines))
print("=" * 60)
for i, l in enumerate(lines):
    if re.search(r"(def search|def _ensure_model|def _lazy_ensure_semantic|_SEMANTIC_MODEL\s*=|SentenceTransformer\(|def execute_knowledge_tool)", l):
        print(f"{i+1:5}: {l.strip()[:110]}")
print("=" * 60)
# 打印 search 方法体
for i, l in enumerate(lines):
    if re.match(r"\s*def search\(self", l):
        print("--- search 方法 @", i + 1, "---")
        for j in range(i, min(i + 45, len(lines))):
            print(lines[j])
        break
