from pathlib import Path
p = Path(__file__).resolve().parent.parent.parent / "tools" / "knowledge_store.py"
lines = p.read_text(encoding="utf-8").splitlines()
print("--- 40~80 行（_lazy_ensure_semantic）---")
for j in range(39, 80):
    print(j + 1, lines[j])
print("\n--- 235~300 行（_ensure_model / is_available）---")
for j in range(234, 300):
    print(j + 1, lines[j])
