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

html = fetch("https://deepseek-harness.github.io/deepseek-harness/guide/quickstart")
links = re.findall(r'href="([^"]+)"[^>]*>([^<]*)<', html)
seen = set()
print("=== 全部站内链接 ===")
for u, t in links:
    t2 = t.strip()
    if not u.startswith("http") and not u.startswith("/"):
        continue
    if "deepseek-harness" not in u and not u.startswith("/"):
        continue
    key = (u, t2)
    if key in seen:
        continue
    seen.add(key)
    print(u, "|", t2)
