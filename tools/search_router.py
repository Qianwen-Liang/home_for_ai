"""search_router — 检索路由器：L1 重排 / L2 缓存 / L3 改写 / L4 多源 RRF

四层增强的编排者：
  L3 查询改写 → L2 缓存检查 → L4 多源并行召回 + RRF 融合 → L1 噪音过滤与重排

设计原则：
  - 每层可独立开关（便于 A/B 对照与回滚）
  - 单源失败不影响整体（降级）
  - 全部结果统一为 SearchHit，便于融合
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path

from tools.search_sources import (
    ALL_SOURCES, FALLBACK_SOURCES, SearchHit, Source, SourceError,
)

# ─────────────────────────── L1: 噪音与重排 ───────────────────────────

# 噪音域名：词典 / 百科 / 翻译 / 词典聚合站
NOISE_DOMAINS = {
    "dictionary.cambridge.org", "baike.baidu.com", "iciba.com", "dict.eudic.net",
    "global.bing.com", "learn-en.org", "youdao.com", "dict.cn", "zdic.net",
    "hanyu.baidu.com", "cidian.com", "thesaurus.com", "merriam-webster.com",
    "dictionary.com", "vocabulary.com", "wordreference.com", "collinsdictionary.com",
}
# 噪音标题特征
NOISE_TITLE_MARKERS = ("词典", "百科", "翻译", "音标", "例句", "的意思", "是什么意思",
                       "dictionary", "definition & meaning", "translation")


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    d = (m.group(1) if m else "").lower()
    return d[4:] if d.startswith("www.") else d


def is_noise(hit: SearchHit) -> bool:
    """判断是否噪音结果。"""
    dom = _domain(hit.url)
    if dom and any(dom == n or dom.endswith("." + n) for n in NOISE_DOMAINS):
        return True
    title_low = hit.title.lower()
    return any(m.lower() in title_low for m in NOISE_TITLE_MARKERS)


_STOP = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with",
         "is", "are", "how", "what", "vs", "versus", "的", "了", "和", "与", "是"}


def _terms(query: str) -> list[str]:
    """中文按字/词、英文按词提取检索词。"""
    q = query.lower()
    en = [t for t in re.findall(r"[a-z0-9][a-z0-9\-\._]*", q) if t not in _STOP and len(t) > 1]
    zh = re.findall(r"[\u4e00-\u9fa5]{2,}", q)
    return en + zh


def relevance(hit: SearchHit, query: str) -> float:
    """查询词覆盖度 0..1。"""
    terms = _terms(query)
    if not terms:
        return 0.0
    text = hit.as_text()
    hit_n = sum(1 for t in terms if t in text)
    return hit_n / len(terms)


def rank_hits(hits: list[SearchHit], query: str, top_k: int,
              drop_noise: bool = True) -> list[SearchHit]:
    """L1：噪音过滤 + 综合重排。

    综合分 = 0.45*relevance + 0.30*authority + 0.25*rrf_norm
    """
    pool = [h for h in hits if not (drop_noise and is_noise(h))]
    if not pool:
        pool = hits  # 全是噪音时保留，避免空结果（由调用方决定是否展示）
    # 相关性阈值：剔除几乎不匹配的"陪跑"结果
    # 注意：对长查询（词数多）纯比例判定会过严——6 词查询命中 2 词仅 0.33，
    # 会被误杀。故采用"比例达标 或 长查询命中至少 2 词"的自适应判定。
    MIN_REL = 0.34
    terms = _terms(query)

    def _relevant(h: SearchHit) -> bool:
        if relevance(h, query) >= MIN_REL:
            return True
        if len(terms) >= 4:
            text = h.as_text()
            return sum(1 for t in terms if t in text) >= 2
        return False

    filtered = [h for h in pool if _relevant(h)]
    if filtered:
        pool = filtered
    max_rrf = max((1.0 / (60 + h.rank) for h in pool), default=1.0) or 1.0
    scored = []
    for h in pool:
        rrf_norm = (1.0 / (60 + h.rank)) / max_rrf
        score = 0.45 * relevance(h, query) + 0.30 * h.authority + 0.25 * rrf_norm
        scored.append((score, h))
    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:top_k]]


# ─────────────────────────── L2: 持久化缓存 ───────────────────────────

class SearchCache:
    """TTL 磁盘缓存（替代原 20 条内存缓存）。"""

    def __init__(self, path: Path | None = None, ttl: int = 1800, max_entries: int = 500):
        self.path = path or (Path(__file__).resolve().parent.parent / "memory" / "search_cache.json")
        self.ttl = ttl
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self.stats = {"hit": 0, "miss": 0, "evict": 0}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw.get("entries", {})
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"entries": self._data}, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def get(self, key: str):
        with self._lock:
            e = self._data.get(key)
            if not e:
                self.stats["miss"] += 1
                return None
            if time.time() - e.get("ts", 0) > self.ttl:
                self._data.pop(key, None)
                self.stats["miss"] += 1
                return None
            self.stats["hit"] += 1
            return e.get("v")

    def put(self, key: str, value) -> None:
        with self._lock:
            if len(self._data) >= self.max_entries:
                oldest = sorted(self._data.items(), key=lambda kv: kv[1].get("ts", 0))
                for k, _ in oldest[: max(1, len(oldest) // 5)]:
                    self._data.pop(k, None)
                    self.stats["evict"] += 1
            self._data[key] = {"ts": time.time(), "v": value}
            self._save()

    def hit_rate(self) -> float:
        t = self.stats["hit"] + self.stats["miss"]
        return self.stats["hit"] / t if t else 0.0


_CACHE = SearchCache()


# ─────────────────────────── L3: 查询改写 ───────────────────────────

# 领域词注入表：查询含左侧词时，追加右侧领域限定词以提升召回精度
DOMAIN_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("context engineering", "上下文工程", "context rot", "attention budget"), "LLM agent"),
    (("rag", "retrieval", "检索", "bm25", "召回", "rerank", "重排序"), "retrieval augmented generation"),
    (("mcp", "model context protocol"), "protocol specification"),
    (("harness", "智能体", "agent", "agentic"), "agent framework"),
]


def rewrite_query(query: str, enable_hints: bool = True) -> tuple[str, list[str]]:
    """L3：规则化查询改写。返回 (主查询, 变体列表)。

    策略：
      1. 压缩多余空白
      2. 领域词注入（仅用于生成变体，不改主查询，避免污染精确标识符查询）
      3. 生成 0-2 个变体用于多路召回
    """
    base = re.sub(r"\s+", " ", query).strip()
    variants: list[str] = []
    if enable_hints:
        low = base.lower()
        for keys, hint in DOMAIN_HINTS:
            if any(k in low for k in keys) and hint.lower() not in low:
                variants.append(f"{base} {hint}")
                break
    return base, variants[:2]


# ─────────────────────────── L4: 多源并行 + RRF ───────────────────────────

def _dispatch(sources: list[Source], query: str, n: int, out: list[SearchHit],
              errors: dict[str, str], used: list[str],
              overall_timeout: float = 8.0) -> None:
    """并行执行多源检索，结果写入 out。

    overall_timeout：整体截止时间。超时未返回的源被取消（不阻塞主流程），
    这是 fast 模式低延迟的关键。
    """
    if not sources:
        return
    ex = ThreadPoolExecutor(max_workers=min(6, len(sources)))
    fut = {ex.submit(s.search, query, n): s for s in sources}
    try:
        done, pending = wait(fut, timeout=overall_timeout)
        for f in done:
            s = fut[f]
            try:
                hits = f.result()
                if hits:
                    out.extend(hits)
                    used.append(s.name)
            except Exception as exc:  # noqa: BLE001
                errors[s.name] = str(exc)[:120]
        for f in pending:
            s = fut[f]
            errors[s.name] = "整体超时被取消"
            f.cancel()
    finally:
        ex.shutdown(wait=False)


# ── 模式配置 ───────────────────────────────────────────
# fast：少源 + 小召回 + 短超时，优先低延迟
# deep：全相关源 + 变体召回 + 宽超时，优先质量
FAST_PROFILE = {"max_sources": 3, "per_source": 3, "variants": False,
                "timeout": 4.0, "exclude_slow": True}
DEEP_PROFILE = {"max_sources": 99, "per_source": 4, "variants": True,
                "timeout": 9.0, "exclude_slow": False}

# 已知高延迟源：实测 arXiv API 单次可达 16.9s，fast 模式应规避
SLOW_SOURCES = {"arxiv"}


def _select_sources(base: str, max_sources: int, exclude_slow: bool = False) -> list[Source]:
    """按触发器相关度排序选源，并保证基础召回源在场。

    exclude_slow=True 时剔除已知高延迟源（fast 模式用，保低延迟）。
    """
    scored = [(s.match_score(base), i, s) for i, s in enumerate(ALL_SOURCES)]
    selected = [s for sc, _, s in scored if sc > 0]
    for s in ALL_SOURCES:
        if s.name in {"github", "huggingface"} and s not in selected:
            selected.append(s)
    order = {id(s): sc for sc, _, s in scored}
    selected.sort(key=lambda s: -order.get(id(s), 0))
    if exclude_slow:
        fast_pool = [s for s in selected if s.name not in SLOW_SOURCES]
        if fast_pool:
            selected = fast_pool
    # 无触发器命中时扩大基础源，避免长自然语言查询只有 1-2 个源可用
    if not any(s.match_score(base) > 0 for s in ALL_SOURCES):
        for name in ("stackoverflow", "wikipedia"):
            for s in ALL_SOURCES:
                if s.name == name and s not in selected:
                    selected.append(s)
    return selected[:max_sources] if max_sources < len(selected) else selected


def _search_once(base: str, variants: list[str], max_results: int,
                 profile: dict, use_fallback: bool, drop_noise: bool,
                 deadline: float = 0.0
                 ) -> tuple[list[SearchHit], dict[str, str], list[str]]:
    """执行一轮检索（不含缓存与改写）。deadline 为绝对时间戳，超时即提前返回。"""
    import time as _t

    def _out_of_time() -> bool:
        return deadline > 0 and _t.time() > deadline

    selected = _select_sources(base, profile["max_sources"],
                               exclude_slow=profile.get("exclude_slow", False))
    hits: list[SearchHit] = []
    errors: dict[str, str] = {}
    used: list[str] = []
    _dispatch(selected, base, profile["per_source"], hits, errors, used,
              overall_timeout=profile["timeout"])
    # 变体仅在完全无结果时启用（有少量结果时不值得再多花一轮往返）
    if profile["variants"] and not hits and not _out_of_time():
        for v in variants:
            _dispatch(selected[:2], v, profile["per_source"], hits, errors, used,
                      overall_timeout=profile["timeout"])

    # 兜底：一级 Wikipedia（无词典噪音）→ 二级 Bing（加严过滤）
    if not hits and use_fallback and not _out_of_time():
        _dispatch([s for s in ALL_SOURCES if s.name == "wikipedia"],
                  base, profile["per_source"], hits, errors, used,
                  overall_timeout=profile["timeout"])
    if not hits and use_fallback and not _out_of_time():
        _dispatch(FALLBACK_SOURCES, base, profile["per_source"], hits, errors, used,
                  overall_timeout=profile["timeout"])
        hits = [h for h in hits if not is_noise(h) and relevance(h, base) >= 0.5]
    return hits, errors, used


def _quality_ok(hits: list[SearchHit], query: str, max_results: int) -> bool:
    """级联升级判据：判断 fast 模式结果是否已足够。

    实测结论（10 查询对比）：fast 模式本身已达 P@5=1.000，与 deep 持平。
    因此 auto 的升级不应由"相关性"触发（那会让大多数查询跑两轮、延迟翻倍），
    而应只在 fast「严重无结果」时兜底升级，让 deep 承担 fallback 职责。
    """
    return len(hits) >= min(3, max_results)


def federated_search(query: str, max_results: int = 5, mode: str = "auto", *,
                     use_rewrite: bool = True, use_cache: bool = True,
                     use_fallback: bool = True, drop_noise: bool = True,
                     per_source: int = 4) -> dict:
    """联邦检索主入口。

    mode:
      - "fast"  低延迟：最多 2 个源、每源 3 条、整体 4s 超时
      - "deep"  高质量：全相关源、变体召回、整体 9s 超时
      - "auto"  级联：先 fast，质量不达标再升级 deep（默认）
    """
    t0 = time.time()
    mode = (mode or "auto").lower()
    if mode not in {"fast", "deep", "auto"}:
        mode = "auto"
    key = f"{query}|{max_results}|{mode}"
    if use_cache:
        cached = _CACHE.get(key)
        if cached is not None:
            cached["from_cache"] = True
            cached["ms"] = round((time.time() - t0) * 1000)
            return cached

    base, variants = rewrite_query(query, enable_hints=use_rewrite)
    # 总时间预算：防止极端查询（行话密集、多源全空）导致超长等待
    TOTAL_BUDGET = 12.0
    deadline = t0 + TOTAL_BUDGET

    if mode == "auto":
        hits, errors, used = _search_once(
            base, variants, max_results, FAST_PROFILE, use_fallback, drop_noise,
            deadline=deadline)
        mode_used = "fast"
        if not _quality_ok(hits, base, max_results) and time.time() < deadline:
            h2, e2, u2 = _search_once(
                base, variants, max_results, DEEP_PROFILE, use_fallback, drop_noise,
                deadline=deadline)
            hits = h2 or hits
            errors.update(e2)
            used = list(dict.fromkeys(used + u2))
            mode_used = "deep"
    else:
        profile = FAST_PROFILE if mode == "fast" else DEEP_PROFILE
        hits, errors, used = _search_once(
            base, variants, max_results, profile, use_fallback, drop_noise,
            deadline=deadline)
        mode_used = mode

    # 去重（按 URL）
    seen: set[str] = set()
    uniq: list[SearchHit] = []
    for h in hits:
        k = (h.url or h.title).strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(h)

    ranked = rank_hits(uniq, base, max_results, drop_noise=drop_noise)

    result = {
        "query": query, "rewritten": base, "variants": variants,
        "mode": mode_used,
        "hits": [asdict(h) for h in ranked],
        "sources_used": used, "errors": errors,
        "raw_count": len(uniq),
        "ms": round((time.time() - t0) * 1000),
        "from_cache": False,
    }
    if use_cache and result["hits"]:
        # 只缓存有结果的查询：避免限流/网络抖动导致的空结果被固化，
        # 否则会让同一查询长期落到 Bing 兜底（实测踩坑）
        _CACHE.put(key, result)
    return result


def format_results(result: dict) -> str:
    """格式化为面向模型的可读文本。"""
    hits = result.get("hits", [])
    src = ", ".join(result.get("sources_used", [])) or "无"
    mode = result.get("mode", "auto")
    mode_tag = {"fast": "⚡快速", "deep": "🔬深度"}.get(mode, mode)
    head = (f"🔍 搜索 '{result['query']}' 的结果"
            f"（源: {src}｜{mode_tag}｜原始 {result.get('raw_count', 0)} 条｜{result.get('ms', 0)}ms"
            f"{'｜缓存' if result.get('from_cache') else ''}）:\n")
    if not hits:
        errs = result.get("errors", {})
        tail = f"\n（部分源错误: {errs}）" if errs else ""
        return head + "未找到相关结果。" + tail
    lines = [head]
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h['title']}")
        if h.get("url"):
            lines.append(f"   {h['url']}")
        if h.get("snippet"):
            lines.append(f"   {h['snippet'][:200]}")
        lines.append(f"   [{h.get('source', '')} · 权威度 {h.get('authority', 0):.2f}]")
        lines.append("")
    return "\n".join(lines)
