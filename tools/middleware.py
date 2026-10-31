"""middleware — 可观测性中间件（步骤 3）

设计依据（见 eval/governance/STEP3_LANDING_CONTRACT.md）：
  1. 数据模型对齐 OpenTelemetry GenAI 语义约定（属性/指标/异常命名），但零第三方依赖
  2. 确定性验证优先于统计异常检测（arXiv 2608.02464：0 误报 vs 17% 误报）
  3. 观测闭环：阈值突破触发行动，而非仅记录（arXiv 2604.05119）
  4. 与注册表联动：读取 ToolSpec 行为标注，新增工具自动纳入
  5. 检测静默失败（arXiv 2609.26836；对应本项目 K2）

对外 API：
  TraceMiddleware.record_call(...)      统一采集（替代手工埋点）
  verify_recomputation(...)             确定性验证一：结果重算
  verify_coverage(...)                  确定性验证二：必需调用覆盖
  detect_silent_failure(...)            确定性验证三：静默失败识别
  on_threshold(...)                     观测闭环钩子
  snapshot() / export_otel()            本地快照 / OTel 兼容导出
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # 步骤4.3：阈值唯一来源
    from tools.budget import RESULT_LIMIT
except ImportError:  # pragma: no cover
    from budget import RESULT_LIMIT

# ── OTel GenAI 语义约定（命名对齐，不引入 SDK）──────────────
OTEL_TOOL_NAME = "gen_ai.tool.name"
OTEL_TOOL_TYPE = "gen_ai.tool.type"
OTEL_CALL_ID = "gen_ai.tool.call.id"
OTEL_CALL_ARGS = "gen_ai.tool.call.arguments"
OTEL_CALL_RESULT = "gen_ai.tool.call.result"
OTEL_OP_NAME = "gen_ai.operation.name"
OTEL_AGENT_NAME = "gen_ai.agent.name"
OTEL_ERROR_TYPE = "error.type"
OTEL_EXCEPTION = "gen_ai.client.operation.exception"

METRIC_TOOL_DURATION = "gen_ai.execute_tool.duration"
METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"

OP_EXECUTE_TOOL = "execute_tool"

# 静默失败标记：成功返回但缺少失败语义时视为可疑
_FAILURE_MARKERS = ("❌", "⚠️", "错误", "失败", "异常", "不支持", "未知操作",
                    "不可用", "未找到", "无效", "超时", "返回码")


@dataclass
class CallRecord:
    """单次工具调用记录（内部结构，可导出为 OTel 形状）。"""
    tool: str
    tool_type: str
    call_id: str
    duration_ms: float
    success: bool
    result_chars: int
    arg_chars: int
    error_type: str = ""
    error_category: str = ""
    silent_failure: bool = False
    read_only: bool = False
    destructive: bool = False
    ts: float = field(default_factory=time.time)


@dataclass
class ThresholdAction:
    """阈值触发的闭环动作。"""
    kind: str          # slow_tool / large_result / silent_failure / error_rate
    tool: str
    message: str
    severity: str = "warn"


class TraceMiddleware:
    """工具调用可观测性中间件。"""

    SLOW_MS = 3_000            # 慢工具阈值
    LARGE_CHARS = RESULT_LIMIT  # 大结果阈值（步骤4.3 统一来源：tools/budget.py）
    MAX_RECORDS = 2_000        # 内存上限

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[CallRecord] = []
        self._actions: list[ThresholdAction] = []
        self._enabled = True

    # ── 统一采集（替代手工埋点）──
    def record_call(self, *, tool: str, call_id: str, arguments: Any,
                    result: str, duration_ms: float, error: BaseException | None = None,
                    spec: Any = None) -> CallRecord:
        """记录一次工具调用。spec 为 ToolSpec（可选），用于读取行为标注。"""
        if not self._enabled:
            return CallRecord(tool, "", call_id, duration_ms, True, 0, 0)

        result = result if isinstance(result, str) else str(result)
        arg_chars = len(json.dumps(arguments, ensure_ascii=False)) if arguments else 0
        success = error is None
        silent = False
        err_type = ""
        err_cat = ""

        if error is not None:
            err_type = type(error).__name__
            err_cat = self._classify_error(error, result)
        else:
            silent = self.detect_silent_failure(tool, result)

        rec = CallRecord(
            tool=tool,
            tool_type=OP_EXECUTE_TOOL,
            call_id=call_id,
            duration_ms=duration_ms,
            success=success,
            result_chars=len(result),
            arg_chars=arg_chars,
            error_type=err_type,
            error_category=err_cat,
            silent_failure=silent,
            read_only=bool(getattr(spec, "read_only", False)),
            destructive=bool(getattr(spec, "destructive", False)),
        )
        with self._lock:
            self._records.append(rec)
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS:]
            self._actions.extend(self._check_thresholds(rec))
            if len(self._actions) > 500:
                self._actions = self._actions[-500:]

        # ── 向后兼容：同步写入既有 monitor，避免 health_dashboard /
        #    usage_analyzer / self_check 等依赖方数据断流 ──
        try:
            from tools import monitor as _mon
            _mon._monitor.record(tool, duration_ms / 1000.0, success)
        except Exception:
            pass

        return rec

    # ── 错误分类（三层，供步骤 4 复用）──
    @staticmethod
    def _classify_error(exc: BaseException, result: str = "") -> str:
        """错误分类：复用统一契约，避免 middleware 与 errors.py 两套逻辑漂移。

        ★T2822：原实现是自建的 name 关键词匹配，与 tools/errors.py 的
        ERROR_MAP 各写一份，长期必然不一致。改为优先调用统一契约。

        顺序很重要：
          1. 先按异常类型分类（真实异常如 OSError 能准确归类）
          2. 若归为 FATAL 且带返回文本，再用文本细分——
             因为 agent1 把失败包装成 RuntimeError(result[:120])，
             RuntimeError 不在 ERROR_MAP 里，按类型只能得到 FATAL，
             会丢掉「该重试」还是「该改参数」的关键信息。
        """
        try:
            from tools.errors import ErrorCategory, classify, classify_result
        except ImportError:  # 兜底：契约不可用时不阻塞主流程
            name = type(exc).__name__.lower()
            if any(k in name for k in ("timeout", "network", "connection", "rate", "limit")):
                return "RETRYABLE"
            if any(k in name for k in ("path", "reject", "invalid", "argument", "notfound")):
                return "REJECTED"
            return "FATAL"

        category, _code, _phase = classify(exc)
        if category != ErrorCategory.FATAL:
            return category.value
        if result:
            text_category, _c, _p = classify_result(result)
            return text_category.value
        return category.value

    # ── 确定性验证三：静默失败识别 ──
    @staticmethod
    def detect_silent_failure(tool: str, result: str) -> bool:
        """判断"看似成功但可能失败"的结果。

        规则（确定性，非统计）：
          - 结果为空 → 可疑
          - 结果含失败标记但未以明确失败前缀开头 → 可疑（如 K2：'返回码: 1'）
          - 结果含 '返回码: N' 且 N != 0 → 静默失败
        """
        if not isinstance(result, str) or not result.strip():
            return True
        low = result.strip()
        m = re.search(r"返回码:\s*(-?\d+)", low)
        if m and m.group(1) != "0":
            return True
        has_marker = any(k in low[:200] for k in _FAILURE_MARKERS)
        explicit_fail = low.startswith(("❌", "⚠️", "工具执行失败"))
        return has_marker and not explicit_fail

    # ── 确定性验证一：结果重算 ──
    @staticmethod
    def verify_recomputation(claimed_total: float, tool_results: list[float],
                             tol: float = 1e-6) -> tuple[bool, str]:
        """从实际工具结果重算，与声称总数比对（arXiv 2608.02464）。"""
        actual = sum(tool_results)
        ok = abs(actual - claimed_total) <= tol
        msg = ("重算一致" if ok else
               f"重算不一致: 声称 {claimed_total} vs 实际 {actual}")
        return ok, msg

    # ── 确定性验证二：必需调用覆盖 ──
    @staticmethod
    def verify_coverage(required_calls: list[str], actual_calls: list[str]) -> tuple[bool, str]:
        """检查每个必需调用是否发生（arXiv 2608.02464）。"""
        missing = [c for c in required_calls if c not in actual_calls]
        ok = not missing
        return ok, ("覆盖完整" if ok else f"缺失必需调用: {missing}")

    # ── 观测闭环：阈值 → 动作 ──
    def _check_thresholds(self, rec: CallRecord) -> list[ThresholdAction]:
        acts: list[ThresholdAction] = []
        if rec.duration_ms >= self.SLOW_MS:
            acts.append(ThresholdAction("slow_tool", rec.tool,
                                        f"{rec.tool} 耗时 {rec.duration_ms:.0f}ms 超阈值",
                                        "warn"))
        if rec.result_chars >= self.LARGE_CHARS:
            acts.append(ThresholdAction("large_result", rec.tool,
                                        f"{rec.tool} 返回 {rec.result_chars} 字符超预算",
                                        "info"))
        if rec.silent_failure:
            acts.append(ThresholdAction("silent_failure", rec.tool,
                                        f"{rec.tool} 疑似静默失败（成功返回但含失败特征）",
                                        "error"))
        return acts

    def on_threshold(self) -> list[dict[str, str]]:
        """取出并清空待处理动作（闭环执行入口）。"""
        with self._lock:
            out = [{"kind": a.kind, "tool": a.tool, "message": a.message,
                    "severity": a.severity} for a in self._actions]
            self._actions.clear()
        return out

    # ── 汇总与导出 ──
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            recs = list(self._records)
        n = len(recs)
        if n == 0:
            return {"total": 0}
        by_tool: dict[str, dict] = {}
        for r in recs:
            d = by_tool.setdefault(r.tool, {"calls": 0, "ms": 0.0, "errors": 0,
                                            "silent": 0, "max_chars": 0, "max_ms": 0.0})
            d["calls"] += 1
            d["ms"] += r.duration_ms
            d["errors"] += 0 if r.success else 1
            d["silent"] += 1 if r.silent_failure else 0
            d["max_chars"] = max(d["max_chars"], r.result_chars)
            d["max_ms"] = max(d["max_ms"], r.duration_ms)
        for d in by_tool.values():
            d["avg_ms"] = round(d["ms"] / d["calls"], 1) if d["calls"] else 0.0
        return {
            "total": n,
            "error_rate": round(sum(0 if r.success else 1 for r in recs) / n, 4),
            "silent_rate": round(sum(1 for r in recs if r.silent_failure) / n, 4),
            "avg_ms": round(sum(r.duration_ms for r in recs) / n, 1),
            "by_tool": by_tool,
        }

    def slow_tools(self, top_n: int = 10) -> list[dict]:
        s = self.snapshot().get("by_tool", {})
        rows = [{"tool": k, **v} for k, v in s.items()]
        return sorted(rows, key=lambda x: -x["avg_ms"])[:top_n]

    def large_result_tools(self, top_n: int = 10) -> list[dict]:
        s = self.snapshot().get("by_tool", {})
        rows = [{"tool": k, **v} for k, v in s.items()]
        return sorted(rows, key=lambda x: -x["max_chars"])[:top_n]

    def error_coverage(self) -> dict[str, Any]:
        """错误分类覆盖率（T2822 补）：衡量分类**是否真的有效**，而不只是映射表多大。

        区分两个层次：
          - 映射表覆盖（errors.coverage_report）：表里登记了多少种异常
          - **运行时覆盖（本方法）**：真实失败调用中，有多少被细分到了具体类别

        只有后者能反映分类质量。判据：
          已细分 = 归入 RETRYABLE / REJECTED
          未细分 = 落在 FATAL 且 error_type 是 RuntimeError
                   （agent1 用 RuntimeError(result[:120]) 包装所有失败，
                     这类记录说明文本分类也没能给出更具体的判断）
        """
        with self._lock:
            recs = list(self._records)
        failed = [r for r in recs if not r.success]
        total = len(recs)
        if not failed:
            return {"total_calls": total, "failed": 0, "refined_ratio": 1.0,
                    "note": "无失败调用"}

        from collections import Counter

        cats = Counter((r.error_category or "(未分类)") for r in failed)
        unrefined = [
            r for r in failed
            if r.error_category == "FATAL" and r.error_type == "RuntimeError"
        ]
        refined = len(failed) - len(unrefined)
        by_tool = Counter(r.tool for r in unrefined).most_common(5)

        return {
            "total_calls": total,
            "failed": len(failed),
            "categories": dict(cats),
            "refined": refined,
            "unrefined": len(unrefined),
            "refined_ratio": round(refined / len(failed), 3),
            "unrefined_by_tool": by_tool,
        }

    def silent_failure_tools(self, top_n: int = 10) -> list[dict]:
        s = self.snapshot().get("by_tool", {})
        rows = [{"tool": k, **v} for k, v in s.items() if v["silent"] > 0]
        return sorted(rows, key=lambda x: -x["silent"])[:top_n]

    def export_otel(self, limit: int = 200) -> list[dict]:
        """导出为 OTel GenAI 兼容的事件形状（便于未来接入任意后端）。"""
        with self._lock:
            recs = self._records[-limit:]
        out = []
        for r in recs:
            attrs = {
                OTEL_OP_NAME: OP_EXECUTE_TOOL,
                OTEL_TOOL_NAME: r.tool,
                OTEL_TOOL_TYPE: r.tool_type,
                OTEL_CALL_ID: r.call_id,
                OTEL_CALL_RESULT: f"{r.result_chars} chars",
                "duration_ms": r.duration_ms,
            }
            if not r.success:
                attrs[OTEL_ERROR_TYPE] = r.error_type
                attrs[OTEL_EXCEPTION] = r.error_category
            out.append({"name": OP_EXECUTE_TOOL, "attributes": attrs,
                        "metric": {METRIC_TOOL_DURATION: r.duration_ms}})
        return out

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._actions.clear()


MIDDLEWARE = TraceMiddleware()
