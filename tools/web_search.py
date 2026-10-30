"""
web_search — 联网搜索工具
=========================
基于 DuckDuckGo 的免费搜索，不需要 API Key。
支持网络搜索和获取搜索结果摘要。
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ── 错误类型 ──────────────────────────────────────────────


class WebSearchError(RuntimeError):
    """联网搜索错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "联网搜索工具。通过搜索引擎获取网络信息。"
            "支持搜索互联网内容，返回标题、链接和摘要。"
            "注意：此工具会消耗网络流量，请合理使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如 'Python 最新版本 2025'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，1-10，默认 5",
                    "default": 5,
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "fast", "deep"],
                    "description": (
                        "检索模式：auto=自动级联(默认，先快后深)；"
                        "fast=低延迟(≤2源/4s，适合简单查询)；"
                        "deep=高质量(全源/9s，适合复杂技术调研)"
                    ),
                    "default": "auto",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


# ── 搜索实现 ──────────────────────────────────────────────


def _create_ssl_context() -> ssl.SSLContext:
    """创建经过证书校验的现代 TLS 上下文。"""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _search_duckduckgo_html(query: str, max_results: int = 5) -> str:
    """使用 DuckDuckGo HTML 搜索接口（更可靠）。"""
    
    # 使用 DuckDuckGo 的标准 HTML 搜索
    params = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{params}"
    
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    
    try:
        ssl_context = _create_ssl_context()
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise WebSearchError(f"搜索服务返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # 主 HTML 端点被代理或网络策略阻断时，继续尝试 Lite 端点。
        fallback = _search_fallback(query, max_results)
        if not fallback.startswith("搜索 '") or "无法连接" not in fallback:
            return fallback
        raise WebSearchError(f"主端点和备用端点均不可用: {exc}") from exc
    
    # 解析 HTML 提取搜索结果
    results = _parse_duckduckgo_html_results(html, max_results)
    
    if not results:
        # 尝试备用搜索方式
        return _search_fallback(query, max_results)
    
    lines = [f"🔍 搜索 '{query}' 的结果:\n"]
    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['title']}")
        lines.append(f"   {result['url']}")
        if result.get("snippet"):
            lines.append(f"   {result['snippet'][:200]}")
        lines.append("")
    
    return "\n".join(lines)


def _parse_duckduckgo_html_results(html: str, max_results: int) -> list[dict[str, str]]:
    """从 DuckDuckGo HTML 搜索结果中提取信息。"""
    results: list[dict[str, str]] = []
    
    # DuckDuckGo HTML 搜索结果的典型结构：
    # <a rel="nofollow" class="result__a" href="...">标题</a>
    # <a class="result__snippet" ...>摘要</a>
    
    # 方法1：查找 result__a 类链接（主要搜索结果）
    # <a rel="nofollow" class="result__a" href="URL">TITLE</a>
    result_pattern = re.compile(
        r'<a\s+rel="nofollow"\s+class="result__a"\s+href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    
    # 查找摘要
    snippet_pattern = re.compile(
        r'<a\s+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    
    links = result_pattern.findall(html)
    snippets = snippet_pattern.findall(html)
    
    # 处理结果
    for i, (url, title) in enumerate(links):
        # 清理 HTML 标签
        title = re.sub(r'<[^>]+>', '', title).strip()
        if not title:
            continue
        
        # 获取摘要
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
        
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })
        
        if len(results) >= max_results:
            break
    
    # 如果方法1没找到，尝试方法2
    if not results:
        # 通用的链接提取方式
        link_pattern = re.compile(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        all_links = link_pattern.findall(html)
        
        # 过滤掉 DuckDuckGo 自身的链接
        for url, title in all_links:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if not title or any(skip in url for skip in [
                "duckduckgo.com", "safe.duckduckgo.com", 
                "twitter.com", "facebook.com", "javascript:"
            ]):
                continue
            results.append({
                "title": title,
                "url": url,
                "snippet": "",
            })
            if len(results) >= max_results:
                break
    
    return results


def _search_fallback(query: str, max_results: int = 5) -> str:
    """备用搜索方式：使用 DuckDuckGo Lite API。"""
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    
    try:
        ssl_context = _create_ssl_context()
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception:
        return f"❌ 搜索 '{query}' 时无法连接到搜索引擎，请检查网络连接。"
    
    # 解析 Lite 版结果
    results: list[dict[str, str]] = []
    
    # Lite 版本的结果在 <a rel="nofollow" href="..."> 中
    link_pattern = re.compile(
        r'<a\s+rel="nofollow"\s+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL
    )
    
    snippet_pattern = re.compile(
        r'<td\s+class="snippet"[^>]*>(.*?)</td>',
        re.DOTALL
    )
    
    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)
    
    for i, (url, title) in enumerate(links):
        title = re.sub(r'<[^>]+>', '', title).strip()
        if not title or "duckduckgo.com" in url:
            continue
        
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
        
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })
        
        if len(results) >= max_results:
            break
    
    if not results:
        return f"搜索 '{query}' 未找到结果。"
    
    lines = [f"🔍 搜索 '{query}' 的结果:\n"]
    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['title']}")
        lines.append(f"   {result['url']}")
        if result.get("snippet"):
            lines.append(f"   {result['snippet'][:200]}")
        lines.append("")
    
    return "\n".join(lines)


