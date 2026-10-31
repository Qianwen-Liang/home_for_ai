import urllib.request, urllib.parse, ssl, re, json
ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

def get(url, timeout=20, accept="text/html,*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

print("=" * 68)
print("A. arXiv 官方 API（结构化，无词典噪音）")
print("=" * 68)
try:
    url = "http://export.arxiv.org/api/query?search_query=all:%22context%20engineering%22&max_results=3"
    xml = get(url)
    titles = re.findall(r"<title>(.*?)</title>", xml, re.DOTALL)[1:]
    print(f"len={len(xml)} 条数={len(titles)}")
    for t in titles[:3]:
        print("   ", re.sub(r"\s+", " ", t).strip()[:75])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 68)
print("B. GitHub 仓库搜索 API")
print("=" * 68)
try:
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote("agent harness") + "&per_page=3"
    data = json.loads(get(url, accept="application/json"))
    print(f"total={data.get('total_count')}")
    for it in data.get("items", [])[:3]:
        print(f"   {it['full_name']:42} ★{it['stargazers_count']}")
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 68)
print("C. HuggingFace 模型搜索 API")
print("=" * 68)
try:
    url = "https://huggingface.co/api/models?search=" + urllib.parse.quote("minilm") + "&limit=3"
    data = json.loads(get(url, accept="application/json"))
    print(f"条数={len(data)}")
    for it in data[:3]:
        print("   ", it.get("modelId", ""))
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 68)
print("D. MCP 官方 llms.txt 文档索引")
print("=" * 68)
try:
    txt = get("https://modelcontextprotocol.io/llms.txt", accept="text/plain")
    hits = [l for l in txt.splitlines() if "specification" in l.lower() or "architecture" in l.lower()]
    print(f"总行数={len(txt.splitlines())} | 匹配行={len(hits)}")
    for h in hits[:3]:
        print("   ", h[:90])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])

print()
print("=" * 68)
print("E. Anthropic 工程博客列表页")
print("=" * 68)
try:
    html = get("https://www.anthropic.com/engineering")
    arts = re.findall(r'href="(/engineering/[a-z0-9\-]+)"', html)
    uniq = list(dict.fromkeys(arts))
    print(f"len={len(html)} 文章链接={len(uniq)}")
    for a in uniq[:5]:
        print("   ", a)
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:80])
