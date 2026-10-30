"""web_search 质量基准测试 — 量化当前搜索能力的真实短板"""
import sys, time
sys.path.insert(0, '.')
from tools.web_search import _search_bing_rss, _search_duckduckgo_html, WebSearchError

# 技术类查询：理想结果应包含技术关键词
CASES = [
    ("context engineering agents", ["context", "agent", "token", "retrieval"]),
    ("RAG hybrid search BM25", ["bm25", "retrieval", "search", "hybrid"]),
    ("MCP model context protocol", ["mcp", "protocol", "server", "tool"]),
    ("DeepSeek Harness", ["deepseek", "harness", "agent", "plugin"]),
]

def score(text, kws):
    low = text.lower()
    hits = sum(1 for k in kws if k in low)
    return hits, len(kws)

print("=" * 72)
print("搜索质量基准：Bing RSS（当前主引擎）")
print("=" * 72)
for q, kws in CASES:
    t0 = time.time()
    try:
        out = _search_bing_rss(q, 6)
        cost = time.time() - t0
        hits, total = score(out, kws)
        # 检测词典/百科类噪音
        noise = sum(1 for n in ["词典", "百科", "翻译", "dictionary", "baike"] if n in out.lower())
        print(f"\n[{q}]")
        print(f"  耗时 {cost*1000:.0f}ms | 技术词命中 {hits}/{total} | 噪音源 {noise}")
        # 打印前3条标题
        lines = [l.strip() for l in out.splitlines() if l.strip().startswith(tuple("123456"))]
        for l in lines[:3]:
            print("   ", l[:100])
    except WebSearchError as e:
        print(f"\n[{q}] FAIL: {e}")
