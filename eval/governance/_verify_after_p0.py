"""5.1 验证：P0 修复后跨进程缓存命中效果"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools import knowledge_store as ks

print("预热模型...")
ks._semantic_engine._ensure_model()
print("磁盘缓存条目:", len(getattr(ks._semantic_engine, "_vector_cache", {})))

t0 = time.time()
r = ks._store.search("DeepSeek 架构", max_results=3, mode="auto")
el = (time.time() - t0) * 1000
print(f"\n修复后 首次搜索: {el:.0f}ms   (修复前基线 9485ms)")

t0 = time.time()
ks._store.search("DeepSeek 架构", max_results=3, mode="auto")
print(f"修复后 第二次  : {(time.time()-t0)*1000:.0f}ms")

for q in ["缓存 设计", "错误契约", "架构治理"]:
    t0 = time.time()
    ks._store.search(q, max_results=3, mode="auto")
    print(f"  查询 {q!r:14}: {(time.time()-t0)*1000:6.0f}ms")

print(f"\n返回前 60 字: {r[:60]}")
print(f"加速比: {9485 / max(el, 1):.1f}x")
