import urllib.request, ssl, re, sys

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html",
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

html = fetch("https://api-docs.deepseek.com/zh-cn/quick_start/pricing")
links = re.findall(r'href="([^"]*)"[^>]*>([^<]*)<', html)
print("=== harness/agent related links ===")
seen = set()
for u, t in links:
    t2 = t.strip()
    if not t2:
        continue
    if "harness" in u.lower() or "harness" in t2.lower() or "agent" in u.lower() or "agent" in t2.lower():
        key = (u, t2)
        if key in seen:
            continue
        seen.add(key)
        print(u, "|", t2)
