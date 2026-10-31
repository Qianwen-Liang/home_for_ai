import sys, json, hashlib, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── 1) 记录当前 ALL_TOOLS 的字节基线（改造后必须一致）──
import agent1
payload = json.dumps(agent1.ALL_TOOLS, ensure_ascii=False, separators=(",", ":"))
print("── 当前 ALL_TOOLS 字节基线 ──")
print(f"  工具数: {len(agent1.ALL_TOOLS)}")
print(f"  紧凑序列化长度: {len(payload)}")
print(f"  sha256: {hashlib.sha256(payload.encode()).hexdigest()}")
print(f"  顺序: {[t['function']['name'] for t in agent1.ALL_TOOLS]}")

# ── 2) 抓 pluggy 设计（声明式注册标杆）──
import urllib.request, ssl
ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

print("\n── pluggy README 核心设计 ──")
for u in ["https://raw.githubusercontent.com/pytest-dev/pluggy/main/README.rst",
          "https://raw.githubusercontent.com/pytest-dev/pluggy/main/docs/index.rst"]:
    try:
        t = fetch(u)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\n\s*\n+", "\n\n", t)
        print(f"[{u.split('/')[-1]}]")
        print(t[:1800])
        break
    except Exception as e:
        print(f"[{u.split('/')[-1]}] {type(e).__name__}")
