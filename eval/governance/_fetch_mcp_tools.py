import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=25, accept="text/html,*/*"):
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

print("=" * 74)
print("### MCP 规范：工具（Tools）契约定义")
print("=" * 74)
for url in ["https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md",
            "https://modelcontextprotocol.io/docs/2026-07-28/learn/server-concepts.md"]:
    try:
        t = clean(fetch(url, accept="text/markdown,text/plain,text/html"))
        i = t.find("Tool")
        print(f"\n[{url.split('/')[-1]}] len={len(t)}")
        # 找 inputSchema / outputSchema 相关段落
        for kw in ["inputSchema", "outputSchema", "tools/list", "isError", "annotations"]:
            j = t.find(kw)
            if j > 0:
                print(f"\n--- 命中 {kw} ---")
                print(t[max(0, j-260):j+700])
                break
    except Exception as e:
        print(f"[{url.split('/')[-1]}] FAIL {type(e).__name__}: {str(e)[:80]}")