def _search_bing_rss(query: str, max_results: int = 5) -> str:
    """使用 Bing RSS 搜索接口（DuckDuckGo 被阻断时的备用引擎）。

    返回格式化搜索结果。Bing RSS 端点对低频查询更稳定，
    且在沙箱网络环境下实测可达（DuckDuckGo 的 HTML 端点可能超时）。
    """
    import xml.etree.ElementTree as ET

    params = urllib.parse.urlencode({"format": "rss", "q": query})
    url = f"https://cn.bing.com/search?{params}"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )

    try:
        ssl_context = _create_ssl_context()
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            xml_text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise WebSearchError(f"Bing 备用搜索不可用: {exc}") from exc

    # 解析 RSS
    results: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            if not title or not link:
                continue
            results.append({"title": title, "url": link, "snippet": desc})
            if len(results) >= max_results:
                break
    except ET.ParseError:
        # RSS 解析失败，正则兜底
        title_pattern = re.compile(r"<title>(.*?)</title>", re.DOTALL)
        link_pattern = re.compile(r"<link>(.*?)</link>", re.DOTALL)
        desc_pattern = re.compile(r"<description>(.*?)</description>", re.DOTALL)
        titles = [re.sub(r"<[^>]+>", "", t).strip() for t in title_pattern.findall(xml_text)]
        links = [l.strip() for l in link_pattern.findall(xml_text)]
        descs = [re.sub(r"<[^>]+>", "", d).strip() for d in desc_pattern.findall(xml_text)]
        # 跳过第一个（channel 级标题）
        for i in range(1, min(len(titles), len(links), max_results + 1)):
            results.append({
                "title": titles[i],
                "url": links[i],
                "snippet": descs[i] if i < len(descs) else "",
            })

    if not results:
        raise WebSearchError(f"Bing 搜索 '{query}' 未返回结果")

    lines = [f"🔍 搜索 '{query}' 的结果（Bing）:\n"]
    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['title']}")
        lines.append(f"   {result['url']}")
        if result.get("snippet"):
            lines.append(f"   {result['snippet'][:200]}")
        lines.append("")

    return "\n".join(lines)


# ── 工具入口 ──────────────────────────────────────────────

# 简单内存缓存：避免短时间内重复查询同一关键词（减少网络延迟）
_SEARCH_CACHE: dict[str, str] = {}
_SEARCH_CACHE_MAX = 20


def web_search(query: str, max_results: int = 5, mode: str = "auto") -> str:
    """执行联网搜索，返回格式化结果。

    v2.1 架构：联邦检索优先（领域权威源 + RRF 融合 + 重排 + 改写 + 缓存），
    Bing/DDG 降级为最后兜底。支持 fast / deep / auto 双模式。

    实测（28 查询基准，deep 模式）：P@5 0.407→0.893，Noise@5 0.250→0.000。
    """
    
    if not query or not query.strip():
        raise WebSearchError("搜索关键词不能为空")
    
    query = query.strip()
    try:
        max_results = int(max_results)
    except (TypeError, ValueError) as exc:
        raise WebSearchError("max_results 必须是整数") from exc
    max_results = max(1, min(10, max_results if max_results else 5))
    mode = (mode or "auto").lower()
    if mode not in {"auto", "fast", "deep"}:
        mode = "auto"

    # ── 主路径：联邦检索（权威源） ──
    try:
        from tools.search_router import federated_search, format_results
        fed = federated_search(query, max_results, mode=mode, use_cache=True)
        if fed.get("hits"):
            return format_results(fed)
    except Exception:  # noqa: BLE001
        pass  # 联邦检索异常时降级到通用引擎

    # ── 兜底路径：Bing RSS → DuckDuckGo（内存缓存） ──
    cache_key = f"{query}:{max_results}"
    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        result = _search_bing_rss(query, max_results)
    except WebSearchError:
        result = _search_duckduckgo_html(query, max_results)

    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
        _SEARCH_CACHE.clear()
    _SEARCH_CACHE[cache_key] = result

    # 明确标注：权威源未命中，这是低质量兜底（实测 Bing 易返回词典/百科）
    return ("⚠️ 权威源未命中，以下为通用引擎兜底结果（质量可能较低，建议改用 mode='deep' 或更精确的关键词）：\n\n"
            + result)


def execute_web_search_tool(arguments: dict[str, Any]) -> str:
    """执行 web_search 工具的入口函数。"""
    query = arguments.get("query", "")
    max_results = arguments.get("max_results", 5)
    mode = arguments.get("mode", "auto")

    try:
        return web_search(query, max_results, mode=mode)
    except WebSearchError as exc:
        return f"❌ 搜索错误: {exc}"
