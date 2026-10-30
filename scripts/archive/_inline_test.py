"""_inline_test — 内联快速验证""" 
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
R = []

def check(name, condition, detail=""):
    s = "✅" if condition else "❌"
    R.append((name, condition))
    print(f"  {s} {name}" + (f" — {detail}" if detail else ""))

def _try(n):
    try: __import__(n); return True
    except: return False

print("=" * 50)
print("⚡ Agent 1 内联快速检查")
print("=" * 50)
for m in ["broken_tool", "tools.runner", "tools.offline_runner",
           "tools.checkpoint_manager", "tools.specialist_base"]:
    check(m, _try(m))
for d in ["tools", "tests", "memory", "knowledge", "logs"]:
    check(f"{d}/", os.path.isdir(d))
try:
    import py_compile; py_compile.compile("agent1.py", doraise=True)
    check("agent1.py 语法", True)
except: check("agent1.py 语法", False)
p = sum(1 for _, ok in R if ok)
print(f"\n📊 {p}/{len(R)} 通过" + (" ✅" if p == len(R) else " ❌"))
