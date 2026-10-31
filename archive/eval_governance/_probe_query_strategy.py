import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.search_sources import GitHubSource, _simplify_query, _STOP_WORDS

GENERIC = {"agent","tool","tools","model","models","search","context","system",
           "framework","data","code","api","service","user","llm","ai"}
s = GitHubSource()

def variants(q):
    terms = [t for t in re.split(r"[\s,;\/]+", q) if t and t.lower() not in _STOP_WORDS]
    out = {
        "完整": q,
        "最长3": _simplify_query(q, 3),
        "去通用后最长3": " ".join(sorted([t for t in terms if t.lower() not in GENERIC],
                                    key=len, reverse=True)[:3]) or _simplify_query(q, 3),
        "去通用后最短3": " ".join(sorted([t for t in terms if t.lower() not in GENERIC],
                                    key=len)[:3]) or _simplify_query(q, 3),
        "前3词": " ".join(terms[:3]),
    }
    return out

QUERIES = [
    "JIT tool schema injection token bloat reduction agent",
    "agent tool registry lazy loading MCP gateway",
    "progressive tool discovery context window",
]
for q in QUERIES:
    print("=" * 76)
    print("Q:", q)
    for label, v in variants(q).items():
        try:
            n = len(s.search(v, 5))
            print(f"  {label:16} '{v[:52]:54}' -> {n} 条")
        except Exception as e:
            print(f"  {label:16} '{v[:52]:54}' -> {type(e).__name__}")
    print()
