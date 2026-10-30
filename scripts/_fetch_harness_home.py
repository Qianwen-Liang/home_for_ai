import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html",
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

def clean(html):
    t = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

base = "https://deepseek-harness.github.io/deepseek-harness/"

# 1) 首页
try:
    html = fetch(base)
    print("=== 首页内容 ===")
    print(clean(html)[:2500])
    print()
    print("=== 导航链接 ===")
    links = re.findall(r'href="([^"]*deepseek-harness/[^"]*)"[^>]*>([^<]*)<', html)
    seen = set()
    for u, t in links:
        t2 = t.strip()
        if not t2 or (u, t2) in seen:
            continue
        seen.add((u, t2))
        print(u, "|", t2)
except Exception as e:
    print("首页 FAIL:", type(e).__name__, e)
