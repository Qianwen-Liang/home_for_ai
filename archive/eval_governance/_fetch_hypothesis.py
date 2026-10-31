import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=25, accept="text/plain,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

print("=" * 74)
print("### Hypothesis README（属性测试核心思想）")
print("=" * 74)
for u in ["https://raw.githubusercontent.com/HypothesisWorks/hypothesis/master/README.rst",
          "https://raw.githubusercontent.com/HypothesisWorks/hypothesis/master/README.md"]:
    try:
        h = fetch(u)
        h = re.sub(r"<[^>]+>", "", h)
        h = re.sub(r"\n\s*\n+", "\n\n", h)
        print(h[:2400])
        break
    except Exception as e:
        print(f"[{u.split('/')[-1]}] {type(e).__name__}: {str(e)[:60]}")
