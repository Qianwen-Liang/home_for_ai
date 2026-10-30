"""架构债量化：支撑「总领性 vs 逐模块」的路线判断"""
import re, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent

a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")

# 1) 工具分派分支数
elif_n = len(re.findall(r'elif name == "', a1))
if_n = len(re.findall(r'if name in \{', a1))
print(f"1) execute_model_tool_call 分派分支: elif={elif_n}, if-in-set={if_n}")

# 2) 工具自定义错误类型
errs = set()
for f in glob.glob(str(ROOT / "tools" / "*.py")):
    src = open(f, encoding="utf-8", errors="replace").read()
    errs.update(re.findall(r"class (\w*Error)\(RuntimeError\)", src))
print(f"2) 工具自定义错误类型: {len(errs)} 种")
print(f"   {sorted(errs)[:12]}{' ...' if len(errs) > 12 else ''}")

# 3) except 元组里登记的错误类型（逐个维护）
m = re.search(r"except \((.*?)\) as exc:", a1, re.DOTALL)
if m:
    listed = [x.strip() for x in m.group(1).split(",") if x.strip()]
    print(f"3) agent1.py 手工登记的错误类型: {len(listed)} 个（每加一个工具就要加一行）")

# 4) 埋点调用点
mon = len(re.findall(r"tool_monitor\._monitor\.record", a1))
print(f"4) monitor 手工埋点调用点: {mon} 处")

# 5) 工具文件数与模块规模
tfiles = glob.glob(str(ROOT / "tools" / "*.py"))
tlines = sum(len(open(f, encoding="utf-8", errors="replace").read().splitlines()) for f in tfiles)
print(f"5) tools/ 模块: {len(tfiles)} 个文件 / {tlines} 行")

# 6) self_check 覆盖 vs 实际工具
print(f"6) 实际工具 16 个；self_check 覆盖模块数需另行核对（此前实测 20 项含重复）")
