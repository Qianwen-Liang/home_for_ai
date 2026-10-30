import sys, urllib.request, urllib.parse, ssl, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

def get(url, timeout=20, accept="text/html"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

def bing_rss(q, extra):
    url = f"https://cn.bing.com/search?format=rss&q={urllib.parse.quote(q)}{extra}"
    xml = get(url, accept="application/rss+xml")
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    out = []
    for it in items[:5]:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        out.append(re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else "")
    return len(items), out

Q = "context engineering agents"
print("=" * 66)
print("测试1: Bing RSS 市场/语言参数")
print("=" * 66)
for label, extra in [
    ("默认(cn)", ""),
    ("mkt=en-US", "&mkt=en-US"),
    ("setmkt=en-US&setlang=en", "&setmkt=en-US&setlang=en"),
    ("cc=us", "&cc=us"),
]:
    try:
        n, titles = bing_rss(Q, extra)
        noise = sum(1 for t in titles if any(x in t for x in ["词典", "百科", "翻译", "音标"]))
        print(f"\n[{label}] 共{n}条 噪音{noise}")
        for t in titles[:3]:
            print("   ", t[:72])
    except Exception as e:
        print(f"[{label}] FAIL {type(e).__name__}: {e}")
    time.sleep(1)

print()
print("=" * 66)
print("测试2: 其他搜索引擎可达性")
print("=" * 66)
def probe_mojeek(q):
    html = get("https://www.mojeek.com/search?q=" + urllib.parse.quote(q))
    res = re.findall(r'<a class="ob"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
    if not res:
        res = re.findall(r'<a[^>]+class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
    return len(html), [(u, re.sub(r"<[^>]+>", "", t).strip()) for u, t in res[:3]]

try:
    ln, res = probe_mojeek(Q)
    print(f"Mojeek: len={ln} results={len(res)}")
    for u, t in res:
        print("   ", t[:60], "|", u[:60])
except Exception as e:
    print("Mojeek FAIL:", type(e).__name__, e)

try:
    ln = len(get("https://search.marginalia.nu/search?query=" + urllib.parse.quote(Q)))
    print(f"Marginalia: len={ln} (可达)")
except Exception as e:
    print("Marginalia FAIL:", type(e).__name__, e)
