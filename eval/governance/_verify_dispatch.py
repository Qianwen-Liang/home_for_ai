import sys, json, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过")

import agent1
from tools.registry import REGISTRY

print(f"\n工具数: {len(agent1.ALL_TOOLS)} | 注册表: {len(REGISTRY)}")
print(f"主路径开关 _USE_REGISTRY_DISPATCH: {agent1._USE_REGISTRY_DISPATCH}")
print(f"legacy 兼容函数存在: {callable(getattr(agent1, '_legacy_dispatch', None))}")

def call(name, args):
    tc = {"id": f"t_{name}", "type": "function",
          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    return agent1.execute_model_tool_call(tc)

print("\n── 主路径（注册表查表）──")
for n, a in [("calculate", {"expression": "2+3"}),
             ("read_file", {"path": "README.md"}),
             ("list_directory", {"path": "."})]:
    try:
        _, _, r = call(n, a)
        print(f"  {n:16} -> {r.strip()[:60]}")
    except Exception as e:
        print(f"  {n:16} -> EXC {type(e).__name__}: {e}")

print("\n── 未知工具提示 ──")
try:
    _, _, r = call("nonexistent_tool", {})
    print(f"  -> {r.strip()[:90]}")
except Exception as e:
    print(f"  -> EXC {type(e).__name__}: {e}")

print("\n── 回退路径（legacy elif 链）──")
agent1._USE_REGISTRY_DISPATCH = False
try:
    _, _, r = call("calculate", {"expression": "7*6"})
    print(f"  legacy calculate -> {r.strip()[:60]}")
except Exception as e:
    print(f"  legacy -> EXC {type(e).__name__}: {e}")
finally:
    agent1._USE_REGISTRY_DISPATCH = True
print("\n开关已恢复为", agent1._USE_REGISTRY_DISPATCH)
