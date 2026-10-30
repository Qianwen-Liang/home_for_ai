"""paper_collab.py — 投稿人↔审稿人 多智能体论文协作（强化版）

融合多个前沿框架的长处：
  - AutoGen：Writer-Reviewer 多轮对话循环、Critic 角色
  - MetaGPT：角色 SOP + 结构化工件传递（审稿表强制 JSON 输出）
  - ChatDev：反思机制、阶段产物审查
  - CAMEL：角色扮演（角色化 prompt）
  - 离线自主智能体（AutoGPT/ARIS）：检查点持久化、收敛/终止条件

核心：两个子智能体 ——
  投稿人 Writer：撰写/修改论文
  审稿人 Reviewer：批判性评审，输出结构化意见（verdict/score/strengths/weaknesses/suggestions）

多轮对话直至收敛（verdict=accept 或 score 达阈值或达到最大轮数），产出高质量论文。

使用方式：
  # 在线（函数调用）
  from research.paper_collab import run_paper_collab
  paper, history = run_paper_collab(topic="...", requirements="...", max_rounds=3)

  # 离线（后台进程）
  python research/paper_collab.py --topic "..." --max_rounds 3 --output memory/offline/<id>
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent

# 复用 research_worker 的 LLM 客户端（已处理推理模型空 content 等）
from research.offline.research_worker import llm_chat

DEFAULT_MAX_ROUNDS = 3
ACCEPT_SCORE_THRESHOLD = 8  # score >= 8 视为可接受
PAPER_MAX_TOKENS = 16000  # 论文生成长文本需更大的输出配额（推理模型思考挤占 content）
DRAFT_TRUNCATE = 30000  # 传给审稿人/投稿人的草稿截断上限（避免截断完整论文）


# ─────────────────────────── 角色 prompt ───────────────────────────

WRITER_INITIAL_PROMPT = """你是资深学术论文投稿人（Writer）。请为以下主题撰写一篇学术论文初稿。

主题：{topic}
写作要求：{requirements}

【真实参考资料（来自联网检索，请优先引用）】
{references}

请输出完整的论文（Markdown），包含以下章节：
## 标题
## 摘要
## 1 引言
## 2 相关工作
## 3 方法
## 4 实验与结果
## 5 结论与展望
## 参考文献

要求：
1. 结构严谨、逻辑清晰、方法具体可复现、结论有依据、突出创新点。
2. 参考文献必须基于上面的真实资料（真实存在的论文），不要虚构引用。
3. 若某处是推测或假设，明确标注，不要编造实验数据冒充真实结果。"""

REVIEWER_PROMPT = """你是严格的学术审稿人（Reviewer）。请评审以下论文投稿。

论文主题：{topic}

【论文草稿】
{draft}

【事实核查参考（来自联网检索的真实资料）】
{fact_context}

【历史评审记录】
{history}

请**只输出 JSON**（不要输出任何其他文字），格式如下：
{{
  "verdict": "accept" 或 "revise" 或 "reject",
  "score": 0到10的整数（多维评分的加权平均）,
  "dimensions": {{
    "novelty": 0到10,
    "correctness": 0到10,
    "reproducibility": 0到10,
    "clarity": 0到10
  }},
  "fact_check": [
    {{"claim": "论文中的关键声明或引用", "status": "verified/unverified/suspicious", "note": "核查说明"}}
  ],
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["缺点1", "缺点2"],
  "suggestions": ["具体可执行的修改建议1", "具体可执行的修改建议2"]
}}

要求：
1. 评分标准：0-3 不可用，4-6 需大修，7 可小修，8-10 可接受。
2. 对照【事实核查参考】核查论文中的引用和关键声明是否与真实研究一致，
   在 fact_check 中标注存疑或虚构的引用/数据。
3. 若历史评审中已提出的问题已被解决，不要重复提出。"""

WRITER_REVISE_PROMPT = """你是资深学术论文投稿人（Writer）。审稿人给出了评审意见，请据此修改论文。

论文主题：{topic}

【当前论文】
{draft}

【审稿人意见】
{review_text}

