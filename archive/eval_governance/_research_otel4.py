import sys, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=30, accept="text/plain,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

REPO = "open-telemetry/semantic-conventions-genai"
tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1",
                        accept="application/json"))
docs = [t["path"] for t in tree.get("tree", [])
        if t["path"].startswith("docs/") and t["path"].endswith(".md")]
print(f"docs/ 下 markdown {len(docs)} 个：")
for p in docs:
    print("  ", p)
