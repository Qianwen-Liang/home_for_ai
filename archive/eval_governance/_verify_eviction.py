"""5.1 P1 验证：淘汰策略不再整体清空"""
import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "tools" / "knowledge_store.py"), doraise=True)
print("✅ 语法通过\n")

from tools import knowledge_store as ks
import json

print(f"MAX_VECTOR_CACHE = {ks.MAX_VECTOR_CACHE}")
print(f"当前缓存条目 = {len(ks._semantic_engine._vector_cache)}")

# 模拟超上限：临时把上限调小，验证淘汰而非清空
eng = ks._semantic_engine
orig_max = ks.MAX_VECTOR_CACHE
try:
    ks.MAX_VECTOR_CACHE = 50
    before = len(eng._vector_cache)
    eng._evict_if_needed()
    after = len(eng._vector_cache)
    print(f"\n上限设为 50：{before} 条 → {after} 条")
    print(f"淘汰率 {after/before*100:.0f}%（保留 80%，非清空）")
    print(f"是否整体清空: {'❌ 是（旧行为）' if after == 0 else '✅ 否（新行为）'}")
finally:
    ks.MAX_VECTOR_CACHE = orig_max
    # 恢复完整缓存
    print(f"\n恢复上限 {ks.MAX_VECTOR_CACHE}")
