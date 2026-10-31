import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl, re

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
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

txt = clean(fetch("https://www.anthropic.com/engineering/advanced-tool-use"))
print("=" * 72)
print("### Programmatic Tool Calling 详细机制")
print("=" * 72)
i = txt.find("Programmatic Tool Calling", 3000)
print(txt[i:i+2800] if i > 0 else "未找到")

print()
print("=" * 72)
print("### Tool Use Examples")
print("=" * 72)
j = txt.find("Tool Use Examples", 5000)
print(txt[j:j+1800] if j > 0 else "未找到")

# MCP Client Best Practices
print()
print("=" * 72)
print("### MCP: Client Best Practices")
print("=" * 72)
try:
    mt = clean(fetch("https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices.md"))
    k = mt.find("Back to top")
    print(mt[k:k+3000] if k > 0 else mt[:3000])
except Exception as e:
    print("MCP FAIL:", type(e).__name__, str(e)[:100])
