"""budget — 全局上下文预算（步骤 4.3）

设计依据（步骤4调研）：
  arXiv 2605.26165 发现上下文预算是**二元启用效应**：一旦超限则整体失效
  （8K 预算下 JSON schema 溢出，EM 从正常降至 2.6%），而非线性退化。
  因此预算分配必须**随剩余量动态收缩**，而不是各工具各配一个固定阈值。

现状问题（实测）：
  `20_000` 这个数值在 4 处重复定义：
    core/read.py  FULL_TEXT_LIMIT / read MAX_FILE_BYTES
    tools/runner.py  MAX_OUTPUT_CHARS
    tools/middleware.py  LARGE_CHARS
    tools/registry.py  budget_chars
本模块作为**唯一事实来源**，其余模块从此引用。

用法：
    from tools.budget import BUDGET, FULL_TEXT_LIMIT, HARD_FILE_LIMIT, fit_text
"""
from __future__ import annotations

import threading

# ── 统一阈值（唯一事实来源）──────────────────────────────
FULL_TEXT_LIMIT = 20_000     # 低于此值全文返回
RESULT_LIMIT = 20_000        # 单次工具结果上限（超出走摘要+句柄）
HARD_FILE_LIMIT = 100_000    # 读取文件的硬上限（超出仅采样，不拒绝）
MIN_ALLOWANCE = 2_000        # 动态分配的下限，避免额度收缩到不可用
SUMMARY_HEAD_RATIO = 0.7     # 摘要保留比例（其余给尾部）

# 单会话内所有工具结果累计池（近似上下文容量；二元效应的安全边界）
DEFAULT_SESSION_POOL = 200_000


class ContextBudget:
    """预算感知的上下文分配器。

    核心思想：单次额度 = min(期望值, 剩余池)；剩余不足时按比例收缩，
    并强制走摘要路径，避免"某一工具吃光预算导致后续整体失效"。
    """

    def __init__(self, pool: int = DEFAULT_SESSION_POOL) -> None:
        self.pool = pool
        self._used = 0
        self._lock = threading.Lock()

    # ── 池状态 ──
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.pool - self._used)

    def consume(self, n: int) -> None:
        with self._lock:
            self._used += max(0, int(n))

    def reset(self) -> None:
        with self._lock:
            self._used = 0

    def usage(self) -> dict:
        with self._lock:
            return {"pool": self.pool, "used": self._used,
                    "remaining": max(0, self.pool - self._used),
                    "ratio": round(self._used / self.pool, 4) if self.pool else 0.0}

    # ── 额度计算（预算感知）──
    def allowance(self, wanted: int = RESULT_LIMIT) -> int:
        """本次可用额度。

        规则：
          - 剩余充足 → 返回 wanted（不超过 RESULT_LIMIT）
          - 剩余紧张 → 收缩到剩余量（但不低于 MIN_ALLOWANCE）
        """
        rem = self.remaining()
        if rem <= 0:
            return MIN_ALLOWANCE
        return max(min(int(wanted), rem), MIN_ALLOWANCE)

    def should_summarize(self, n_chars: int, wanted: int = RESULT_LIMIT) -> bool:
        """是否应走摘要路径（内容超单次额度，或池已紧张）。"""
        return n_chars > self.allowance(wanted)


BUDGET = ContextBudget()


def fit_text(text: str, *, wanted: int = RESULT_LIMIT, handle: str = "",
             budget: ContextBudget | None = None) -> tuple[str, bool]:
    """按预算裁剪文本。

    返回 (text, truncated)。截断时保留头 SUMMARY_HEAD_RATIO 与尾部，并附落盘句柄提示。
    """
    b = budget or BUDGET
    if not isinstance(text, str):
        text = str(text)
    limit = b.allowance(wanted)
    if len(text) <= limit:
        b.consume(len(text))
        return text, False

    head_n = int(limit * SUMMARY_HEAD_RATIO)
    tail_n = limit - head_n
    parts = [f"⚠️ 输出过大（{len(text)} 字符），已按上下文预算 {limit} 裁剪。"]
    if handle:
        parts.append(f"💡 完整内容已落盘：{handle}（可用 read_file offset/limit 分段读取）")
    parts += ["", f"── 前 {head_n} 字符 ──", text[:head_n],
              "", f"── 末 {tail_n} 字符 ──", text[-tail_n:]]
    out = "\n".join(parts)
    b.consume(len(out))
    return out, True


def snapshot() -> dict:
    """当前预算快照（供中间件/诊断使用）。"""
    return BUDGET.usage()
