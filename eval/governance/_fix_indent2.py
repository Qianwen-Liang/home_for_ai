"""修复 _legacy_dispatch 函数体缩进（8 -> 4 空格）"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
p = ROOT / "agent1.py"
lines = p.read_text(encoding="utf-8").splitlines()

start = next(i for i, l in enumerate(lines) if l.startswith("def _legacy_dispatch("))
body_start = start + 2          # 跳过 def 行与单行 docstring
body_end = next(i for i in range(body_start, len(lines))
                if lines[i].strip() == "return None")

fixed = 0
for i in range(body_start, body_end):
    l = lines[i]
    if l.startswith("        "):
        lines[i] = l[4:]
        fixed += 1

p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"✅ 修复 {fixed} 行；函数体 {body_start + 1}~{body_end + 1}")

import py_compile
try:
    py_compile.compile(str(p), doraise=True)
    print("✅ 语法通过")
except py_compile.PyCompileError as e:
    print("❌", str(e)[:400])
