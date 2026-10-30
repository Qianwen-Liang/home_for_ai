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
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

# 1) Code execution with MCP — 方案部分
print("=" * 70)
print("### [1] Code execution with MCP — 核心方案")
print("=" * 70)
try:
    txt = clean(fetch("https://www.anthropic.com/engineering/code-execution-with-mcp"))
    i = txt.find("Code execution with MCP improves context efficiency")
    j = txt.find("View more")
    print(txt[i:j if j > i else i+5000][:5000])
except Exception as e:
    print("FAIL:", type(e).__name__, e)

# 2) Context engineering — 核心论点
print()
print("=" * 70)
print("### [2] Effective Context Engineering — 核心论点")
print("=" * 70)
try:
    txt = clean(fetch("https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents"))
    i = txt.find("The anatomy of effective context")
    if i < 0:
        i = txt.find("Context retrieval")
    print(txt[i:i+4000] if i > 0 else txt[2000:5500])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
