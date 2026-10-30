import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,text/plain,*/*",
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

# 1) GitHub README.zh.md 原始内容
print("=" * 70)
print("### GitHub README.zh.md")
print("=" * 70)
try:
    md = fetch("https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/README.zh.md")
    print("LEN", len(md))
    print(md[:5000])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
