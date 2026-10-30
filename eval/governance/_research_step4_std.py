"""步骤4 工程标准侧：错误分类语义 + 重试策略"""
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
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]:
        t = t.replace(a, b)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()

print("=" * 78)
print("### gRPC 状态码语义（错误分类业界标准）")
print("=" * 78)
try:
    t = clean(fetch("https://grpc.io/docs/guides/status-codes/"))
    for kw in ["RETRYABLE", "retry", "UNAVAILABLE"]:
        j = t.find(kw)
        if j > 0:
            print(t[max(0, j-300):j+700])
            break
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 78)
print("### OTel 错误语义：error.type / exception 约定")
print("=" * 78)
try:
    t = fetch("https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-exceptions.md",
              accept="text/plain")
    print(re.sub(r"\n\s*\n+", "\n", t)[:1600])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 78)
print("### tenacity 重试策略设计（业界标准库，本地未安装）")
print("=" * 78)
try:
    t = fetch("https://raw.githubusercontent.com/jd/tenacity/main/README.rst", accept="text/plain")
    t = re.sub(r"<[^>]+>", "", t)
    print(re.sub(r"\n\s*\n+", "\n", t)[:1500])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])
