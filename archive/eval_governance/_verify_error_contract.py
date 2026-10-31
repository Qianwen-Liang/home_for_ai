"""4.2 验证：错误契约声明化 + 手工 except 元组消除"""
import sys, re, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过\n")

a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")

# 1) 手工 except 元组是否消除
m = re.search(r"except \(\s*\n\s*ReadToolError", a1)
print(f"手工 except 元组残留: {'是 ❌' if m else '否 ✅'}")
print(f"统一 except RuntimeError: {'✅' if 'except RuntimeError as exc:' in a1 else '❌'}")
print(f"错误契约映射存在: {'✅' if '_TOOL_ERROR_TYPES' in a1 else '❌'}")
print(f"错误分类调用: {'✅' if 'make_evidence' in a1 else '❌'}")

import agent1
from tools.registry import REGISTRY

print("\n── 各工具声明的错误契约 ──")
for name in REGISTRY.names():
    spec = REGISTRY.get(name)
    print(f"  {name:20} {[e.__name__ for e in spec.errors]}")

# 2) 实测：错误分类是否生效
from tools.errors import classify

def call(name, args):
    import json
    tc = {"id": f"e_{name}", "type": "function",
          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    return agent1.execute_model_tool_call(tc)

print("\n── 错误消息是否带类别+错误码（顺带修复 K1）──")
for n, a in [("read_file", {"path": "__nope__.txt"}),
             ("calculate", {"expression": "1/0"})]:
    try:
        _, _, r = call(n, a)
        print(f"  {n}: {r.strip()[:100]}")
    except Exception as e:
        print(f"  {n}: EXC {e}")
