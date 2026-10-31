"""5.1 P1：重建向量索引（批量编码 + 稳定 key 持久化）"""
import sys, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools import knowledge_store as ks

eng = ks._semantic_engine
print("预热模型...")
eng._ensure_model()
print("模型就绪:", eng.is_model_ready())

# 清理旧格式（v_<数字>）缓存：稳定 key 为 32 位十六进制
old = dict(eng._vector_cache)
kept = {k: v for k, v in old.items() if k.startswith("v_") and len(k) == 34
        and all(c in "0123456789abcdef" for c in k[2:])}
print(f"旧缓存 {len(old)} 条 → 保留稳定 key 格式 {len(kept)} 条，清理 {len(old) - len(kept)} 条")
eng._vector_cache = kept

data = list(ks._store._data.values())
print(f"知识条目: {len(data)}")

# 构造与 search 一致的文本
def text_of(e):
    return (f"{e.get('title','')} {e.get('content','')} "
            f"{e.get('category','')} {' '.join(e.get('tags') or [])}").strip()

texts = [text_of(e) for e in data]

# 批量编码（P3：重建时用大 batch）
model = ks._SEMANTIC_MODEL
t0 = time.time()
vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
el = time.time() - t0
print(f"批量编码 {len(texts)} 条: {el*1000:.0f}ms → {el/len(texts)*1000:.1f}ms/条")

# 写入缓存（稳定 key）
import hashlib
n_new = 0
for txt, vec in zip(texts, vecs):
    key = f"v_{hashlib.md5(txt.encode('utf-8')).hexdigest()}"
    if key not in eng._vector_cache:
        n_new += 1
    eng._vector_cache[key] = vec.tolist() if hasattr(vec, "tolist") else list(vec)
eng._save_cache()
print(f"写入缓存: 新增 {n_new} 条，总计 {len(eng._vector_cache)} 条")
print(f"缓存文件: {ks.VECTOR_CACHE_FILE}")
