import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/plain,text/html,*/*",
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

def clean(html):
    t = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

# 1) MCP llms.txt — 生态全貌
print("=" * 70)
print("### MCP llms.txt（文档索引/生态全貌）")
print("=" * 70)
try:
    txt = fetch("https://modelcontextprotocol.io/llms.txt", timeout=20)
    print("LEN", len(txt))
    print(txt[:2500])
except Exception as e:
    print("FAIL:", type(e).__name__, e)

# 2) Code execution — benefits 尾段（安全/状态管理）
print()
print("=" * 70)
print("### Code execution with MCP — 安全与状态管理收益")
print("=" * 70)
try:
    txt = clean(fetch("https://www.anthropic.com/engineering/code-execution-with-mcp"))
    for kw in ["Privacy-preserving", "State", "token-efficient", "Summary"]:
        i = txt.find(kw)
        if i > 0:
            print("---", kw, "---")
            print(txt[i:i+1200])
            break
except Exception as e:
    print("FAIL:", type(e).__name__, e)
