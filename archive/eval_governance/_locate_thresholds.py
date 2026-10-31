from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
for f in ["core/read.py", "tools/runner.py", "tools/middleware.py", "tools/registry.py"]:
    p = ROOT / f
    s = p.read_text(encoding="utf-8")
    print("===", f)
    for i, l in enumerate(s.splitlines()[:60], 1):
        t = l.strip()
        if ("MAX_" in t or "LIMIT" in t or "LARGE_CHARS" in t
                or "budget_chars" in t or "SLOW_MS" in t):
            print(f"  {i:3}| {t[:88]}")
