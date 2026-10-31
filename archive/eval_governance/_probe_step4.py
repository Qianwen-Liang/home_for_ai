"""步骤4 本地现状盘点：错误类型 / 阈值分布 / 依赖"""
import sys, re, glob, importlib.util as iu
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

print("=" * 74)
print("1) 依赖盘点（错误/重试/预算相关）")
print("=" * 74)
for m in ["tenacity", "backoff", "retrying", "resilience", "tiktoken",
          "transformers", "jsonschema", "pydantic", "attrs"]:
    print(f"  {m:16} {'OK' if iu.find_spec(m) else '--'}")

print()
print("=" * 74)
print("2) 现有错误类型全量（按继承关系）")
print("=" * 74)
errs = {}
for f in glob.glob(str(ROOT / "tools" / "*.py")) + glob.glob(str(ROOT / "core" / "*.py")) + glob.glob(str(ROOT / "evolver" / "*.py")):
    src = open(f, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"class (\w*Error\w*)\((.*?)\):", src):
        errs.setdefault(m.group(1), set()).add(m.group(2).strip())
print(f"  共 {len(errs)} 种：")
for name, bases in sorted(errs.items()):
    print(f"    {name:32} <- {', '.join(sorted(bases))[:40]}")

print()
print("=" * 74)
print("3) agent1.py except 元组登记")
print("=" * 74)
a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")
m = re.search(r"except \((.*?)\) as exc:", a1, re.DOTALL)
if m:
    listed = [x.strip() for x in m.group(1).split(",") if x.strip()]
    print(f"  手工登记 {len(listed)} 个: {', '.join(listed)}")

print()
print("=" * 74)
print("4) 各工具现有上下文阈值（散落各处）")
print("=" * 74)
pats = [
    ("core/read.py", r"MAX_FILE_BYTES\s*=\s*([\d_]+)"),
    ("core/read.py", r"FULL_TEXT_LIMIT\s*=\s*([\d_]+)"),
    ("tools/runner.py", r"MAX_OUTPUT_CHARS\s*=\s*([\d_]+)"),
    ("tools/middleware.py", r"LARGE_CHARS\s*=\s*([\d_]+)"),
    ("tools/middleware.py", r"SLOW_MS\s*=\s*([\d_]+)"),
    ("tools/registry.py", r"budget_chars:\s*int\s*=\s*([\d_]+)"),
]
for f, p in pats:
    fp = ROOT / f
    if not fp.is_file():
        continue
    mm = re.search(p, fp.read_text(encoding="utf-8"))
    print(f"  {f:24} {p.split(chr(92))[0][:24]:26} = {mm.group(1) if mm else '未找到'}")
