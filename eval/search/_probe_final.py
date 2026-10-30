import urllib.request, urllib.parse, ssl, re, time

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get(url, timeout=20, accept="text/html"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

Q = "context engineering agents"
print("=" * 68)
print("测试A: Bing 国际站 HTML 端点")
print("=" * 68)
for label, url in [
    ("www.bing.com HTML", f"https://www.bing.com/search?q={urllib.parse.quote(Q)}&setlang=en"),
    ("cn.bing.com HTML", f"https://cn.bing.com/search?q={urllib.parse.quote(Q)}&setlang=en"),
]:
    try:
        html = get(url)
        # Bing HTML 结果通常是 <h2><a href="...">标题</a></h2>
        titles = re.findall(r'<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>', html, re.DOTALL)
        noise = sum(1 for _, t in titles if any(x in t for x in ["词典", "百科", "翻译"]))
        print(f"\n[{label}] len={len(html)} 结果={len(titles)} 噪音={noise}")
        for u, t in titles[:4]:
            print("   ", re.sub(r"<[^>]+>", "", t).strip()[:70])
    except Exception as e:
        print(f"[{label}] FAIL {type(e).__name__}: {e}")
    time.sleep(1)

print()
print("=" * 68)
print("测试B: SearXNG 公共实例")
print("=" * 68)
INSTANCES = [
    "https://searx.be",
    "https://search.bus-hit.me",
    "https://priv.au",
    "https://searxng.site",
    "https://search.inetol.net",
]
for base in INSTANCES:
    try:
        url = f"{base}/search?q={urllib.parse.quote(Q)}&format=json"
        raw = get(url, timeout=12, accept="application/json")
        import json as _j
        data = _j.loads(raw)
        results = data.get("results", [])
        noise = sum(1 for r in results[:5] if any(x in (r.get("title","")+r.get("url","")) for x in ["词典","百科","dictionary"]))
        print(f"\n[{base}] JSON可用 结果={len(results)} 噪音={noise}")
        for r in results[:3]:
            print("   ", r.get("title","")[:65])
    except Exception as e:
        print(f"[{base}] FAIL {type(e).__name__}: {str(e)[:70]}")
