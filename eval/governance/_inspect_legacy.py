from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
lines = (ROOT / "agent1.py").read_text(encoding="utf-8").splitlines()
start = next((i for i, l in enumerate(lines) if l.startswith("def _legacy_dispatch(")), None)
print("def 行:", start + 1 if start is not None else "未找到")
if start is not None:
    for j in range(max(0, start - 6), min(start + 14, len(lines))):
        print(f"{j+1:5}|{lines[j]!r}")
