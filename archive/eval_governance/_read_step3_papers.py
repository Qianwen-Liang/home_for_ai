"""深读步骤3 关键论文"""
import sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (compatible; ResearchBot/1.0)"

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

def clean(t):
    t = re.sub(r"<script.*?</script>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        t = t.replace(a, b)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()

PAPERS = [
    ("2411.05285", "AgentOps: Enabling Observability of LLM Agents"),
    ("2609.26836", "Silent Failures in Agent-Tool Interaction (ToolUniverse audit)"),
    ("2607.18754", "AgentDebugX: Failure Observability, Attribution, Recovery"),
    ("2608.02464", "Real-Time Detection and Repair of LLM Agent Failures"),
]
for pid, label in PAPERS:
    print("=" * 78)
    print(f"### {pid} — {label}")
    print("=" * 78)
    try:
        txt = clean(fetch(f"https://arxiv.org/abs/{pid}"))
        m = re.search(r"Abstract[:：]\s*(.*?)(?:Comments|Subjects|Cite as|Submission history)", txt, re.DOTALL)
        print(re.sub(r"\s+", " ", m.group(1)).strip()[:1500] if m else txt[:1100])
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:90])
    print()
    time.sleep(2)
