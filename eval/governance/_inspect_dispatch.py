from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
lines = (ROOT / "agent1.py").read_text(encoding="utf-8").splitlines()
# 定位分派块
start = None
for i, l in enumerate(lines):
    if 'if name in {"read_file", "list_directory"}' in l:
        start = i
        break
if start is None:
    for i, l in enumerate(lines):
        if "if name in {" in l and "read_file" in l:
            start = i
            break
print("分派起点行:", start + 1 if start is not None else "未找到")
if start is not None:
    for j in range(start - 3, min(start + 90, len(lines))):
        print(f"{j+1:5}: {lines[j]}")
