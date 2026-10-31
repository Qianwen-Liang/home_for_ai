"""错误分类测试（T2822 / 第1梯队）。

覆盖三处改动：
  1. errors.classify_result —— 从返回文本推断类别（新增）
  2. errors.ERROR_MAP —— 补全 Python 内置异常（36 → 53）
  3. middleware._classify_error —— 复用统一契约，消除自建的第二套逻辑

外部依据：MCP SEP-1303 (Final) 要求工具参数校验失败作为 Tool Execution Error
返回给模型；类别判断正确，模型才知道该重试还是该改输入。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.errors import (  # noqa: E402
    ERROR_MAP,
    ErrorCategory,
    classify,
    classify_result,
    coverage_report,
)
from tools.middleware import TraceMiddleware  # noqa: E402


# ── 1. classify_result ───────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("❌ 路径不存在: foo.txt", ErrorCategory.REJECTED),
    ("❌ 表达式不能为空", ErrorCategory.REJECTED),
    ("❌ 参数格式错误", ErrorCategory.REJECTED),
    ("⚠️ 命令执行超时（30秒），已终止。", ErrorCategory.RETRYABLE),
    ("❌ 连接失败，请检查网络", ErrorCategory.RETRYABLE),
    ("❌ 请求被限流", ErrorCategory.RETRYABLE),
    ("❌ 未知操作: zzz", ErrorCategory.FATAL),
])
def test_classify_result_categories(text: str, expected: ErrorCategory) -> None:
    category, code, phase = classify_result(text)
    assert category is expected, f"{text!r} 应归 {expected}，实际 {category}"
    assert code.startswith("result.")
    assert phase


def test_classify_result_empty_is_fatal() -> None:
    assert classify_result("")[0] is ErrorCategory.FATAL


def test_empty_search_result_is_not_treated_as_error() -> None:
    """「未找到相关条目」是合法空结果，不能当作 REJECTED。

    这类返回根本不该进入 classify_result——调用方须先判定失败。
    此测试确保即便误调用，也不会被判成"需改输入"从而触发无效重试。
    """
    category, _c, _p = classify_result("❌ 未找到与 'abc' 相关的知识条目。")
    assert category is not ErrorCategory.RETRYABLE


# ── 2. 内置异常覆盖 ─────────────────────────────────────

@pytest.mark.parametrize("exc_cls,expected", [
    (OSError, ErrorCategory.REJECTED),
    (FileNotFoundError, ErrorCategory.REJECTED),
    (PermissionError, ErrorCategory.REJECTED),
    (ValueError, ErrorCategory.REJECTED),
    (TimeoutError, ErrorCategory.RETRYABLE),
    (ConnectionError, ErrorCategory.RETRYABLE),
    (TypeError, ErrorCategory.FATAL),
    (KeyError, ErrorCategory.FATAL),
    (AttributeError, ErrorCategory.FATAL),
])
def test_builtin_exceptions_mapped(exc_cls: type, expected: ErrorCategory) -> None:
    """内置异常必须有明确归类，不能只靠类名启发式兜底。"""
    assert exc_cls.__name__ in ERROR_MAP, f"{exc_cls.__name__} 未登记入 ERROR_MAP"
    assert classify(exc_cls("x"))[0] is expected


def test_oserror_no_longer_fatal() -> None:
    """回归：OSError 曾被判 FATAL（需人工介入），实际只需修复路径/权限。"""
    assert classify(OSError("boom"))[0] is not ErrorCategory.FATAL


def test_map_size_grew() -> None:
    assert len(ERROR_MAP) >= 50, "内置异常补充后映射表应不少于 50 种"


def test_coverage_report_mentions_all_three() -> None:
    report = coverage_report()
    for name in ("RETRYABLE", "REJECTED", "FATAL"):
        assert name in report


# ── 3. middleware 复用统一契约 ──────────────────────────

def test_middleware_reuses_unified_contract() -> None:
    """middleware 不再自建第二套 name 匹配逻辑。

    agent1 把失败包装成 RuntimeError(result[:120])，按异常类型只能归 FATAL；
    现在应能从文本细分出 REJECTED / RETRYABLE。
    """
    assert TraceMiddleware._classify_error(RuntimeError("x"), "❌ 路径不存在: a") == "REJECTED"
    assert TraceMiddleware._classify_error(RuntimeError("x"), "⚠️ 命令执行超时（30秒）") == "RETRYABLE"


def test_middleware_real_exception_still_wins() -> None:
    """真实异常按类型分类优先于文本（OSError 即便附带的文本无特征也应正确）。"""
    assert TraceMiddleware._classify_error(OSError("boom")) == "REJECTED"


def test_middleware_unknown_stays_fatal() -> None:
    assert TraceMiddleware._classify_error(RuntimeError("x"), "❌ 未知操作: zz") == "FATAL"


def test_middleware_record_call_records_category() -> None:
    """端到端：record_call 应把分类落到 CallRecord.error_category。"""
    mw = TraceMiddleware()
    rec = mw.record_call(
        tool="read_file", call_id="c1", arguments={"path": "x"},
        result="❌ 路径不存在: x", duration_ms=1.0,
        error=RuntimeError("❌ 路径不存在: x"),
    )
    assert rec.success is False
    assert rec.error_category == "REJECTED"


def test_middleware_success_has_no_category() -> None:
    mw = TraceMiddleware()
    rec = mw.record_call(
        tool="calculator", call_id="c2", arguments={},
        result="4", duration_ms=1.0, error=None,
    )
    assert rec.success is True
    assert rec.error_category == ""
