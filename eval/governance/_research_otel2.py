"""抓 OpenTelemetry semconv GenAI 规范源文件（GitHub raw）+ 两篇治理遥测论文"""
import sys, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=30, accept="text/plain,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

BASE = "https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/docs/gen-ai/"
FILES = ["README.md", "gen-ai-spans.md", "gen-ai-metrics.md", "gen-ai-agent-spans.md"]

for fn in FILES:
    print("=" * 78)
    print("###", fn)
    print("=" * 78)
    try:
        t = fetch(BASE + fn)
        # 提取 gen_ai.* 属性名
        attrs = sorted(set(re.findall(r"`?(gen_ai\.[a-z_.]+)`?", t)))
        print(f"len={len(t)} | 属性数={len(attrs)}")
        print("属性样例:", ", ".join(attrs[:18]))
        # 打印开头
        head = re.sub(r"\n\s*\n+", "\n", t)
        print("\n--- 开头 ---")
        print(head[:700])
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:80])
    print()
    time.sleep(1)
