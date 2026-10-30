import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html",
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

def clean(html):
    t = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

txt = clean(fetch("https://www.anthropic.com/news/contextual-retrieval"))
print("=" * 70)
print("### Contextual Retrieval — 实施方案")
print("=" * 70)
i = txt.find("Introducing Contextual Retrieval")
i2 = txt.find("Introducing Contextual Retrieval", i + 10)  # 跳过目录
print(txt[i2 if i2 > 0 else i:][:3800])
print()
print("=" * 70)
print("### Reranking 部分")
print("=" * 70)
j = txt.find("Further boosting performance with Reranking")
j2 = txt.find("Further boosting performance with Reranking", j + 10)
print(txt[j2 if j2 > 0 else j:][:2500])
