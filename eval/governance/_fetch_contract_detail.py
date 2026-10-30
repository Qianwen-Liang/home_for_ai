import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=25, accept="text/markdown,text/plain,text/html,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

def clean(t):
    t = re.sub(r"<script.*?</script>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")]:
        t = t.replace(a, b)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()

t = clean(fetch("https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md"))
print("=" * 74)
print("### MCP: isError / outputSchema / 错误处理")
print("=" * 74)
for kw in ["isError", "Structured Content", "outputSchema", "Error Handling"]:
    j = t.find(kw)
    if j > 0:
        print(f"\n--- {kw} ---")
        print(t[j:j + 900])
        print()

print("=" * 74)
print("### Hypothesis 核心思想（README）")
print("=" * 74)
try:
    h = fetch("https://raw.githubusercontent.com/HypothesisWorks/hypothesis/master/README.rst")
    h = re.sub(r"<[^>]+>", "", h)
    print(h[:2200])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])
