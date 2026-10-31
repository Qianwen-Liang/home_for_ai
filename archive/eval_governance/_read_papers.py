"""深读关键论文：abstract + 核心结论"""
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
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]:
        t = t.replace(a, b)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()

PAPERS = [
    ("2608.25512", "A Programming Paradigm for Spatiotemporal Composability (Cordis 理论基础)"),
    ("2608.28553", "Composition without a Host (可逆性保证)"),
    ("2608.06370", "The Bitter Lesson of Tool Calling"),
]

for pid, label in PAPERS:
    print("=" * 78)
    print(f"### arXiv {pid} — {label}")
    print("=" * 78)
    try:
        txt = clean(fetch(f"https://arxiv.org/abs/{pid}"))
        m = re.search(r"Abstract[:：]\s*(.*?)(?:Comments|Subjects|Cite as|Submission history)", txt, re.DOTALL)
        abs_txt = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        print(abs_txt[:1500] if abs_txt else txt[:1200])
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:100])
    print()
    time.sleep(2)
