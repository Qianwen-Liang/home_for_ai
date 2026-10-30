"""抓 open-telemetry/semantic-conventions-genai 新仓库"""
import sys, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl, json

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=30, accept="text/plain,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

REPO = "open-telemetry/semantic-conventions-genai"
print("=" * 78)
print("### 仓库结构")
print("=" * 78)
try:
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1",
                            accept="application/json"))
    paths = [t["path"] for t in tree.get("tree", [])
             if t["path"].endswith(".md") and t["type"] == "blob"]
    print(f"markdown 文件 {len(paths)} 个：")
    for p in paths[:40]:
        print("  ", p)
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:100])
