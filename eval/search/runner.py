"""搜索质量评测执行器 —— 确定性评分，可复现。

评分规则（每条结果）：
  +2.0  命中 expect_any 任一核心短语  → 强相关
  +1.0  未命中核心短语，但 expect 技术词命中 >= 2 个 → 相关
   0.0  其余 → 不相关
  -2.0  命中 noise 任一噪音标记（词典/百科/翻译）→ 重罚
  +0.5  域名属于权威源白名单

汇总指标：P@5(前5相关率) / Noise@5(前5噪音率) / MRR / Hit@5 / 耗时
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
QUERIES = BASE / "queries.json"

# 权威源白名单（技术内容可信来源）
AUTHORITY = {
    "anthropic.com", "github.com", "modelcontextprotocol.io", "arxiv.org",
    "huggingface.co", "python.org", "docs.python.org", "deepseek.com",
    "api-docs.deepseek.com", "deepseek-harness.github.io", "scikit-learn.org",
    "sbert.net", "readthedocs.io", "stackoverflow.com", "wikipedia.org",
    "langchain.com", "openai.com",
}


def parse_results(text: str) -> list[dict]:
    """把 web_search 的文本输出解析为结构化结果列表。"""
    out: list[dict] = []
    if not text:
        return out
    # 形如: "1. 标题\n   URL\n   snippet"
    blocks = re.split(r"\n(?=\d+\.\s)", text)
    for b in blocks:
        b = b.strip()
        m = re.match(r"^(\d+)\.\s+(.*)$", b, re.S)
        if not m:
            continue
        body = m.group(2)
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        url = ""
        snippet = ""
        for ln in lines[1:]:
            if ln.startswith("http://") or ln.startswith("https://"):
                url = ln
            elif not url:
                continue
            else:
                snippet += ln + " "
        out.append({"title": title, "url": url, "snippet": snippet.strip()})
    return out


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    d = (m.group(1) if m else "").lower()
    return d[4:] if d.startswith("www.") else d


def score_result(r: dict, spec: dict) -> float:
    text = " ".join([r.get("title", ""), r.get("url", ""), r.get("snippet", "")]).lower()
    s = 0.0
    if any(k.lower() in text for k in spec.get("expect_any", [])):
        s = 2.0
    elif sum(1 for k in spec.get("expect", []) if k.lower() in text) >= 2:
        s = 1.0
    if any(n.lower() in text for n in spec.get("noise", [])):
        s -= 2.0
    dom = _domain(r.get("url", ""))
    if dom and any(dom == a or dom.endswith("." + a) for a in AUTHORITY):
        s += 0.5
    return s


def evaluate(engine_fn, queries: list[dict], k: int = 5, max_results: int = 8) -> dict:
    """对一个引擎函数做评测。engine_fn(query, n) -> 文本输出。"""
    per_query = []
    t_total = 0.0
    for spec in queries:
        t0 = time.time()
        try:
            raw = engine_fn(spec["query"], max_results)
            err = ""
        except Exception as e:  # noqa: BLE001
            raw = ""
            err = f"{type(e).__name__}: {e}"
        cost = time.time() - t0
        t_total += cost

        results = parse_results(raw)[:max_results]
        scores = [score_result(r, spec) for r in results]

        top = scores[:k]
        p_at_k = (sum(1 for s in top if s > 0) / len(top)) if top else 0.0
        noise_at_k = (sum(1 for s in top if s < 0) / len(top)) if top else 0.0
        mrr = 0.0
        for i, s in enumerate(scores, 1):
            if s >= 1.0:
                mrr = 1.0 / i
                break
        per_query.append({
            "id": spec["id"], "query": spec["query"], "category": spec.get("category", ""),
            "n": len(results), "p@k": round(p_at_k, 3), "noise@k": round(noise_at_k, 3),
            "mrr": round(mrr, 3), "ms": round(cost * 1000), "err": err,
        })

    n = len(per_query) or 1
    agg = {
        "queries": len(per_query),
        "P@k": round(sum(q["p@k"] for q in per_query) / n, 4),
        "Noise@k": round(sum(q["noise@k"] for q in per_query) / n, 4),
        "MRR": round(sum(q["mrr"] for q in per_query) / n, 4),
        "Hit@k": round(sum(1 for q in per_query if q["mrr"] > 0) / n, 4),
        "avg_ms": round(t_total / n * 1000),
        "errors": sum(1 for q in per_query if q["err"]),
    }
    return {"agg": agg, "per_query": per_query}


def load_queries() -> list[dict]:
    return json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]


def report(res: dict, title: str = "") -> str:
    a = res["agg"]
    lines = [f"{'=' * 62}", f"评测报告: {title}", f"{'=' * 62}",
             f"查询数 {a['queries']} | P@5 {a['P@k']:.3f} | Noise@5 {a['Noise@k']:.3f} | "
             f"MRR {a['MRR']:.3f} | Hit@5 {a['Hit@k']:.3f} | 均耗时 {a['avg_ms']}ms | 错误 {a['errors']}"]
    bad = [q for q in res["per_query"] if q["p@k"] < 0.4 or q["noise@k"] > 0.2]
    if bad:
        lines.append("--- 待改进查询 ---")
        for q in bad:
            lines.append(f"  [{q['id']}] {q['query'][:42]:44} P@5={q['p@k']:.2f} Noise={q['noise@k']:.2f} MRR={q['mrr']:.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(BASE.parent.parent))
    from tools.web_search import _search_bing_rss

    qs = load_queries()
    res = evaluate(_search_bing_rss, qs)
    print(report(res, "Bing RSS 基线"))
    (BASE / "baseline_bing.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {BASE / 'baseline_bing.json'}")
