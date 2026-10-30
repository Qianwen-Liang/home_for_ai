import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,text/markdown,*/*",
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

pages = [
    ("MCP-Memory", "https://deepseek-harness.github.io/deepseek-harness/guide/mcp-memory"),
    ("Schedule", "https://deepseek-harness.github.io/deepseek-harness/guide/schedule"),
    ("Python-SDK", "https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk"),
    ("Plugin-Market", "https://deepseek-harness.github.io/deepseek-harness/guide/plugin-market"),
    ("GitHub-Review", "https://deepseek-harness.github.io/deepseek-harness/guide/github-review"),
]

for name, url in pages:
    print("=" * 70)
    print("### " + name)
    print("=" * 70)
    try:
        html = fetch(url)
        txt = clean(html)
        # 去掉公共导航前缀，保留正文
        print(txt[:2200])
    except Exception as e:
        print("FAIL:", type(e).__name__, e)
    print()
