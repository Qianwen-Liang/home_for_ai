import re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
p = ROOT / "core" / "read.py"
lines = p.read_text(encoding="utf-8").splitlines()
print("core/read.py 行数:", len(lines))
print("=" * 64)
for i, l in enumerate(lines):
    if re.search(r"(MAX_|LIMIT|100000|bytes|size|offset|limit)", l) and not l.strip().startswith("#"):
        print(f"{i+1:4}: {l.strip()[:110]}")
