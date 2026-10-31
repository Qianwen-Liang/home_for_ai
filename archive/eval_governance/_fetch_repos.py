import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import urllib.request, ssl

ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")

REPOS = [
    ("SkillPrism (96.7% token 削减)", "RitualDev-Lab/SkillPrism"),
    ("aigent-os (context capsule 替代 compaction)", "wrg32786/aigent-os"),
    ("dsh-progressive-tools (DeepSeek Harness 渐进工具)", "everclear077/dsh-progressive-tools"),
]
for label, repo in REPOS:
    print("=" * 74)
    print("###", label, "|", repo)
    print("=" * 74)
    got = False
    for branch in ("main", "master"):
        for fn in ("README.md", "readme.md"):
            try:
                txt = fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/{fn}")
                # 去掉 HTML 与徽章
                txt = re.sub(r"<[^>]+>", "", txt)
                txt = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", txt)
                txt = re.sub(r"\n\s*\n+", "\n", txt)
                print(txt[:1800])
                got = True
                break
            except Exception:
                continue
        if got:
            break
    if not got:
        print("(README 获取失败)")
    print()
