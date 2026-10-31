"""错误分类覆盖率测试（T2822）。

区分两个层次的"覆盖"，不能混为一谈：
  errors.coverage_report()      —— 静态：映射表登记了多少种异常
  middleware.error_coverage()   —— 动态：真实失败中多少被细分到了具体类别

只有动态指标能反映分类是否真的有效。本文件锁定后者。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.middleware import TraceMiddleware  # noqa: E402


def _fail(mw: TraceMiddleware, tool: str, text: str, cid: str) -> None:
    mw.record_call(
        tool=tool, call_id=cid, arguments={}, result=text,
        duration_ms=1.0, error=RuntimeError(text),
    )


def test_no_failures_means_full_ratio() -> None:
    mw = TraceMiddleware()
    mw.record_call(tool="calc", call_id="c", arguments={}, result="4", duration_ms=1.0)
    cov = mw.error_coverage()
    assert cov["failed"] == 0
    assert cov["refined_ratio"] == 1.0


def test_mixed_failures_are_refined() -> None:
    """路径错→REJECTED、超时→RETRYABLE，都算"已细分"。"""
    mw = TraceMiddleware()
    _fail(mw, "read_file", "❌ 路径不存在: x", "a")
    _fail(mw, "runner", "⚠️ 命令执行超时（30秒）", "b")
    _fail(mw, "unknown_tool", "❌ 未知操作: zz", "c")   # 无法细分
    mw.record_call(tool="calc", call_id="d", arguments={}, result="4", duration_ms=1.0)

    cov = mw.error_coverage()
    assert cov["total_calls"] == 4
    assert cov["failed"] == 3
    assert cov["categories"]["REJECTED"] == 1
    assert cov["categories"]["RETRYABLE"] == 1
    assert cov["categories"]["FATAL"] == 1
    assert cov["refined"] == 2
    assert cov["unrefined"] == 1
    assert cov["refined_ratio"] == pytest.approx(2 / 3, abs=1e-3)


def test_unrefined_attributed_to_tools() -> None:
    """未细分要能定位到具体工具，否则无法改进。"""
    mw = TraceMiddleware()
    _fail(mw, "mystery_a", "❌ 未知操作: a", "1")
    _fail(mw, "mystery_b", "❌ 未知操作: b", "2")

    cov = mw.error_coverage()
    assert cov["refined"] == 0
    assert cov["refined_ratio"] == 0.0
    tools = dict(cov["unrefined_by_tool"])
    assert tools.get("mystery_a") == 1
    assert tools.get("mystery_b") == 1


def test_all_refined_gives_ratio_one() -> None:
    mw = TraceMiddleware()
    _fail(mw, "read_file", "❌ 路径不存在: a", "1")
    _fail(mw, "web_search", "❌ 连接失败", "2")
    cov = mw.error_coverage()
    assert cov["refined_ratio"] == 1.0
    assert cov["unrefined"] == 0


def test_real_exception_counts_as_refined() -> None:
    """真实异常（非 RuntimeError 包装）按类型分类，不应算作未细分。"""
    mw = TraceMiddleware()
    mw.record_call(
        tool="file", call_id="x", arguments={}, result="",
        duration_ms=1.0, error=OSError("boom"),
    )
    cov = mw.error_coverage()
    assert cov["categories"].get("REJECTED") == 1
    assert cov["refined"] == 1
    assert cov["unrefined"] == 0


def test_coverage_shape_is_stable() -> None:
    """字段名是外部契约，改动需同步调用方。"""
    mw = TraceMiddleware()
    _fail(mw, "t", "❌ 路径不存在", "1")
    cov = mw.error_coverage()
    for key in ("total_calls", "failed", "categories", "refined",
                "unrefined", "refined_ratio", "unrefined_by_tool"):
        assert key in cov, f"缺少字段 {key}"
