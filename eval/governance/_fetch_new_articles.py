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

TARGETS = [
    ("advanced-tool-use", "https://www.anthropic.com/engineering/advanced-tool-use"),
    ("long-running-harnesses", "https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents"),
]
for name, url in TARGETS:
    print("=" * 72)
    print("###", name)
    print("=" * 72)
    try:
        txt = clean(fetch(url))
        print("LEN", len(txt))
        print(txt[:4200])
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:100])
    print()
