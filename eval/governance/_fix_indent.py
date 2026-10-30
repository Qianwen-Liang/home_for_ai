"""修复 _legacy_dispatch 函数体缩进（减少 4 空格）"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
p = ROOT / "agent1.py"
lines = p.read_text(encoding="utf-8").splitlines()

# 定位函数体范围
start = None
for i, l in enumerate(lines):
    if l.startswith("def _legacy_dispatch("):
        start = i
        break
assert start is not None, "未找到 _legacy_dispatch"

# 函数体从 start+2（docstring 之后）开始，到 "    return None" 结束
body_start = None
for i in range(start + 1, len(lines)):
    if lines[i].strip().startswith('"""') and not body_start:
        continue
    if lines[i].strip() == '"""旧 elif 分派链（兼容回退路径，保留全部历史分支）。"""':
        body_start = i + 1
        break
assert body_start is not None

body_end = None
for i in range(body_start, len(lines)):
    if lines[i].strip() == "return None":
        body_end = i
        break
assert body_end is not None

# 缩小 4 空格
fixed = 0
for i in range(body_start, body_end):
    l = lines[i]
    if l.startswith("    ") and l.strip():
        lines[i] = l[4:]
        fixed += 1
    elif not l.strip():
        lines[i] = ""

p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"✅ 已修复 {fixed} 行缩进")
print(f"   函数体范围: {body_start + 1} ~ {body_end + 1}")

# 语法校验
import py_compile
try:
    py_compile.compile(str(p), doraise=True)
    print("✅ 语法通过")
except py_compile.PyCompileError as e:
    print("❌ 语法错误:", str(e)[:300])
