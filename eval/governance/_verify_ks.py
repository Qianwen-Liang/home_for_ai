"""验证 knowledge 冷启动降级 + 后台预热效果（全新进程）"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools import knowledge_store as ks

print("模型初始就绪:", ks._semantic_engine.is_model_ready())

t0 = time.time()
r1 = ks._store.search("DeepSeek 架构", max_results=3)
d1 = (time.time() - t0) * 1000
print(f"首次查询(auto): {d1:.0f}ms  模型就绪={ks._semantic_engine.is_model_ready()}")
print("  返回前 80 字:", r1[:80].replace("\n", " "))

t0 = time.time()
r2 = ks._store.search("搜索 架构", max_results=3)
d2 = (time.time() - t0) * 1000
print(f"二次查询(auto): {d2:.0f}ms")

print("\n等待后台预热（最多 60s）...")
for i in range(60):
    if ks._semantic_engine.is_model_ready():
        print(f"  模型就绪于第 {i+1}s")
        break
    time.sleep(1)
else:
    print("  60s 内未就绪")

t0 = time.time()
r3 = ks._store.search("DeepSeek 架构", max_results=3)
print(f"模型就绪后查询: {(time.time()-t0)*1000:.0f}ms (此时走语义混合)")
