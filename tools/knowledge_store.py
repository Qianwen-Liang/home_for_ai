"""
KnowledgeStore — 知识存储与检索系统（v4.0 认知类型版）
=====================================================
为智能体提供持久化的知识存储能力，支持分类、标签和全文检索。

v4.0 新增认知类型双轨制（借鉴 ReasFlow 知识卡片）：
  - kind 字段：declarative(事实) / procedural(方法) / boundary(失效边界)
  - semantic_tags 语义标签
  - 种子卡片自动导入（knowledge/seed_heuristics.json）

v3.0 新增语义搜索（基于 sentence-transformers）：
  - 语义向量检索：理解查询意图而非关键词匹配
  - 混合搜索模式：语义搜索 + TF-IDF + 模糊匹配 + 同义词
  - 自动向量缓存：首次使用时自动计算并缓存
  - jieba 中文分词改进：中文查询更准确

v2.0 已有功能：
  - TF-IDF 加权搜索
  - 模糊匹配（difflib）
  - 同义词扩展
  - 标题/标签加权
  - 综合评分排序
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = SANDBOX_DIR / "knowledge"
KNOWLEDGE_FILE = KNOWLEDGE_DIR / "knowledge_store.json"
VECTOR_CACHE_FILE = KNOWLEDGE_DIR / "vector_cache.json"

# 向量缓存容量护栏（步骤5.1：原为 300 且"满即清空"，会在知识库增长时
# 触发全量重建。改为按需淘汰 + 提高上限，避免灾难性抖动）
MAX_VECTOR_CACHE = 2_000

# 两阶段检索（★5.1）：Stage 1 廉价粗召回的候选上限。
# 取保守值，使中小规模知识库（当前 225 条）完全等价于全量精排，
# 只有库显著增长后粗筛才生效，避免检索延迟随库体积线性膨胀。
STAGE1_MIN_CANDIDATES = 300

# ── 可选导入：语义搜索依赖（惰性加载，避免 self_check 等场景的性能损耗）──

_SEMANTIC_AVAILABLE: bool | None = None  # None = 尚未检测
_SEMANTIC_MODEL = None


def _stable_hash(text: str) -> str:
    """稳定哈希（md5），用于向量缓存键。

    ★步骤 5.1 P0 根因修复：
    原实现使用内置 hash()，其对字符串的取值受 PYTHONHASHSEED 随机化影响，
    **跨进程不稳定**（实测三个独立进程对同一文本得到三个不同值），
    导致磁盘上持久化的向量缓存永远无法命中，每次运行都要全量重编码。
    """
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _entry_search_text(entry: dict) -> str:
    """构造条目用于向量化的**唯一**文本（单一事实来源）。

    ★步骤 5.1 第二层根因修复：
    原 search 与 rebuild 各自拼接文本且规则不一致——
    search 用 content[:500]、顺序为 title/content/tags/category；
    rebuild 用 content 全文、顺序为 title/content/category/tags。
    两套规则导致缓存键永不匹配，即使哈希稳定也无法命中。
    """
    tags = entry.get("tags") or []
    return (f"{entry.get('title', '')} {str(entry.get('content', ''))[:500]} "
            f"{' '.join(tags)} {entry.get('category', '')}")


def _lazy_ensure_semantic() -> bool:
    """惰性检测语义搜索依赖是否可用。仅在首次调用语义搜索功能时执行。"""
    global _SEMANTIC_AVAILABLE
    if _SEMANTIC_AVAILABLE is not None:
        return _SEMANTIC_AVAILABLE
    try:
        import numpy as _np
        from sentence_transformers import SentenceTransformer
        globals()["np"] = _np
        globals()["SentenceTransformer"] = SentenceTransformer
        _SEMANTIC_AVAILABLE = True
    except ImportError:
        _SEMANTIC_AVAILABLE = False
    return _SEMANTIC_AVAILABLE


_JP_AVAILABLE: bool | None = None


def _lazy_ensure_jieba() -> bool:
    """惰性检测 jieba 分词是否可用。"""
    global _JP_AVAILABLE
    if _JP_AVAILABLE is not None:
        return _JP_AVAILABLE
    try:
        import jieba
        globals()["jieba"] = jieba
        _JP_AVAILABLE = True
    except ImportError:
        _JP_AVAILABLE = False
    return _JP_AVAILABLE

# ── 错误类型 ──────────────────────────────────────────────


class KnowledgeStoreError(RuntimeError):
    """知识存储操作错误。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class KnowledgeEntry:
    """一条知识记录。"""

    id: str
    title: str
    content: str
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    source: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1
    # v4.0 新增：认知类型与语义标签（借鉴 ReasFlow 知识卡片双轨制）
    #   kind: declarative(是什么/事实) | procedural(怎么做/方法) | boundary(何时失效/边界)
    kind: str = "declarative"
    semantic_tags: list[str] = field(default_factory=list)


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "knowledge",
        "description": (
            "知识存储与检索系统。支持存储、查询、搜索知识条目。"
            "搜索支持语义向量检索、TF-IDF 加权、模糊匹配和同义词扩展。"
            "v3.0 新增语义搜索：理解查询意图而非仅关键词匹配。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "get", "search", "list", "delete", "archive", "stats", "reindex"],
                    "description": (
                        "操作类型："
                        "store — 存储知识条目；"
                        "get — 按 ID 获取条目；"
                        "search — 搜索知识内容（支持语义+关键词混合检索）；"
                        "list — 列出条目（可按分类筛选）；"
                        "delete — 删除条目；"
                        "stats — 知识库统计；"
                        "reindex — 重建语义向量索引。"
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "知识条目标题（store 操作必需）",
                    "default": "",
                },
                "content": {
                    "type": "string",
                    "description": "知识条目内容（store 操作必需）",
                    "default": "",
                },
                "category": {
                    "type": "string",
                    "description": "分类标签，如 'tool'、'experience'、'lesson'",
                    "default": "",
                },
                "tags": {
                    "type": "string",
                    "description": "逗号分隔的标签列表，如 'python,debug,performance'",
                    "default": "",
                },
                "kind": {
                    "type": "string",
                    "enum": ["declarative", "procedural", "boundary"],
                    "description": (
                        "认知类型（store 时指定条目类型，search/list 时按类型过滤）："
                        "declarative — 声明性事实（是什么）；"
                        "procedural — 程序性启发式（怎么做）；"
                        "boundary — 失效边界（何时失效/踩坑）。"
                    ),
                    "default": "declarative",
                },
                "semantic_tags": {
                    "type": "string",
                    "description": "逗号分隔的语义标签，如 'method,pitfall,benchmark,lesson'",
                    "default": "",
                },
                "entry_id": {
                    "type": "string",
                    "description": "知识条目 ID（用于 get/delete 操作）",
                    "default": "",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（用于 search 操作）",
                    "default": "",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 20",
                    "default": 20,
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "semantic", "keyword"],
                    "description": "搜索模式：auto（自动选择）、semantic（语义搜索）、keyword（关键词搜索）",
                    "default": "auto",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ======================================================================
# 语义搜索引擎（v3.0 新增）
# ======================================================================


class SemanticSearchEngine:
    """
    基于 sentence-transformers 的语义搜索引擎。
    
    将文本编码为向量，通过余弦相似度进行语义匹配。
    支持向量缓存，避免重复计算。
    """

    def __init__(self) -> None:
        self._model = None
        self._vector_cache: dict[str, list[float]] = {}
        # ★5.1：脏标记 + 延迟落盘。原实现每编码一条就全量重写 339KB 缓存文件，
        # 225 条条目冷启动实测额外耗费约 5.7s。
        self._cache_dirty = False
        self._load_cache()

    def _load_cache(self) -> None:
        """加载向量缓存。"""
        if VECTOR_CACHE_FILE.is_file():
            try:
                self._vector_cache = json.loads(
                    VECTOR_CACHE_FILE.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                self._vector_cache = {}
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        """按需淘汰（步骤5.1）：超上限时淘汰最旧的 20%，而非整体清空。

        原实现 `self._vector_cache = {}` 会在知识库增长到上限时清空全部，
        导致下次查询全量重编码（数秒级抖动）。
        """
        n = len(self._vector_cache)
        if n <= MAX_VECTOR_CACHE:
            return
        keep_n = int(MAX_VECTOR_CACHE * 0.8)
        keys = list(self._vector_cache.keys())
        drop_n = n - keep_n
        for k in keys[:drop_n]:
            del self._vector_cache[k]
        self._save_cache()
        self._cache_dirty = False

    def _save_cache(self) -> None:
        """保存向量缓存。"""
        VECTOR_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        VECTOR_CACHE_FILE.write_text(
            json.dumps(self._vector_cache, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_model(self) -> bool:
        """确保模型已加载（惰性）。"""
        global _SEMANTIC_MODEL
        if _SEMANTIC_MODEL is not None:
            return True
        if not _lazy_ensure_semantic():
            return False
        try:
            SentenceTransformer = globals().get("SentenceTransformer")
            if SentenceTransformer is None:
                return False
            model = SentenceTransformer('all-MiniLM-L6-v2')
            _SEMANTIC_MODEL = model
            self._model = model
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """检查语义搜索是否可用（惰性检测依赖，不加载模型）。"""
        return _lazy_ensure_semantic()

    def is_model_ready(self) -> bool:
        """模型是否已真正加载就绪（不触发加载）。

        用于搜索路径判断：模型未就绪时先走关键词检索，避免首次查询
        被 40 秒级的模型加载阻塞（实测冷启动 43.5s）。
        """
        return _SEMANTIC_MODEL is not None

    def warmup_async(self) -> None:
        """后台异步预热语义模型，不阻塞调用线程。

        注意：依赖 import（numpy/sentence_transformers/torch，实测约 10s）
        也必须在子线程内完成，否则主线程仍会被阻塞。
        """
        if _SEMANTIC_MODEL is not None or getattr(self, "_warming", False):
            return
        self._warming = True
        import threading

        def _load() -> None:
            try:
                if not _lazy_ensure_semantic():
                    return
                self._ensure_model()
            except Exception:
                pass
            finally:
                self._warming = False

        threading.Thread(target=_load, daemon=True, name="ks-semantic-warmup").start()

    def encode(self, text: str) -> list[float] | None:
        """将文本编码为向量。"""
        if not self._ensure_model():
            return None

        # 检查缓存（步骤5.1：改用稳定哈希，跨进程可命中）
        cache_key = f"v_{_stable_hash(text)}"
        if cache_key in self._vector_cache:
            return self._vector_cache[cache_key]

        # 编码
        try:
            model = _SEMANTIC_MODEL
            vector = model.encode(text, show_progress_bar=False)
            vector_list = vector.tolist() if hasattr(vector, 'tolist') else list(vector)

            # 缓存（★5.1：只打脏标记，落盘由 flush_cache 统一执行）
            self._vector_cache[cache_key] = vector_list
            self._cache_dirty = True
            if len(self._vector_cache) > MAX_VECTOR_CACHE:
                self._evict_if_needed()

            return vector_list
        except Exception:
            return None

    def encode_batch(self, texts: list[str]) -> list[list[float] | None]:
        """批量编码文本（★5.1 核心优化）。

        原实现逐条调用 encode()：batch=1 时 CPU 上每条约 26ms，且**每编码一条
        就全量重写缓存文件**。改为「先查缓存 → 未命中者一次性批量编码 →
        统一打脏标记」，实测 20 条 0.523s → 0.262s，落盘次数 N 次 → 1 次。

        返回与输入等长的列表，缓存命中项直接复用，失败项为 None。
        """
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        pending: list[tuple[int, str, str]] = []  # (位置, 文本, 缓存键)
        for i, text in enumerate(texts):
            key = f"v_{_stable_hash(text)}"
            cached = self._vector_cache.get(key)
            if cached is not None:
                results[i] = cached
            else:
                pending.append((i, text, key))

        if not pending:
            return results

        if not self._ensure_model():
            return results

        try:
            model = _SEMANTIC_MODEL
            vectors = model.encode(
                [p[1] for p in pending], show_progress_bar=False, batch_size=32
            )
        except Exception:
            return results

        for (i, _text, key), vector in zip(pending, vectors):
            vector_list = vector.tolist() if hasattr(vector, "tolist") else list(vector)
            self._vector_cache[key] = vector_list
            results[i] = vector_list

        self._cache_dirty = True
        if len(self._vector_cache) > MAX_VECTOR_CACHE:
            self._evict_if_needed()
        return results

    def flush_cache(self) -> None:
        """把脏缓存落盘（★5.1：整个检索流程末尾统一调用一次）。"""
        if self._cache_dirty:
            self._save_cache()
            self._cache_dirty = False

    def cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """计算余弦相似度。"""
        if not _lazy_ensure_semantic():
            return 0.0
        np = globals().get("np")
        if np is None:
            return 0.0
        a = np.array(vec_a)
        b = np.array(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


# ── 全局语义搜索引擎实例 ──────────────────────────────────────

_semantic_engine = SemanticSearchEngine()


# ======================================================================
# 多策略搜索增强引擎（v2.0 保留，v3.0 增强）
# ======================================================================


class SearchEnhancer:
    """
    多策略搜索增强引擎。
    
    v3.0 新增：
      - 语义搜索集成（调用 SemanticSearchEngine）
      - 混合搜索模式（语义 + 关键词加权）
      - jieba 中文分词
    """

    # ── 同义词映射表 ────────────────────────────────────
    SYNONYM_MAP: dict[str, list[str]] = {
        "ai": ["人工智能", "artificial intelligence", "ai"],
        "人工智能": ["ai", "artificial intelligence"],
        "agent": ["智能体", "代理", "智能代理"],
        "智能体": ["agent", "代理", "智能代理"],
        "llm": ["大语言模型", "大模型", "语言模型"],
        "大模型": ["llm", "大语言模型", "语言模型"],
        "rag": ["检索增强", "检索增强生成", "知识检索"],
        "检索": ["search", "搜索", "查询"],
        "search": ["检索", "搜索", "查询"],
        "工具": ["tool", "工具函数", "工具模块"],
        "tool": ["工具", "工具函数", "工具模块"],
        "代码": ["code", "代码实现", "源码"],
        "code": ["代码", "源码", "代码实现"],
        "bug": ["错误", "缺陷", "问题", "故障"],
        "错误": ["bug", "缺陷", "问题", "故障"],
        "性能": ["performance", "效率", "速度", "优化"],
        "performance": ["性能", "效率", "速度"],
        "部署": ["deploy", "发布", "上线"],
        "deploy": ["部署", "发布", "上线"],
        "测试": ["test", "测试用例", "验证"],
        "test": ["测试", "测试用例", "验证"],
        "python": ["python", "python3"],
        "github": ["github", "git"],
        "openai": ["openai", "gpt", "chatgpt"],
        "google": ["google", "gemini"],
        "microsoft": ["microsoft", "autoGen", "autogen"],
        "安全": ["security", "安全机制", "护栏"],
        "security": ["安全", "安全机制"],
        "监控": ["monitor", "监控系统", "监视"],
        "monitor": ["监控", "监控系统"],
        "决策": ["decision", "决定", "选择"],
        "decision": ["决策", "决定"],
        "工作流": ["workflow", "流程", "流水线"],
        "workflow": ["工作流", "流程"],
        "向量": ["vector", "embedding", "嵌入"],
        "vector": ["向量", "embedding", "嵌入"],
    }

    def __init__(self) -> None:
        self._synonym_lookup: dict[str, list[str]] = {}
        for word, synonyms in self.SYNONYM_MAP.items():
            self._synonym_lookup[word.lower()] = [s.lower() for s in synonyms]

    # ── 中文分词 ────────────────────────────────────────

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """分词：英文按空格，中文用 jieba（如果可用）。"""
        if _lazy_ensure_jieba():
            try:
                jieba = globals().get("jieba")
                if jieba:
                    return list(jieba.cut(text))
            except Exception:
                pass
        # 回退：按空格和常见分隔符拆分
        import re
        return [w for w in re.split(r'[\s,，。；;：:！!？?（）()\[\]【】{}""''、/\\|_\-]+', text) if w]

    # ── 同义词扩展 ───────────────────────────────────────

    def expand_query(self, query: str) -> list[str]:
        """扩展查询词为同义词列表。"""
        query_lower = query.lower().strip()
        if not query_lower:
            return [query_lower]

        words = query_lower.split()
        expanded: set[str] = set()
        
        for word in words:
            expanded.add(word)
            synonyms = self._synonym_lookup.get(word, [])
            for syn in synonyms:
                expanded.add(syn)
            for key, syn_list in self._synonym_lookup.items():
                if word in key or key in word:
                    for syn in syn_list:
                        expanded.add(syn)

        result = list(expanded)
        if query_lower not in result:
            result.append(query_lower)
        return result

    # ── TF-IDF 评分 ───────────────────────────────────────

    @staticmethod
    def compute_tfidf(
        text: str,
        query_terms: list[str],
        total_docs: int,
        docs_with_term_counts: dict[str, int],
        text_lower: str | None = None,
    ) -> float:
        # ★5.1：支持传入已小写化的文本，避免每条条目重复 lower()
        t = text_lower if text_lower is not None else text.lower()
        score = 0.0
        for term in query_terms:
            tf = 1 + math.log(t.count(term) + 1)
            idf = math.log(total_docs / max(docs_with_term_counts.get(term, 1), 1))
            score += tf * idf
        return score

    @staticmethod
    def search_text_of(entry: dict[str, Any]) -> str:
        """条目参与 IDF 统计的检索文本（★5.1：单一事实来源，供索引复用）。

        注意与 _entry_search_text（向量化用，content 截断 500 字、字段顺序不同）
        刻意保持区别：两者用途不同，混用会改变检索结果。
        """
        return (
            f"{entry.get('title', '')} {entry.get('content', '')} "
            f"{entry.get('category', '')} {' '.join(entry.get('tags') or [])}"
        ).lower()

    def build_idf(
        self, query_terms: list[str], search_texts: list[str] | dict[str, Any]
    ) -> dict[str, int]:
        """计算各查询词的文档频率（★5.1：支持直接传入预构建的检索文本列表）。

        原实现每次 search 都重新拼接 + lower 全库文本（O(terms × docs) 次），
        且无法复用索引。现在可传索引中缓存的文本列表，避免重复构造。
        """
        if isinstance(search_texts, dict):
            texts = [self.search_text_of(e) for e in search_texts.values()]
        else:
            texts = search_texts
        counts: dict[str, int] = {}
        for term in query_terms:
            if not term:
                continue
            c = 0
            for s in texts:
                if term in s:
                    c += 1
            counts[term] = max(c, 1)
        return counts

    # ── 模糊匹配 ─────────────────────────────────────────

    @staticmethod
    def best_fuzzy_score(
        text: str,
        query_terms: list[str],
        char_counts: dict[str, int] | None = None,
    ) -> float:
        """模糊匹配最优分（★5.1：加入三层**精确**剪枝，结果与改造前完全等价）。

        优化前这是关键词检索的最大热点：225 条 × 7 个词共 675 次
        SequenceMatcher(500字正文, 2~5字词) 调用，占 search 总耗时 85%（0.215s）。

        剪枝 1 —— 命中即短路：ratio 的上界是 1.0，best 达到 1.0 后不可能再增大。
        剪枝 2 —— quick_ratio 上界：SequenceMatcher 的匹配字符数 M 不超过两串
                   字符多重集交集的大小，即
                       M ≤ Σ_c min(cnt_text[c], cnt_term[c])
                   若 (2·M_ub/T)·0.7 ≤ best，则该项贡献不可能超过当前最优，跳过。
                   （注意：**不能**简化为"任一字符缺失即 M=0"——空格等字符仍可
                     独立形成匹配块，这是首版实现的错误，已被逐条校验捕获。）
        剪枝 3 —— real_quick_ratio 上界：ratio = 2M/T ≤ 2·min(len_a,len_b)/T。

        三层剪枝均为数学严格上界，不改变任何返回值（见
        scripts/verify_knowledge_equiv.py 的逐条等价校验）。
        """
        if not query_terms or not text:
            return 0.0
        text_lower = text.lower()
        len_a = len(text_lower)
        if char_counts is None:
            char_counts = {}
            for ch in text_lower:
                char_counts[ch] = char_counts.get(ch, 0) + 1
        best = 0.0
        if len(query_terms) > 1:
            # ★5.1：按「与文本的字符交集」降序处理词条。
            # max() 与遍历顺序无关（除完全相等时的浮点表现），因此不改变结果；
            # 但先算高潜力词条能让 best 更快抬升，从而使剪枝 2/3 更早生效。
            def _pot(term: str) -> int:
                if not term:
                    return -1
                seen_t: dict[str, int] = {}
                for ch in term:
                    seen_t[ch] = seen_t.get(ch, 0) + 1
                return sum(
                    min(char_counts.get(ch, 0), need) for ch, need in seen_t.items()
                )

            query_terms = sorted(query_terms, key=lambda t: (-_pot(t), t))
        for term in query_terms:
            if not term:
                continue
            if term in text_lower:
                best = 1.0
                break
            len_b = len(term)
            total_len = len_a + len_b
            if not total_len:
                continue

            # 剪枝 2：字符多重集交集上界（quick_ratio 的严格上界）
            m_ub = 0
            seen: dict[str, int] = {}
            for ch in term:
                seen[ch] = seen.get(ch, 0) + 1
            for ch, need in seen.items():
                have = char_counts.get(ch, 0)
                if have:
                    m_ub += have if have < need else need
            if (2.0 * m_ub / total_len) * 0.7 <= best:
                continue

            # 剪枝 3：real_quick_ratio 严格上界
            if (2.0 * (len_a if len_a < len_b else len_b) / total_len) * 0.7 <= best:
                continue

            score = SequenceMatcher(None, text_lower, term).ratio()
            candidate = score * 0.7
            if candidate > best:
                best = candidate
        return best

    # ── 综合评分（v3.0 增强：语义+关键词混合） ───────────

    def score_entry(
        self,
        entry: dict[str, Any],
        query: str,
        query_terms: list[str],
        total_docs: int,
        docs_with_term_counts: dict[str, int],
        precomputed: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        """
        对一条知识条目进行综合评分。
        
        返回 (keyword_score, semantic_score) 二元组。
        keyword_score 用于纯关键词搜索排序。
        semantic_score 用于语义搜索排序。

        precomputed（★5.1 新增，可选）：由 KnowledgeStore 索引提供的预计算字段
        （小写文本与字符集），用于免去每条目重复的 lower()/set() 构造。
        不传时行为与改造前完全一致。
        """
        keyword_score = 0.0
        query_lower = query.lower()

        if precomputed is not None:
            title_lower = precomputed["title_lower"]
            content_lower = precomputed["content_lower"]
            tags_lower = precomputed["tags_lower"]
            category_lower = precomputed["category_lower"]
            title_counts = precomputed["title_counts"]
            content_counts = precomputed["content_counts"]
        else:
            title_lower = entry.get("title", "").lower()
            content_lower = entry.get("content", "").lower()
            tags_lower = " ".join(entry.get("tags", [])).lower()
            category_lower = entry.get("category", "").lower()
            title_counts = {}
            for ch in title_lower:
                title_counts[ch] = title_counts.get(ch, 0) + 1
            content_counts = {}
            for ch in content_lower:
                content_counts[ch] = content_counts.get(ch, 0) + 1

        # ── 关键词评分 ──
        if query_lower in title_lower:
            keyword_score += 4.0
        for term in query_terms:
            if term and term in title_lower:
                keyword_score += 2.0
        keyword_score += self.best_fuzzy_score(title_lower, query_terms, title_counts) * 2.0

        if query_lower in tags_lower:
            keyword_score += 3.0
        for term in query_terms:
            if term and term in tags_lower:
                keyword_score += 1.5

        if query_lower in category_lower:
            keyword_score += 2.0
        for term in query_terms:
            if term and term in category_lower:
                keyword_score += 1.0

        keyword_score += (
            self.compute_tfidf(
                content_lower, query_terms, total_docs, docs_with_term_counts, content_lower
            )
            * 1.5
        )
        keyword_score += self.best_fuzzy_score(content_lower, query_terms, content_counts) * 1.0

        if query_lower in content_lower:
            keyword_score += 2.0
        if query_lower in title_lower:
            keyword_score += 3.0

        # ── 语义评分（由外部计算后传入） ──
        # 此处只返回 0.0，实际语义分数由外部计算
        return (keyword_score, 0.0)

    def score_entry_semantic(
        self,
        entry: dict[str, Any],
        query_vector: list[float] | None,
        entry_vector: list[float] | None,
    ) -> float:
        """计算语义相似度分数。"""
        if query_vector is None or entry_vector is None:
            return 0.0
        return _semantic_engine.cosine_similarity(query_vector, entry_vector)


# ── 全局搜索增强器实例 ──────────────────────────────────────

_search_enhancer = SearchEnhancer()


# ── 存储引擎（v3.0 增强版） ──────────────────────────────


class KnowledgeStore:
    """知识存储引擎（v3.0 语义搜索版）。"""

    def __init__(self, path: Path = KNOWLEDGE_FILE) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        # ★5.1：检索索引（小写文本 + 字符频次），按数据版本号惰性重建。
        # 避免每次 search 都 O(terms × docs) 次地重复拼接/lower 全库文本。
        self._data_version = 0
        self._index_version = -1
        self._index: list[dict[str, Any]] = []
        self._warming_store = False
        self._load()
        self._import_seeds_if_needed()
        self._data_version += 1

    def _import_seeds_if_needed(self) -> None:
        """首次启动时，若知识库缺少程序性启发式条目，则自动导入种子卡片。

        幂等：只要已存在 procedural 条目即跳过，避免重复导入。
        数据源为 knowledge/seed_heuristics.json（借鉴 ReasFlow 知识卡片双轨制）。
        """
        seed_file = KNOWLEDGE_DIR / "seed_heuristics.json"
        if not seed_file.is_file():
            return
        if any(e.get("kind") == "procedural" for e in self._data.values()):
            return
        try:
            seeds = json.loads(seed_file.read_text(encoding="utf-8"))
            now = time.time()
            for i, seed in enumerate(seeds):
                entry_id = f"KSEED{int(now)}_{i}"
                entry = KnowledgeEntry(
                    id=entry_id,
                    title=seed.get("title", ""),
                    content=seed.get("content", ""),
                    category=seed.get("category", "general"),
                    tags=seed.get("tags", []),
                    kind=seed.get("kind", "declarative"),
                    semantic_tags=seed.get("semantic_tags", []),
                    source="seed_heuristics.json",
                    created_at=now,
                    updated_at=now,
                )
                self._data[entry_id] = asdict(entry)
            self._save()
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    def _load(self) -> None:
        """从文件加载知识库。"""
        if self._path.is_file():
            try:
                raw = self._path.read_text(encoding="utf-8")
                self._data = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """保存知识库到文件。"""
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 数据变化 → 索引失效
        self._data_version += 1

    # ── 检索索引（★5.1 两阶段检索的 Stage 1 基础设施） ──────────

    def _ensure_index(self) -> None:
        """按数据版本惰性构建/复用检索索引。

        索引内容（每条目）：
          search_text   —— IDF 统计用的检索文本（小写，单一事实来源）
          pre           —— score_entry 的预计算字段（小写文本 + 字符频次），
                           免去每次检索重复的 lower() / 字符计数
        构建成本 O(总字数)，只在数据变更后发生一次；检索成本从
        O(terms × docs) 的重复构造降为 O(docs) 的纯查找。
        """
        if self._index_version == self._data_version:
            return

        index: list[dict[str, Any]] = []
        for entry in self._data.values():
            title_lower = entry.get("title", "").lower()
            content_lower = entry.get("content", "").lower()
            title_counts: dict[str, int] = {}
            for ch in title_lower:
                title_counts[ch] = title_counts.get(ch, 0) + 1
            content_counts: dict[str, int] = {}
            for ch in content_lower:
                content_counts[ch] = content_counts.get(ch, 0) + 1
            index.append({
                "id": entry.get("id", ""),
                "entry": entry,
                "search_text": _search_enhancer.search_text_of(entry),
                "pre": {
                    "title_lower": title_lower,
                    "content_lower": content_lower,
                    "tags_lower": " ".join(entry.get("tags") or []).lower(),
                    "category_lower": entry.get("category", "").lower(),
                    "title_counts": title_counts,
                    "content_counts": content_counts,
                },
            })
        self._index = index
        self._index_version = self._data_version

    def _stage1_candidates(
        self, query_terms: list[str], kind: str, max_results: int, semantic: bool = False
    ) -> list[int]:
        """Stage 1：廉价粗召回（纯子串判断，**不**调用 SequenceMatcher）。

        返回索引下标列表。为保证结果等价，候选上限取得很保守：
            limit = max(STAGE1_MIN_CANDIDATES, max_results * 20)
        当前规模（225 条 < 300）下等价于全量，行为与改造前完全一致；
        只有库显著增长时粗筛才真正生效，从而避免延迟随库体积线性膨胀。

        ★语义模式不参与粗筛（semantic=True 时直接返回全量）：
          关键词粗筛会漏掉"语义相关但字面无交集"的条目，这与语义检索的
          目的直接冲突。知识卡片 K1793348203 已明确该边界——两阶段的关键词
          预筛只作**关键词路径**的加速手段，不能当作语义召回的前置过滤器。
        """
        if semantic:
            return [
                i
                for i, item in enumerate(self._index)
                if not kind or item["entry"].get("kind", "declarative") == kind
            ]

        limit = max(STAGE1_MIN_CANDIDATES, max_results * 20)
        total = len(self._index)
        keep_all = total <= limit

        scored: list[tuple[int, int]] = []
        for i, item in enumerate(self._index):
            entry = item["entry"]
            if kind and entry.get("kind", "declarative") != kind:
                continue
            if keep_all:
                scored.append((0, i))
                continue
            search_text = item["search_text"]
            hits = 0
            for term in query_terms:
                if term and term in search_text:
                    hits += 1
            scored.append((hits, i))

        if not keep_all:
            scored.sort(key=lambda x: -x[0])
            scored = scored[:limit]

        return [i for _, i in scored]

    def _warmup_semantic_bg(self) -> None:
        """后台预热语义模型 **并预编码全部条目**（★5.1）。

        原实现只调用 warmup_async() 加载模型，不建向量：模型就绪后的
        "首次"语义查询仍要现场逐条编码全部条目（实测 225 条约 5.9s）。
        改为在预热线程内一并建好向量缓存，使首个语义查询只需编码查询本身。

        全程运行在守护线程内，不阻塞任何调用方（auto 模式首次查询仍走关键词）。
        """
        if _semantic_engine.is_model_ready() or self._warming_store:
            return
        self._warming_store = True
        import threading

        def _job() -> None:
            try:
                if not _lazy_ensure_semantic():
                    return
                if not _semantic_engine._ensure_model():
                    return
                entries = list(self._data.values())
                _semantic_engine.encode_batch([_entry_search_text(e) for e in entries])
                _semantic_engine.flush_cache()
            except Exception:
                pass
            finally:
                self._warming_store = False

        threading.Thread(target=_job, daemon=True, name="ks-warmup-full").start()

    def store(
        self,
        title: str,
        content: str,
        category: str = "",
        tags: str = "",
        kind: str = "declarative",
        semantic_tags: str = "",
    ) -> str:
        """存储一条知识条目。"""
        if not title.strip():
            raise KnowledgeStoreError("标题不能为空")
        if not content.strip():
            raise KnowledgeStoreError("内容不能为空")

        if kind not in ("declarative", "procedural", "boundary"):
            kind = "declarative"

        now = time.time()
        entry_id = f"K{int(now)}"
        # ★5.1：同一秒内连续 store 会生成相同 ID，原实现直接覆盖导致**静默丢数据**
        # （实测两条知识卡片在同一秒写入，第一条被第二条整条覆盖）。
        if entry_id in self._data:
            suffix = 1
            while f"{entry_id}_{suffix}" in self._data:
                suffix += 1
            entry_id = f"{entry_id}_{suffix}"
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        sem_tag_list = (
            [t.strip() for t in semantic_tags.split(",") if t.strip()]
            if semantic_tags else []
        )

        entry = KnowledgeEntry(
            id=entry_id,
            title=title.strip(),
            content=content.strip(),
            category=category.strip() or "general",
            tags=tag_list,
            kind=kind,
            semantic_tags=sem_tag_list,
            created_at=now,
            updated_at=now,
        )

        self._data[entry_id] = asdict(entry)
        self._save()

        return f"✅ 已存储知识条目 [{entry_id}]: {title} ({kind})"

    def get(self, entry_id: str) -> str:
        """按 ID 获取知识条目。"""
        entry = self._data.get(entry_id)
        if not entry:
            raise KnowledgeStoreError(f"未找到条目: {entry_id}")

        return self._format_entry(entry)

    def search(self, query: str, max_results: int = 20, mode: str = "auto", kind: str = "") -> str:
        """
        多策略增强搜索（v3.0 语义搜索版）。
        
        mode 参数：
          - "auto": 自动选择（语义可用则语义+关键词混合，否则纯关键词）
          - "semantic": 强制语义搜索
          - "keyword": 强制关键词搜索
        kind 参数：
          - 空字符串: 不过滤
          - "declarative"/"procedural"/"boundary": 仅在该认知类型内搜索
        """
        if not query:
            raise KnowledgeStoreError("搜索关键词不能为空")

        total_docs = len(self._data)
        if total_docs == 0:
            return "知识库为空，无搜索结果。"

        # ── 决定搜索模式 ──
        use_semantic = False
        if mode == "semantic":
            use_semantic = _semantic_engine.is_available()
            if not use_semantic:
                return "⚠️ 语义搜索不可用（需要安装 sentence-transformers），已回退到关键词搜索。"
        elif mode == "auto":
            # 关键优化：先判模型是否就绪（不触发 import/加载），未就绪则走关键词
            # 并在后台预热。实测冷启动 import torch + 加载模型共需 40s+，
            # 绝不应阻塞首次查询。
            if total_docs >= 2 and _semantic_engine.is_model_ready():
                use_semantic = _semantic_engine.is_available()
            else:
                use_semantic = False
                if total_docs >= 2:
                    # ★5.1：预热同时预编码全部条目，避免"模型刚就绪的首次语义
                    # 查询"仍需现场编码（实测 225 条约 5.9s）
                    self._warmup_semantic_bg()
        # keyword 模式不使用语义

        # ── 同义词扩展（关键词搜索用） ──
        expanded_terms = _search_enhancer.expand_query(query)
        query_terms = list(set(expanded_terms))

        # ── 构建/复用检索索引（★5.1 Stage 1 基础设施） ──
        self._ensure_index()

        # ── Stage 1：廉价粗召回（不触发 SequenceMatcher） ──
        candidates = self._stage1_candidates(query_terms, kind, max_results, semantic=use_semantic)

        # ── 文档频率（IDF）：直接复用索引中的检索文本，避免重复拼接/lower ──
        docs_with_term_counts = _search_enhancer.build_idf(
            query_terms, [item["search_text"] for item in self._index]
        )

        # ── 语义搜索：查询向量 ──
        query_vector = None
        if use_semantic:
            query_vector = _semantic_engine.encode(query)

        # ── Stage 2：候选集精排 ──
        scored_results: list[tuple[float, float, dict[str, Any]]] = []
        if use_semantic and query_vector is not None:
            # ★5.1：候选集向量**一次性批量编码**，替代逐条 encode（batch=1）
            entry_texts = [
                _entry_search_text(self._index[i]["entry"]) for i in candidates
            ]
            entry_vectors = _semantic_engine.encode_batch(entry_texts)
            for idx, entry_vector in zip(candidates, entry_vectors):
                item = self._index[idx]
                kw_score, _ = _search_enhancer.score_entry(
                    item["entry"],
                    query,
                    query_terms,
                    total_docs,
                    docs_with_term_counts,
                    item["pre"],
                )
                sem_score = 0.0
                if entry_vector is not None:
                    sem_score = _semantic_engine.cosine_similarity(
                        query_vector, entry_vector
                    )
                if kw_score > 0 or sem_score > 0:
                    scored_results.append((kw_score, sem_score, item["entry"]))
        else:
            for idx in candidates:
                item = self._index[idx]
                kw_score, _ = _search_enhancer.score_entry(
                    item["entry"],
                    query,
                    query_terms,
                    total_docs,
                    docs_with_term_counts,
                    item["pre"],
                )
                if kw_score > 0:
                    scored_results.append((kw_score, 0.0, item["entry"]))

        # ── 排序 ──
        if use_semantic:
            # 混合排序：语义分 * 0.7 + 关键词分 * 0.3（归一化后）
            max_kw = max((s[0] for s in scored_results), default=1)
            max_sem = max((s[1] for s in scored_results), default=1)
            scored_results.sort(
                key=lambda x: (x[1] / max_sem if max_sem > 0 else 0) * 0.7
                            + (x[0] / max_kw if max_kw > 0 else 0) * 0.3,
                reverse=True,
            )
            sort_desc = "语义+关键词混合排序"
        else:
            # 纯关键词排序
            scored_results.sort(key=lambda x: -x[0])
            sort_desc = "关键词综合评分排序"

        actual_limit = min(max_results, len(scored_results))

        if not scored_results:
            _semantic_engine.flush_cache()
            return f"未找到与 '{query}' 相关的知识条目。"

        # ── 格式化输出 ──
        mode_label = "🔬 语义+关键词混合搜索" if use_semantic else "🔍 关键词搜索"
        lines = [
            f"{mode_label} '{query}' 找到 {len(scored_results)} 条结果",
            f"  排序: {sort_desc}",
            f"  显示前 {actual_limit} 条:\n"
        ]

        for kw_score, sem_score, entry in scored_results[:actual_limit]:
            stars = "⭐" * min(5, max(1, int((kw_score + sem_score * 5) / 3)))
            score_str = f"关键词: {kw_score:.1f}"
            if use_semantic:
                score_str += f" | 语义: {sem_score:.4f}"

            lines.append(f"  {stars} [{entry['id']}] {entry['title']} ({entry['category']})")
            lines.append(f"      {score_str} | 标签: {', '.join(entry['tags']) if entry['tags'] else '无'}")
            content_preview = entry["content"][:100].replace("\n", " ")
            if len(entry["content"]) > 100:
                lines.append(f"      {content_preview}…")
            else:
                lines.append(f"      {content_preview}")
            lines.append("")

        # ★5.1：本次检索新增的向量统一在末尾落盘一次（原实现每条编码都整盘重写）
        _semantic_engine.flush_cache()
        return "\n".join(lines)

    def reindex(self) -> str:
        """重建语义向量索引。"""
        if not _semantic_engine.is_available():
            return "⚠️ 语义搜索不可用，无法重建索引。"

        count = len(self._data)
        if count == 0:
            return "知识库为空，无需重建索引。"

        # 清除旧的向量缓存（★5.1：内存与磁盘需同步清空，
        # 否则 encode 仍会命中内存中的旧向量，重建形同虚设）
        _semantic_engine._vector_cache = {}
        vector_cache_path = VECTOR_CACHE_FILE
        if vector_cache_path.is_file():
            vector_cache_path.write_text("{}", encoding="utf-8")

        # ★5.1：批量编码替代逐条 encode（batch=1 → batch=32），末尾统一落盘一次
        entry_texts = [_entry_search_text(e) for e in self._data.values()]
        vectors = _semantic_engine.encode_batch(entry_texts)
        success = sum(1 for v in vectors if v is not None)
        _semantic_engine.flush_cache()

        return f"✅ 语义索引重建完成: {success}/{count} 条已索引"

    def list_entries(self, category: str = "", max_results: int = 20, kind: str = "") -> str:
        """列出知识条目，可按分类/认知类型筛选。"""
        entries = list(self._data.values())

        if category:
            entries = [e for e in entries if e["category"] == category]
        if kind:
            entries = [e for e in entries if e.get("kind", "declarative") == kind]

        entries.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
        actual_limit = min(max_results, len(entries))

        if not entries:
            if kind and category:
                return f"分类 '{category}' 且认知类型 '{kind}' 中没有知识条目。"
            if kind:
                return f"认知类型 '{kind}' 中没有知识条目。"
            if category:
                return f"分类 '{category}' 中没有知识条目。"
            return "知识库为空。"

        # 检查语义搜索是否可用
        semantic_tag = " 🔬语义就绪" if _semantic_engine.is_available() else ""

        lines = [f"📚 知识条目列表（共 {len(entries)} 条{semantic_tag}，显示前 {actual_limit} 条）:\n"]
        for entry in entries[:actual_limit]:
            tags_str = f" [{', '.join(entry['tags'])}]" if entry["tags"] else ""
            lines.append(f"  [{entry['id']}] {entry['title']} ({entry['category']}){tags_str}")

        if len(entries) > actual_limit:
            lines.append(f"\n  … 还有 {len(entries) - actual_limit} 条未显示")

        return "\n".join(lines)

    def delete(self, entry_id: str) -> str:
        """删除知识条目。"""
        if entry_id not in self._data:
            raise KnowledgeStoreError(f"未找到条目: {entry_id}")

        title = self._data[entry_id]["title"]
        del self._data[entry_id]
        self._save()

        return f"🗑️ 已删除知识条目 [{entry_id}]: {title}"

    def archive(self, entry_id: str) -> str:
        """归档知识条目：移到 knowledge/archive/，不删除（可恢复）。

        与 delete 的区别：归档保留完整条目，只是从主库瘦身，
        未来需要时可从 archive/ 找回，避免"遗忘"导致的不可逆丢失。
        """
        if entry_id not in self._data:
            raise KnowledgeStoreError(f"未找到条目: {entry_id}")

        entry = self._data[entry_id]
        archive_dir = KNOWLEDGE_DIR / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_file = archive_dir / f"{entry_id}.json"
        archive_file.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        title = entry["title"]
        del self._data[entry_id]
        self._save()

        return (
            f"📦 已归档知识条目 [{entry_id}]: {title}\n"
            f"   归档文件: knowledge/archive/{entry_id}.json（可恢复）"
        )

    def stats(self) -> str:
        """知识库统计信息。"""
        if not self._data:
            return "知识库为空。"

        category_count: dict[str, int] = {}
        kind_count: dict[str, int] = {}
        total_tags = 0
        total_content_len = 0

        for entry in self._data.values():
            cat = entry.get("category", "general")
            category_count[cat] = category_count.get(cat, 0) + 1
            kd = entry.get("kind", "declarative")
            kind_count[kd] = kind_count.get(kd, 0) + 1
            total_tags += len(entry.get("tags", []))
            total_content_len += len(entry.get("content", ""))

        avg_len = total_content_len / len(self._data) if self._data else 0

        semantic_status = "✅ 可用" if _semantic_engine.is_available() else "❌ 不可用"
        jieba_status = "✅ 可用" if _lazy_ensure_jieba() else "❌ 不可用"

        lines = [
            f"📊 知识库统计\n{'='*30}",
            f"总条目数: {len(self._data)}",
            f"总标签数: {total_tags}",
            f"平均内容长度: {avg_len:.0f} 字符",
            f"语义搜索: {semantic_status}",
            f"中文分词: {jieba_status}",
            f"\n认知类型分布:",
        ]
        for kd, count in sorted(kind_count.items(), key=lambda x: -x[1]):
            lines.append(f"  {kd}: {count} 条")
        lines.append(f"\n分类分布:")
        for cat, count in sorted(category_count.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {count} 条")

        return "\n".join(lines)

    @staticmethod
    def _format_entry(entry: dict[str, Any]) -> str:
        """格式化显示一条知识条目。"""
        tags_str = f" [{', '.join(entry.get('tags', []))}]" if entry.get("tags") else ""
        source_str = f"\n来源: {entry['source']}" if entry.get("source") else ""
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.get("created_at", 0)))
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.get("updated_at", 0)))

        return (
            f"📖 [{entry['id']}] {entry['title']}\n"
            f"{'='*40}\n"
            f"分类: {entry.get('category', 'general')}{tags_str}{source_str}\n"
            f"创建: {created} | 更新: {updated} | 版本: {entry.get('version', 1)}\n"
            f"{'─'*40}\n"
            f"{entry['content']}"
        )


# ── 全局实例 ──────────────────────────────────────────────

_store = KnowledgeStore()


def execute_knowledge_tool(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "")

    try:
        if action == "store":
            title = arguments.get("title", "")
            content = arguments.get("content", "")
            category = arguments.get("category", "")
            tags = arguments.get("tags", "")
            kind = arguments.get("kind", "declarative")
            semantic_tags = arguments.get("semantic_tags", "")
            return _store.store(title, content, category, tags, kind, semantic_tags)

        elif action == "get":
            entry_id = arguments.get("entry_id", "")
            if not entry_id:
                return "❌ 错误: 请提供 entry_id"
            return _store.get(entry_id)

        elif action == "search":
            query = arguments.get("query", "")
            max_results = int(arguments.get("max_results", 20))
            mode = arguments.get("mode", "auto")
            kind = arguments.get("kind", "")
            return _store.search(query, max_results, mode, kind)

        elif action == "reindex":
            return _store.reindex()

        elif action == "list":
            category = arguments.get("category", "")
            max_results = int(arguments.get("max_results", 20))
            kind = arguments.get("kind", "")
            return _store.list_entries(category, max_results, kind)

        elif action == "delete":
            entry_id = arguments.get("entry_id", "")
            if not entry_id:
                return "❌ 错误: 请提供 entry_id"
            return _store.delete(entry_id)

        elif action == "archive":
            entry_id = arguments.get("entry_id", "")
            if not entry_id:
                return "❌ 错误: 请提供 entry_id"
            return _store.archive(entry_id)

        elif action == "stats":
            return _store.stats()

        else:
            return f"❌ 未知操作: {action}"

    except KnowledgeStoreError as exc:
        return f"❌ 知识库错误: {exc}"
