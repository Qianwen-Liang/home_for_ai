from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
lines = (ROOT / "tools" / "knowledge_store.py").read_text(encoding="utf-8").splitlines()
print("=== L735-775（search 内语义计算）===")
for j in range(734, 775):
    print(f"{j+1:4}| {lines[j]}")
print("\n=== L820-845 ===")
for j in range(819, 845):
    print(f"{j+1:4}| {lines[j]}")
