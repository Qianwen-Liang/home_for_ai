"""关键假设验证：向量缓存 key 是否跨进程稳定"""
import sys, subprocess, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# 1) 检查缓存 key 的实现
src = (ROOT / "tools" / "knowledge_store.py").read_text(encoding="utf-8")
import re
for m in re.finditer(r'cache_key\s*=\s*(.+)', src):
    print("缓存 key 生成:", m.group(1).strip())

# 2) 验证 Python hash() 的跨进程稳定性
code = 'print(hash("DeepSeek 架构 测试文本"))'
outs = []
for i in range(3):
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    outs.append(r.stdout.strip())
print("\n三个独立进程的 hash('DeepSeek 架构 测试文本'):")
for i, o in enumerate(outs, 1):
    print(f"  进程{i}: {o}")
print(f"是否稳定: {'✅ 稳定' if len(set(outs)) == 1 else '❌ 跨进程不稳定（缓存必然失效）'}")

# 3) 对照：稳定哈希
import hashlib
h = hashlib.md5("DeepSeek 架构 测试文本".encode()).hexdigest()
print(f"\n对照 md5（稳定）: {h}")

# 4) 检查缓存文件里有多少条目、是否与新进程 key 对得上
import json
cache_file = getattr(__import__("tools.knowledge_store", fromlist=["VECTOR_CACHE_FILE"]), "VECTOR_CACHE_FILE", None)
if cache_file and Path(cache_file).is_file():
    d = json.loads(Path(cache_file).read_text(encoding="utf-8"))
    keys = list(d.keys())[:5]
    print(f"\n磁盘缓存条目: {len(d)}")
    print(f"key 样例: {keys}")
    sample_key = keys[0] if keys else ""
    print(f"key 形状: {'hash 数字' if sample_key.startswith('v_') and sample_key[2:].lstrip('-').isdigit() else '其他'}")
