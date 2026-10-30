import sys, re, urllib.request, urllib.parse, ssl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def raw_ddg(q):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

for q in ["检索增强生成 混合检索 BM25", "reciprocal rank fusion RRF", "context engineering agents"]:
    print("=" * 66)
    print("QUERY:", q)
    try:
        html = raw_ddg(q)
        anomaly = len(re.findall(r"anomaly|challenge", html, re.I))
        res_a = len(re.findall(r'class="result__a"', html))
        print(f"  长度 {len(html)} | anomaly标记 {anomaly} | result__a {res_a}")
        if anomaly > 3 and res_a == 0:
            print("  → 判定: 被反爬验证码拦截")
        elif res_a > 0:
            print("  → 判定: 正常返回结果")
            titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)[:3]
            for t in titles:
                print("    -", re.sub(r"<[^>]+>", "", t).strip()[:70])
        else:
            print("  → 判定: 无结果页（可能真无结果或结构变化）")
    except Exception as e:
        print("  FAIL:", type(e).__name__, e)
    print()
