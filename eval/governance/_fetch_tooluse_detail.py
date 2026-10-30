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
# 找 Tool Search Tool 具体机制
i = txt.find("With th")
print("=" * 72)
print("### Tool Search Tool 机制")
print("=" * 72)
print(txt[i:i+2600] if i > 0 else txt[3500:6100])

print()
print("=" * 72)
print("### Programmatic Tool Calling")
print("=" * 72)
j = txt.find("Programmatic Tool Calling", txt.find("Programmatic Tool Calling") + 30)
print(txt[j:j+2600] if j > 0 else "未找到")

print()
print("=" * 72)
print("### Best practices / 关键结论")
print("=" * 72)
k = txt.find("Best practices", txt.find("Best practices") + 20)
print(txt[k:k+2200] if k > 0 else "未找到")
