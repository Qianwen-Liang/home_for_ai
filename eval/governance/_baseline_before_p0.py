"""5.1 P0 基线：修复前耗时（跨进程，缓存应无法命中）"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools import knowledge_store as ks

print("预热模型...")
ks._semantic_engine._ensure_model()
print("模型就绪:", ks._semantic_engine.is_model_ready())
print("磁盘缓存条目:", len(getattr(ks._semantic_engine, "_vector_cache", {})))

t0 = time.time()
r = ks._store.search("DeepSeek 架构", max_results=3, mode="auto")
el = (time.time() - t0) * 1000
print(f"\n修复前 store.search(mode=auto): {el:.0f}ms")

t0 = time.time()
r2 = ks._store.search("DeepSeek 架构", max_results=3, mode="auto")
el2 = (time.time() - t0) * 1000
print(f"修复前 同进程第二次: {el2:.0f}ms")
print(f"\n返回前 70 字: {r[:70]}")
