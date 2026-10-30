import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=20):
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
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

targets = [
    ("Anthropic: Building Effective Agents", "https://www.anthropic.com/engineering/building-effective-agents"),
    ("Anthropic: Effective Context Engineering", "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents"),
    ("MCP 官方首页", "https://modelcontextprotocol.io/"),
]

for name, url in targets:
    print("=" * 70)
    print("### " + name)
    print("URL:", url)
    print("=" * 70)
    try:
        html = fetch(url)
        txt = clean(html)
        print("LEN", len(txt))
        print(txt[:1800])
    except Exception as e:
        print("FAIL:", type(e).__name__, e)
    print()
