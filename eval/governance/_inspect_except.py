from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
lines = (ROOT / "agent1.py").read_text(encoding="utf-8").splitlines()
start = next(i for i, l in enumerate(lines) if l.strip().startswith("except (") and i > 900)
print("except 块起始:", start + 1)
for j in range(start - 2, min(start + 34, len(lines))):
    print(f"{j+1:5}| {lines[j]}")
