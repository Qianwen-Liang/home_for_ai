"""5.1 诊断：knowledge 语义搜索瓶颈分解 + 依赖盘点"""
import sys, time, json, importlib.util as iu
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

print("=" * 74)
print("1) 向量检索相关依赖")
print("=" * 74)
for m in ["faiss", "hnswlib", "annoy", "nmslib", "scipy", "numpy",
          "sentence_transformers", "sklearn", "torch", "pynndescent"]:
    print(f"  {m:24} {'OK' if iu.find_spec(m) else '--'}")

print()
print("=" * 74)
print("2) 知识库规模")
print("=" * 74)
from tools import knowledge_store as ks
store = ks._store
data = getattr(store, "_data", {})
print(f"  条目数: {len(data)}")
if data:
    sample = next(iter(data.values()))
    print(f"  单条字段: {list(sample.keys())}")
    lens = [len(f"{e.get('title','')}{e.get('content','')}") for e in data.values()]
    lens.sort()
    print(f"  文本长度: min={lens[0]} 中位={lens[len(lens)//2]} max={lens[-1]} 总={sum(lens)}")

print()
print("=" * 74)
print("3) 向量缓存状态")
print("=" * 74)
vc = getattr(ks._semantic_engine, "_vector_cache", {})
print(f"  缓存向量数: {len(vc)}")
print(f"  缓存上限: {ks.MAX_VECTOR_CACHE}")
one = next(iter(vc.values())) if vc else None
print(f"  向量维度: {len(one) if one else '无'}")

print()
print("=" * 74)
print("4) 语义搜索耗时分解（模型已就绪时）")
print("=" * 74)
print("  预热模型...")
ks._semantic_engine._ensure_model()
print(f"  模型就绪: {ks._semantic_engine.is_model_ready()}")

# 4a) 单条 encode 耗时
t0 = time.time()
_ = ks._semantic_engine.encode("测试文本用于测量编码耗时 αβγ")
print(f"  单条 encode（首次，含缓存写入）: {(time.time()-t0)*1000:.1f}ms")

t0 = time.time()
_ = ks._semantic_engine.encode("测试文本用于测量编码耗时 αβγ")
print(f"  单条 encode（缓存命中）: {(time.time()-t0)*1000:.1f}ms")

# 4b) 全量 encode 耗时（模拟无缓存）
t0 = time.time()
cnt = 0
for e in list(data.values())[:20]:
    txt = f"{e.get('title','')} {e.get('content','')}"
    ks._semantic_engine.encode(txt)
    cnt += 1
elapsed = time.time() - t0
print(f"  20 条 encode: {elapsed*1000:.0f}ms → 单条均值 {elapsed/cnt*1000:.1f}ms")
print(f"  推算全量 {len(data)} 条: {elapsed/cnt*len(data)*1000:.0f}ms")

# 4c) 真实 search 耗时
t0 = time.time()
r = store.search("DeepSeek 架构", max_results=3, mode="auto")
print(f"  store.search(mode=auto): {(time.time()-t0)*1000:.0f}ms")
print(f"  返回前 60 字: {r[:60]}")
