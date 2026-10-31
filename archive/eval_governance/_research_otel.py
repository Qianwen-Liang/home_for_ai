"""步骤3：工程标准侧 — OpenTelemetry GenAI 语义约定 + 治理遥测论文"""
import sys, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
def fetch(url, timeout=30, accept="text/html,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

def clean(t):
    t = re.sub(r"<script.*?</script>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        t = t.replace(a, b)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()

print("=" * 78)
print("### OpenTelemetry GenAI 语义约定（业界标准）")
print("=" * 78)
for url in ["https://opentelemetry.io/docs/specs/semconv/gen-ai/",
            "https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/"]:
    try:
        t = clean(fetch(url))
        print(f"\n[{url.split('/')[-2]}] len={len(t)}")
        # 找关键属性名
        for kw in ["gen_ai.operation.name", "gen_ai.tool.name", "gen_ai.agent",
                   "execute_tool", "invoke_agent", "metrics"]:
            j = t.find(kw)
            if j > 0:
                print(f"\n--- 命中 {kw} ---")
                print(t[max(0, j-200):j+520])
                break
    except Exception as e:
        print(f"[{url}] FAIL {type(e).__name__}: {str(e)[:70]}")
    time.sleep(1)
