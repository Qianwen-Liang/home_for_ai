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

for pid, label in [
    ("2601.03258", "Two-Stage Retrieval + FlashRank Reranking"),
    ("2604.17738", "Mira-Embeddings: recall under limited review budget"),
    ("2109.10739", "Dense vs Sparse retrieval efficiency/effectiveness trade-offs"),
]:
    print("=" * 78)
    print(f"### {pid} — {label}")
    print("=" * 78)
    try:
        txt = clean(fetch(f"https://arxiv.org/abs/{pid}"))
        m = re.search(r"Abstract[:：]\s*(.*?)(?:Comments|Subjects|Cite as|Submission history)", txt, re.DOTALL)
        print(re.sub(r"\s+", " ", m.group(1)).strip()[:1400] if m else txt[:1000])
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:90])
    print()
    time.sleep(2)
