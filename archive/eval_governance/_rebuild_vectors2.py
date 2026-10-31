"""5.1 重建向量索引（用统一 _entry_search_text + 稳定 hash）"""
import sys, time, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools import knowledge_store as ks

eng = ks._semantic_engine
eng._ensure_model()
print("模型就绪:", eng.is_model_ready())

# 清空旧缓存（两套规则混存，全部作废）
eng._vector_cache = {}
eng._save_cache()
print("旧缓存已清空")

data = list(ks._store._data.values())
texts = [ks._entry_search_text(e) for e in data]
print(f"条目 {len(data)}，唯一文本 {len(set(texts))}")

model = ks._SEMANTIC_MODEL
t0 = time.time()
vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
el = time.time() - t0
print(f"批量编码: {el*1000:.0f}ms ({el/len(texts)*1000:.1f}ms/条)")

for txt, vec in zip(texts, vecs):
    eng._vector_cache[f"v_{hashlib.md5(txt.encode('utf-8')).hexdigest()}"] = (
        vec.tolist() if hasattr(vec, "tolist") else list(vec))
eng._save_cache()
print(f"缓存写入: {len(eng._vector_cache)} 条 → {ks.VECTOR_CACHE_FILE.name}")

# 立即校验：search 用的 key 是否能命中
sample = texts[0]
key = f"v_{hashlib.md5(sample.encode('utf-8')).hexdigest()}"
print(f"首条 key 命中: {key in eng._vector_cache}")
