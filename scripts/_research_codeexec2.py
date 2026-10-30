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

def clean(html):
    t = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

# Code execution 文章：正文中段（方案细节）
print("=" * 70)
print("### Code execution with MCP — 方案细节（正文中段）")
print("=" * 70)
try:
    txt = clean(fetch("https://www.anthropic.com/engineering/code-execution-with-mcp"))
    i = txt.find("With code execution")
    if i < 0:
        i = txt.find("Instead of")
    if i < 0:
        i = 3500
    print(txt[i:i+4200])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
