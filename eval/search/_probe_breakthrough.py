import sys, time, re, urllib.request, urllib.parse, ssl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.web_search import _search_bing_rss, WebSearchError

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

print("=" * 68)
print("路径1: Bing 的 site: 限定搜索（能否排除词典站？）")
print("=" * 68)
for q in [
    "context engineering agents site:anthropic.com",
    "MCP specification site:modelcontextprotocol.io",
    "reciprocal rank fusion site:arxiv.org",
    "hybrid retrieval BM25 site:arxiv.org",
]:
    try:
        out = _search_bing_rss(q, 5)
        noise = sum(1 for n in ["词典", "百科", "翻译", "特斯拉"] if n in out)
        lines = [l.strip() for l in out.splitlines() if re.match(r"^\d+\.", l.strip())]
        print(f"\n[{q[:50]}] 噪音={noise}")
        for l in lines[:3]:
            print("   ", l[:78])
    except WebSearchError as e:
        print(f"[{q[:50]}] FAIL {e}")

print()
print("=" * 68)
print("路径2: DuckDuckGo Lite 端点（不同限流策略？）")
print("=" * 68)
def ddg_lite(q):
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({"q": q}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        html = r.read().decode("utf-8", "replace")
    anomaly = len(re.findall(r"anomaly|challenge", html, re.I))
    links = len(re.findall(r'rel="nofollow"', html))
    return len(html), anomaly, links

for q in ["context engineering agents", "reciprocal rank fusion RRF"]:
    try:
        ln, an, lk = ddg_lite(q)
        print(f"[{q[:40]:42}] len={ln} anomaly={an} links={lk}")
    except Exception as e:
        print(f"[{q[:40]:42}] FAIL {type(e).__name__}: {e}")

print()
print("=" * 68)
print("路径3: 等待后 DDG HTML 是否恢复（限流是否时序性）")
print("=" * 68)
def ddg_html_state(q):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        html = r.read().decode("utf-8", "replace")
    return len(re.findall(r"anomaly", html, re.I)), len(re.findall(r'class="result__a"', html))

for wait in [0, 8]:
    if wait:
        print(f"  等待 {wait}s ...")
        time.sleep(wait)
    try:
        an, ra = ddg_html_state("context engineering agents")
        print(f"  等待{wait}s后: anomaly={an} result__a={ra} → {'正常' if ra>0 else '被拦截'}")
    except Exception as e:
        print("  FAIL", e)
