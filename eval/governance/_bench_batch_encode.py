"""5.1 工程实测：批量编码 vs 逐条编码（决定方案可行性）"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools import knowledge_store as ks

print("预热模型...")
ks._semantic_engine._ensure_model()
model = ks._SEMANTIC_MODEL
print("模型:", type(model).__name__)

data = list(ks._store._data.values())
texts = [f"{e.get('title','')} {e.get('content','')}" for e in data[:64]]
print(f"样本数: {len(texts)}\n")

# 1) 逐条编码
t0 = time.time()
for t in texts[:16]:
    model.encode(t, show_progress_bar=False)
per_item = (time.time() - t0) / 16
print(f"逐条编码: {per_item*1000:.1f}ms/条 → 16 条 {(time.time()-t0)*1000:.0f}ms")

# 2) 批量编码
for bs in (8, 16, 32, 64):
    n = min(bs, len(texts))
    t0 = time.time()
    model.encode(texts[:n], batch_size=bs, show_progress_bar=False)
    el = time.time() - t0
    print(f"批量编码 batch_size={bs:2d}, {n:2d} 条: {el*1000:6.0f}ms → {el/n*1000:5.1f}ms/条")

# 3) 全量批量（模拟重建索引）
t0 = time.time()
model.encode(texts, batch_size=32, show_progress_bar=False)
el = time.time() - t0
print(f"\n全量 64 条批量(batch=32): {el*1000:.0f}ms → {el/64*1000:.1f}ms/条")
print(f"推算 224 条: {el/64*224*1000:.0f}ms")

# 4) 纯相似度计算成本（numpy）
import numpy as np
v = np.random.rand(224, 384).astype("float32")
q = np.random.rand(384).astype("float32")
t0 = time.time()
for _ in range(100):
    _ = v @ q
print(f"\n纯向量相似度(224×384) @ 100 次: {(time.time()-t0)*1000:.1f}ms → 单次 {(time.time()-t0)*10:.2f}ms")

# 5) 关键词预筛成本（模拟）
t0 = time.time()
_ = [t for t in texts if "deepseek" in t.lower()]
print(f"关键词过滤 64 条: {(time.time()-t0)*1000:.2f}ms")
