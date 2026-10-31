import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FILES = ["agent1.py", "core/read.py", "tools/knowledge_store.py",
         "tools/runner.py", "tools/capsule.py"]
for f in FILES:
    py_compile.compile(str(ROOT / f), doraise=True)
print("✅ 全部文件语法通过:", ", ".join(FILES))

import agent1, json
print(f"\n工具数: {len(agent1.ALL_TOOLS)}")
print(f"schema: {len(json.dumps(agent1.ALL_TOOLS, ensure_ascii=False))} 字符 ≈ {len(json.dumps(agent1.ALL_TOOLS, ensure_ascii=False))//3} tokens")
print(f"SYSTEM_PROMPT: {len(agent1.SYSTEM_PROMPT)} 字符")
print(f"legacy: {len(agent1.LEGACY_TOOLS)} 个")
print(f"capsule 协议已注入: {'长任务上下文协议' in agent1.SYSTEM_PROMPT}")
