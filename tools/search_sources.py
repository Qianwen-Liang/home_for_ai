"""search_sources — 领域权威源联邦检索（Domain-Authoritative Federation）

设计动机（实测驱动）：
  通用搜索引擎在本环境已被证明不可靠：
    - Bing（cn/www, RSS/HTML）对英文技术查询退化为"首词词典匹配"
    - Bing 无视 site: 操作符
    - DuckDuckGo 两个端点均被 IP 级反爬封禁
    - SearXNG 公共实例 429/403/SSL 全挂
  但结构化权威源 API 实测 100% 可用且零噪音：
    - arXiv API / GitHub API / HuggingFace API / MCP llms.txt

因此本模块把"检索"从"通用引擎"转向"领域权威源联邦"，
通用引擎降级为最后的兜底。

统一契约：每个 Source 实现 search(query, n) -> list[SearchHit]
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 简化查询时剔除的停用词
_STOP_WORDS = {
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with",
    "is", "are", "how", "what", "vs", "versus", "best", "practice",
    "的", "了", "和", "与", "是", "怎么", "如何",
}

# MCP 文档最新版本（多版本去重基准）
_LATEST_MCP_VER = "2026-07-28"


class SourceError(RuntimeError):
    """单个源检索失败（不致命，由路由器降级处理）。"""


def _ssl_ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.minimum_version = ssl.TLSVersion.TLSv1_2
    return c


_CTX = _ssl_ctx()


def _http_get(url: str, timeout: float = 8.0, accept: str = "*/*") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        raise SourceError(f"{type(exc).__name__}: {exc}") from exc


def _simplify_query(query: str, max_terms: int = 3) -> str:
    """把长查询压缩为少量核心关键词（保留供外部调用）。

    注意：实测表明"取最长词"并非最佳策略——长词常是无区分度的泛词
    （如 injection/reduction），反而把关键术语挤掉。见 _query_candidates。
    """
    terms = [t for t in re.split(r"[\s,;\/]+", query) if t]
    keep = [t for t in terms if t.lower() not in _STOP_WORDS and len(t) > 1]
    if not keep:
        keep = terms
    keep.sort(key=len, reverse=True)
    return " ".join(keep[:max_terms])


def _query_candidates(query: str, n_terms: int = 3) -> list[str]:
    """生成查询候选序列，供结构化 API 逐级降级调用。

    实测（3 组查询 × 5 策略）结论：
      - 完整查询在多数情况召回最好；
      - "取最长 N 词"最差（长泛词挤掉关键术语，实测可致 0 召回）；
      - "取前 N 词"是稳定可靠的降级方案。
    因此策略为：完整查询优先 → 前 N 词兜底。
    """
    base = re.sub(r"\s+", " ", query).strip()
    terms = [t for t in re.split(r"[\s,;\/]+", base) if t]
    cands = [base]
    if len(terms) > n_terms:
        short = " ".join(terms[:n_terms])
        if short != base:
            cands.append(short)
    return cands


@dataclass
class SearchHit:
    """统一检索结果。"""
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    authority: float = 0.5      # 0..1 源权威度
    rank: int = 0               # 源内排名（1-based），用于 RRF

    def as_text(self) -> str:
        return f"{self.title} {self.url} {self.snippet}".lower()


class Source:
    """检索源基类。"""
    name: str = "base"
    domains: tuple[str, ...] = ()
    authority: float = 0.5
    # 触发词：查询命中这些词时提升该源优先级
    triggers: tuple[str, ...] = ()

    def search(self, query: str, n: int) -> list[SearchHit]:
        raise NotImplementedError

    def match_score(self, query: str) -> float:
        """查询与本源的相关度 0..1（0 表示不应路由到本源）。"""
        q = query.lower()
        if not self.triggers:
            return 0.0
        hit = sum(1 for t in self.triggers if t in q)
        return min(1.0, hit / 2.0)


# ─────────────────────────── arXiv ───────────────────────────

class ArxivSource(Source):
    """arXiv 官方 API —— 学术论文，零噪音。"""
    name = "arxiv"
    domains = ("arxiv.org",)
    authority = 0.95
    triggers = ("paper", "arxiv", "论文", "研究", "algorithm", "算法",
                "benchmark", "experiment", "experimental", "theorem")

    def search(self, query: str, n: int) -> list[SearchHit]:
        # arXiv 语法：all:"phrase"；去掉运算符与引号避免解析错误
        clean = re.sub(r'[:"()\[\]]', " ", query).strip()
        clean = re.sub(r"\s+", " ", clean)
        q = urllib.parse.quote(f'all:{clean}')
        url = (f"http://export.arxiv.org/api/query?search_query={q}"
               f"&start=0&max_results={max(1, min(n, 20))}&sortBy=relevance")
        xml = _http_get(url, timeout=3.5, accept="application/atom+xml")
        hits: list[SearchHit] = []
        for i, entry in enumerate(re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL), 1):
            t = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r'<id>(.*?)</id>', entry, re.DOTALL)
            summ = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            if not t:
                continue
            hits.append(SearchHit(
                title=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t.group(1))).strip(),
                url=(link.group(1).strip() if link else ""),
                snippet=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", summ.group(1))).strip()[:300] if summ else "",
                source=self.name, authority=self.authority, rank=i,
            ))
            if len(hits) >= n:
                break
        return hits


# ─────────────────────────── GitHub ───────────────────────────

class GitHubSource(Source):
    """GitHub 仓库搜索 API —— 代码仓库。

    注意：未认证 API 限流 60 次/小时。命中 403 后进入冷却期，
    期间直接返回空结果（避免每次请求都阻塞等待超时）。
    """
    name = "github"
    domains = ("github.com",)
    authority = 0.9
    triggers = ("github", "repo", "repository", "library", "开源", "仓库",
                "sdk", "framework", "框架", "package", "harness",
                "rag", "retrieval", "search", "fusion", "vector",
                "embedding", "rerank", "rrf", "bm25")

    _cooldown_until: float = 0.0   # 类级熔断时间戳
    COOLDOWN = 300.0               # 冷却 5 分钟

    def search(self, query: str, n: int) -> list[SearchHit]:
        import time as _t
        if _t.time() < GitHubSource._cooldown_until:
            return []   # 冷却期内静默跳过
        data = None
        # 完整查询优先 → 前 3 词兜底（实测最优策略）
        for cand in _query_candidates(query, 3):
            q = urllib.parse.quote(cand)
            url = (f"https://api.github.com/search/repositories?q={q}"
                   f"&per_page={max(1, min(n, 20))}&sort=stars")
            try:
                raw = _http_get(url, timeout=3.5, accept="application/json")
            except SourceError as exc:
                if "403" in str(exc):
                    GitHubSource._cooldown_until = _t.time() + GitHubSource.COOLDOWN
                    raise SourceError("GitHub API 限流(403)，进入 5 分钟冷却") from exc
                raise
            try:
                d = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SourceError(f"GitHub JSON 解析失败: {exc}") from exc
            if d.get("items"):
                data = d
                break
        if data is None:
            return []
        hits: list[SearchHit] = []
        for i, it in enumerate(data.get("items", [])[:n], 1):
            hits.append(SearchHit(
                title=f"{it.get('full_name', '')} — {it.get('description') or ''}"[:160],
                url=it.get("html_url", ""),
                snippet=(it.get("description") or "")[:300],
                source=self.name, authority=self.authority, rank=i,
            ))
        return hits


# ─────────────────────── HuggingFace ───────────────────────

class HuggingFaceSource(Source):
    """HuggingFace 模型搜索 API。"""
    name = "huggingface"
    domains = ("huggingface.co",)
    authority = 0.88
    triggers = ("model", "模型", "embedding", "llm", "checkpoint",
                "minilm", "bert", "transformer", "weights")

    def search(self, query: str, n: int) -> list[SearchHit]:
        data = None
        for cand in _query_candidates(query, 2):
            q = urllib.parse.quote(cand)
            url = f"https://huggingface.co/api/models?search={q}&limit={max(1, min(n, 20))}"
            raw = _http_get(url, timeout=3.5, accept="application/json")
            try:
                d = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SourceError(f"HF JSON 解析失败: {exc}") from exc
            if isinstance(d, list) and d:
                data = d
                break
        if not data:
            return []
        hits: list[SearchHit] = []
        for i, it in enumerate(data[:n], 1):
            mid = it.get("modelId", "")
            hits.append(SearchHit(
                title=f"{mid} — HuggingFace model",
                url=f"https://huggingface.co/{mid}" if mid else "",
                snippet=f"downloads={it.get('downloads', 0)} likes={it.get('likes', 0)}",
                source=self.name, authority=self.authority, rank=i,
            ))
        return hits


# ────────────────────────── MCP 文档 ──────────────────────────

class MCPDocsSource(Source):
    """MCP 官方文档索引（llms.txt）—— 协议规范检索。"""
    name = "mcp-docs"
    domains = ("modelcontextprotocol.io",)
    authority = 0.95
    triggers = ("mcp", "model context protocol", "协议", "protocol",
                "specification", "规范", "sep", "registry")
    _INDEX_URL = "https://modelcontextprotocol.io/llms.txt"

    def search(self, query: str, n: int) -> list[SearchHit]:
        txt = _http_get(self._INDEX_URL, timeout=3.5, accept="text/plain")
        terms = [t for t in re.split(r"\s+", query.lower()) if len(t) > 2]
        scored: list[tuple[float, int, str]] = []
        for line in txt.splitlines():
            m = re.match(r"-\s*\[([^\]]+)\]\(([^)]+)\)", line.strip())
            if not m:
                continue
            title, url = m.group(1), m.group(2)
            low = (title + " " + url).lower()
            # 多版本去重：/docs/ 与 /specification/ 下均只保留最新稳定版本
            if "/draft/" in url:
                continue
            mv = re.search(r"/(?:docs|specification)/(\d{4}-\d{2}-\d{2})/", url)
            if mv and mv.group(1) != _LATEST_MCP_VER:
                continue
            sc = sum(1 for t in terms if t in low)
            if sc > 0:
                scored.append((sc, len(title), title, url))
        scored.sort(key=lambda x: (-x[0], x[1]))
        hits: list[SearchHit] = []
        for i, (sc, _ln, title, url) in enumerate(scored[:n], 1):
            hits.append(SearchHit(
                title=title, url=url,
                snippet=f"MCP 官方文档（匹配度 {sc}）",
                source=self.name, authority=self.authority, rank=i,
            ))
        return hits


# ───────────────────── Stack Overflow ─────────────────────

class StackOverflowSource(Source):
    """Stack Overflow 官方 API —— 编程问答。"""
    name = "stackoverflow"
    domains = ("stackoverflow.com",)
    authority = 0.8
    triggers = ("error", "exception", "报错", "异常", "how to", "怎么",
                "python", "javascript", "traceback", "bug")

    def search(self, query: str, n: int) -> list[SearchHit]:
        data = None
        for cand in _query_candidates(query, 4):
            q = urllib.parse.quote(cand)
            url = (f"https://api.stackexchange.com/2.3/search/advanced?order=desc"
                   f"&sort=relevance&q={q}&site=stackoverflow&pagesize={max(1, min(n, 15))}")
            raw = _http_get(url, timeout=3.5, accept="application/json")
            try:
                d = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SourceError(f"SO JSON 解析失败: {exc}") from exc
            if d.get("items"):
                data = d
                break
        if data is None:
            return []
        hits: list[SearchHit] = []
        for i, it in enumerate(data.get("items", [])[:n], 1):
            hits.append(SearchHit(
                title=re.sub(r"<[^>]+>", "", it.get("title", "")),
                url=it.get("link", ""),
                snippet=f"score={it.get('score', 0)} answers={it.get('answer_count', 0)}",
                source=self.name, authority=self.authority, rank=i,
            ))
        return hits


# ─────────────────────── Wikipedia ───────────────────────

class WikipediaSource(Source):
    """Wikipedia 搜索 API —— 概念性查询兜底。"""
    name = "wikipedia"
    domains = ("wikipedia.org",)
    authority = 0.7
    triggers = ("what is", "什么是", "定义", "definition", "概念", "concept")

    def search(self, query: str, n: int) -> list[SearchHit]:
        q = urllib.parse.quote(query)
        url = (f"https://en.wikipedia.org/w/api.php?action=query&list=search"
               f"&srsearch={q}&format=json&srlimit={max(1, min(n, 15))}")
        raw = _http_get(url, timeout=3.5, accept="application/json")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SourceError(f"Wiki JSON 解析失败: {exc}") from exc
        hits: list[SearchHit] = []
        for i, it in enumerate(data.get("query", {}).get("search", [])[:n], 1):
            title = it.get("title", "")
            hits.append(SearchHit(
                title=f"{title} — Wikipedia",
                url=f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                snippet=re.sub(r"<[^>]+>", "", it.get("snippet", ""))[:300],
                source=self.name, authority=self.authority, rank=i,
            ))
        return hits


# ─────────────────────── 通用引擎兜底 ───────────────────────

class BingFallbackSource(Source):
    """Bing RSS 兜底源 —— 仅在权威源无结果时启用。

    实测局限（记录于 knowledge）：对英文技术长查询会退化为
    "首词词典匹配"，故 authority 设为最低，且由路由器最后调用。
    """
    name = "bing"
    domains = ("bing.com",)
    authority = 0.35
    triggers = ()   # 不主动路由，仅兜底

    def search(self, query: str, n: int) -> list[SearchHit]:
        params = urllib.parse.urlencode({"format": "rss", "q": query})
        xml = _http_get(f"https://cn.bing.com/search?{params}", timeout=3.5,
                        accept="application/rss+xml")
        hits: list[SearchHit] = []
        for i, item in enumerate(re.findall(r"<item>(.*?)</item>", xml, re.DOTALL), 1):
            t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            lnk = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            d = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
            if not t or not lnk:
                continue
            hits.append(SearchHit(
                title=re.sub(r"<[^>]+>", "", t.group(1)).strip(),
                url=lnk.group(1).strip(),
                snippet=re.sub(r"<[^>]+>", "", d.group(1)).strip()[:300] if d else "",
                source=self.name, authority=self.authority, rank=i,
            ))
            if len(hits) >= n:
                break
        return hits


# ─────────────────────── 源注册表 ───────────────────────

ALL_SOURCES: list[Source] = [
    ArxivSource(),
    GitHubSource(),
    HuggingFaceSource(),
    MCPDocsSource(),
    StackOverflowSource(),
    WikipediaSource(),
]

FALLBACK_SOURCES: list[Source] = [BingFallbackSource()]


def registry_summary() -> str:
    """输出源注册表概览。"""
    lines = ["📚 权威源注册表", "-" * 52]
    for s in ALL_SOURCES + FALLBACK_SOURCES:
        tag = "兜底" if s in FALLBACK_SOURCES else "权威"
        lines.append(f"  [{tag}] {s.name:14} authority={s.authority:.2f} "
                     f"triggers={len(s.triggers)} {','.join(s.triggers[:4])}")
    return "\n".join(lines)
