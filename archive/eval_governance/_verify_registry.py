import sys, json, hashlib, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "tools" / "registry.py"), doraise=True)
py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过")

import agent1
from tools.registry import REGISTRY

print(f"\n注册表工具数: {len(REGISTRY)}")
print(f"ALL_TOOLS 工具数: {len(agent1.ALL_TOOLS)}")

a = REGISTRY.fingerprint(REGISTRY.names())
b = json.dumps(agent1.ALL_TOOLS, ensure_ascii=False, separators=(",", ":"))
print(f"\n注册表装配长度: {len(a)}")
print(f"ALL_TOOLS 长度 : {len(b)}")
print(f"逐字节一致: {a == b}")
print(f"sha256: {hashlib.sha256(a.encode()).hexdigest()}")
print(f"基线  : 080f15c10733ba632f6cc95ab26b4147879123c09307103db9781c6b9bd6f8d0")
print(f"依赖闭包: {'完整' if not REGISTRY.validate_dependencies() else REGISTRY.validate_dependencies()}")
print()
print(REGISTRY.describe())
