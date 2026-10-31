"""补充检索：effect systems / 依赖注入形式化 / agent harness 架构"""
import sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, urllib.parse, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (compatible; ResearchBot/1.0)"

def arxiv(query, max_results=4, retries=3):
    q = urllib.parse.quote(query)
    url = (f"http://export.arxiv.org/api/query?search_query={q}"
           f"&start=0&max_results={max_results}&sortBy=relevance")
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                xml = r.read().decode("utf-8", "replace")
            out = []
            for e in re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL):
                t = re.search(r"<title>(.*?)</title>", e, re.DOTALL)
                i = re.search(r"<id>(.*?)</id>", e, re.DOTALL)
                p = re.search(r"<published>(.*?)</published>", e, re.DOTALL)
                s = re.search(r"<summary>(.*?)</summary>", e, re.DOTALL)
                if t:
                    out.append({
                        "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t.group(1))).strip(),
                        "url": i.group(1).strip() if i else "",
                        "date": p.group(1)[:10] if p else "",
                        "abs": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s.group(1))).strip()[:220] if s else "",
                    })
            return out
        except Exception as e:
            last = e
            time.sleep(3 * (a + 1))
    return [{"error": f"{type(last).__name__}: {str(last)[:70]}"}]

for q in ['all:"algebraic effects" AND all:"effect handler"',
          'all:"agent harness"',
          'all:"capability" AND all:"dynamic composition" AND all:software']:
    print("=" * 76)
    print("QUERY:", q)
    print("=" * 76)
    for r in arxiv(q):
        if "error" in r:
            print("  ERROR:", r["error"]); continue
        print(f"  • [{r['date']}] {r['title'][:86]}")
        print(f"    {r['url']}")
        if r["abs"]:
            print(f"    {r['abs'][:170]}")
    print()
    time.sleep(2)
