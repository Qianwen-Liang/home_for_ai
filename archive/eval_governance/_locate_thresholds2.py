import re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
PAT = re.compile(r"(MAX_FILE_BYTES|FULL_TEXT_LIMIT|MAX_OUTPUT_CHARS|LARGE_CHARS|budget_chars)\s*[:=]\s*([\d_]+)")
for f in ["core/read.py", "tools/runner.py", "tools/middleware.py", "tools/registry.py"]:
    p = ROOT / f
    s = p.read_text(encoding="utf-8")
    for m in PAT.finditer(s):
        line = s[:m.start()].count("\n") + 1
        print(f"{f:24} L{line:<4} {m.group(1):20} = {m.group(2)}")
