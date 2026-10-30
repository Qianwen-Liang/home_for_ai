import sys, json, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过")

import agent1
print(f"工具数: {len(agent1.ALL_TOOLS)}")
print(f"schema: {len(json.dumps(agent1.ALL_TOOLS, ensure_ascii=False))} 字符")
print(f"SYSTEM_PROMPT: {len(agent1.SYSTEM_PROMPT)} 字符 (原 2432)")
print(f"保留: {[t['function']['name'] for t in agent1.ALL_TOOLS]}")
print(f"移出: {len(agent1.LEGACY_TOOLS)} 个")

# 确认执行逻辑仍覆盖被移除的工具（保证可恢复）
src = (ROOT / "agent1.py").read_text(encoding="utf-8")
missing = [n for n in agent1.LEGACY_TOOLS
           if f'elif name == "{n}"' not in src]
print(f"\n执行逻辑仍保留的 legacy 工具数: {len(agent1.LEGACY_TOOLS) - len(missing)}/{len(agent1.LEGACY_TOOLS)}")
if missing:
    print(f"  缺失执行分支: {missing}")