请输出修改后的**完整论文**（Markdown），逐条解决审稿人的 weaknesses 和 suggestions，
保留 strengths，保持完整章节结构（标题/摘要/引言/相关工作/方法/实验/结论/参考文献）。
如果审稿人指出某处需要补充，请真正补充内容，不要只写"已修改"。"""


# ─────────────────────────── 工具函数 ───────────────────────────

def _extract_json(raw: str) -> dict | None:
    """从 LLM 输出中鲁棒地提取 JSON 对象。"""
    if not raw:
        return None
    text = raw.strip()

    # 1) 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass

    # 2) 提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass

    # 3) 提取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _search_context(topic: str, max_sources: int = 5) -> str:
    """联网检索主题相关真实资料，作为写作/评审的事实依据。"""
    try:
        from tools.web_search import web_search
        result = web_search(topic, max_sources)
        return result if result and result.strip() else "（检索无结果）"
    except Exception as exc:
        return f"（检索失败: {type(exc).__name__}: {exc}）"


def _format_history(history: list[dict]) -> str:
    """把历史评审记录格式化为文本。"""
    if not history:
        return "（无，这是第一轮评审）"
    lines = []
    for i, r in enumerate(history, 1):
        lines.append(
            f"第{i}轮: verdict={r.get('verdict','?')}, score={r.get('score','?')}\n"
            f"  问题: {r.get('weaknesses', [])}\n"
            f"  建议: {r.get('suggestions', [])}"
        )
    return "\n".join(lines)


def _format_review(review: dict) -> str:
    """把评审 dict 格式化为给 Writer 看的文本（含多维评分与事实核查）。"""
    parts = [
        f"verdict: {review.get('verdict', '?')}",
        f"score: {review.get('score', '?')}",
    ]
    dims = review.get("dimensions", {})
    if isinstance(dims, dict) and dims:
        parts.append(f"分维度评分: {json.dumps(dims, ensure_ascii=False)}")
    facts = review.get("fact_check", [])
    if facts:
        suspicious = [f for f in facts if isinstance(f, dict) and f.get("status") in ("unverified", "suspicious")]
        if suspicious:
            parts.append(f"⚠️ 存疑引用/声明（需修正或删除）: {json.dumps(suspicious, ensure_ascii=False)}")
    parts.append(f"优点: {json.dumps(review.get('strengths', []), ensure_ascii=False)}")
    parts.append(f"缺点: {json.dumps(review.get('weaknesses', []), ensure_ascii=False)}")
    parts.append(f"修改建议: {json.dumps(review.get('suggestions', []), ensure_ascii=False)}")
    return "\n".join(parts)


# ─────────────────────────── 角色实现 ───────────────────────────

def writer_initial(topic: str, requirements: str) -> str:
    """投稿人：撰写初稿（先检索真实资料，基于真实资料写作）。"""
    references = _search_context(topic)
    prompt = WRITER_INITIAL_PROMPT.format(
        topic=topic,
        requirements=requirements or "无特殊要求",
        references=references,
    )
    return llm_chat([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=PAPER_MAX_TOKENS)


def reviewer_review(topic: str, draft: str, history: list[dict]) -> dict:
    """审稿人：评审论文（先检索真实资料做事实核查），返回结构化意见。"""
    fact_context = _search_context(topic)
    prompt = REVIEWER_PROMPT.format(
        topic=topic,
        draft=draft[:DRAFT_TRUNCATE],
        fact_context=fact_context,
        history=_format_history(history),
    )
    last_error = ""
    for _ in range(3):  # 最多 3 次尝试拿到合法 JSON
        try:
            raw = llm_chat([{"role": "user", "content": prompt}], temperature=0.2)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
            continue

        review = _extract_json(raw)
        if review is not None and "verdict" in review:
            return review
        last_error = f"JSON 解析失败: {raw[:100]}"
        time.sleep(2)

    # 兜底：返回一个默认的 revise 意见
    return {
        "verdict": "revise",
        "score": 5,
        "strengths": [],
        "weaknesses": [f"评审解析异常: {last_error}"],
        "suggestions": ["请检查论文完整性和逻辑性"],
    }


def writer_revise(topic: str, draft: str, review: dict) -> str:
    """投稿人：根据评审意见修改论文。"""
    prompt = WRITER_REVISE_PROMPT.format(
        topic=topic,
        draft=draft[:DRAFT_TRUNCATE],
        review_text=_format_review(review),
    )
    return llm_chat([{"role": "user", "content": prompt}], temperature=0.6, max_tokens=PAPER_MAX_TOKENS)


# ─────────────────────────── 主编排 ───────────────────────────

def run_paper_collab(
    topic: str,
    requirements: str = "",
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    on_progress: Any = None,
) -> tuple[str, list[dict]]:
    """运行投稿人↔审稿人 多轮对话，产出论文。

    返回 (最终论文, 评审历史列表)。
    """
    log = print if on_progress is None else on_progress

    log(f"[投稿人] 开始撰写初稿...")
    draft = writer_initial(topic, requirements)
    log(f"[投稿人] 初稿完成（{len(draft)} 字符）")

    history: list[dict] = []
    for round_no in range(1, max_rounds + 1):
        log(f"[审稿人] 第 {round_no} 轮评审...")
        review = reviewer_review(topic, draft, history)
        history.append(review)

        verdict = review.get("verdict", "revise")
        score = review.get("score", 5)
        dims = review.get("dimensions", {})
        facts = review.get("fact_check", [])
        suspicious_n = len([
            f for f in facts
            if isinstance(f, dict) and f.get("status") in ("unverified", "suspicious")
        ])
        dims_str = json.dumps(dims, ensure_ascii=False) if isinstance(dims, dict) and dims else ""
        log(
            f"[审稿人] 第 {round_no} 轮: verdict={verdict}, score={score}, "
            f"缺点 {len(review.get('weaknesses', []))} 条, 建议 {len(review.get('suggestions', []))} 条, "
            f"存疑引用 {suspicious_n} 条"
            + (f" | 维度 {dims_str}" if dims_str else "")
        )

        # 收敛判断
        if verdict == "accept":
            log(f"[主编] 审稿人判定 accept，协作收敛于第 {round_no} 轮。")
            break
        if isinstance(score, (int, float)) and score >= ACCEPT_SCORE_THRESHOLD:
            log(f"[主编] 评分 {score} >= {ACCEPT_SCORE_THRESHOLD}，协作收敛于第 {round_no} 轮。")
            break
        if round_no >= max_rounds:
            log(f"[主编] 达到最大轮数 {max_rounds}，停止迭代。")
            break

        log(f"[投稿人] 根据第 {round_no} 轮意见修改...")
        draft = writer_revise(topic, draft, review)
        log(f"[投稿人] 修改完成（{len(draft)} 字符）")

    return draft, history


# ─────────────────────────── 命令行入口（离线后台） ───────────────────────────

def _parse_args(argv):
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and i + 1 < len(argv):
            args[a[2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return args


def main() -> None:
    a = _parse_args(sys.argv[1:])
    topic = a.get("topic", "")
    if not topic:
        print("用法: python paper_collab.py --topic <主题> [--requirements <要求>] [--max_rounds 3] [--output <目录>] [--task_id <id>]")
        sys.exit(1)

    requirements = a.get("requirements", "")
    max_rounds = int(a.get("max_rounds", DEFAULT_MAX_ROUNDS))
    task_id = a.get("task_id", "")
    out_dir = Path(a.get("output", SANDBOX_DIR / "memory" / "paper_collab"))
    out_dir.mkdir(parents=True, exist_ok=True)

    def log(msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with (out_dir / "collab.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def save_progress(status: str, **extra) -> None:
        if not task_id:
            return
        prog = {
            "status": status,
            "updated_at": datetime.now().isoformat(),
            **extra,
        }
        (out_dir / "progress.json").write_text(
            json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save_progress("running", topic=topic)
    log(f"论文协作启动: {topic}")

    try:
        paper, history = run_paper_collab(topic, requirements, max_rounds, on_progress=log)
    except Exception as exc:
        save_progress("failed", error=f"{type(exc).__name__}: {exc}")
        log(f"论文协作失败: {exc}")
        sys.exit(1)

    # 落盘
    (out_dir / "paper.md").write_text(paper, encoding="utf-8")
    (out_dir / "report.md").write_text(paper, encoding="utf-8")  # 供 offline_status 识别
    (out_dir / "reviews.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    final = history[-1] if history else {}
    save_progress(
        "done",
        reviews=len(history),
        final_verdict=final.get("verdict", ""),
        final_score=final.get("score", ""),
        paper_chars=len(paper),
    )
    log(f"论文已保存: {out_dir / 'paper.md'}（{len(paper)} 字符，{len(history)} 轮评审）")


if __name__ == "__main__":
    main()
