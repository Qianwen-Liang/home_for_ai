"""抓取 OTel GenAI 规范核心文件，提取标准属性/指标/异常"""
import sys, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=30, accept="text/plain,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

BASE = "https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/"
FILES = [
    "docs/gen-ai/gen-ai-spans.md",
    "docs/gen-ai/gen-ai-metrics.md",
    "docs/gen-ai/gen-ai-exceptions.md",
    "docs/gen-ai/gen-ai-agent-spans.md",
]
for fn in FILES:
    print("=" * 78)
    print("###", fn)
    print("=" * 78)
    try:
        t = fetch(BASE + fn)
        attrs = sorted(set(re.findall(r"(gen_ai\.[a-z0-9_.]+)", t)))
        print(f"len={len(t)} | 唯一属性 {len(attrs)} 个")
        # 分组展示
        for pre in ["gen_ai.operation", "gen_ai.tool", "gen_ai.agent", "gen_ai.request",
                    "gen_ai.response", "gen_ai.usage", "gen_ai.provider", "gen_ai.conversation"]:
            grp = [a for a in attrs if a.startswith(pre)]
            if grp:
                print(f"  {pre}*: {', '.join(x.split('.',2)[-1] for x in grp[:8])}")
        others = [a for a in attrs if not any(a.startswith(p) for p in
                  ["gen_ai.operation", "gen_ai.tool", "gen_ai.agent", "gen_ai.request",
                   "gen_ai.response", "gen_ai.usage", "gen_ai.provider", "gen_ai.conversation"])]
        if others:
            print(f"  其他: {', '.join(others[:10])}")
        # 若有 metric / exception 名称
        mets = sorted(set(re.findall(r"`(gen_ai\.client\.[a-z_.]+|gen_ai\.server\.[a-z_.]+)`", t)))
        if mets:
            print(f"  metrics: {', '.join(mets[:10])}")
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:80])
    print()
    time.sleep(1)
