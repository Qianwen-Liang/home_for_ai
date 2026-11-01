"""web_search 降级可见性与参数契约测试（T2834）。

调研结论：
  web_search 已在 T2781-T2786 完成联邦检索改造（P@5 0.407→0.893），
  分层结构为「联邦检索 → 内存缓存 → Bing RSS → DuckDuckGo」，降级时会明确提示：
    "⚠️ 权威源未命中，以下为通用引擎兜底结果（质量可能较低…）"
  实测 4.1s 正常返回，元信息（来源/模式/耗时/条数）齐全。

因此**不做功能改动**，只补回归测试锁定两条最容易退化的契约：
  1. 降级必须可见——不能被改成静默降级（那会让模型误信低质量结果）
  2. 参数校验边界——空 query / 非整数 / 越界 / 非法 mode

全部用 monkeypatch 模拟，不依赖网络，保证测试稳定快速。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.web_search as WS  # noqa: E402
import tools.search_router as SR  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个测试前后清空内存缓存，避免相互影响。"""
    WS._SEARCH_CACHE.clear()
    yield
    WS._SEARCH_CACHE.clear()


# ── 1. 参数契约 ─────────────────────────────────────────

def test_empty_query_raises() -> None:
    with pytest.raises(WS.WebSearchError):
        WS.web_search("   ")


def test_non_integer_max_results_raises() -> None:
    with pytest.raises(WS.WebSearchError):
        WS.web_search("x", max_results="abc")  # type: ignore[arg-type]


def test_max_results_is_clamped(monkeypatch) -> None:
    """越界值应被夹到 [1, 10]，而不是报错或传下去。"""
    captured: dict = {}

    def fake_federated(query, max_results=5, mode="auto", **kw):
        captured["max_results"] = max_results
        return {"hits": [{"title": "t", "url": "u", "snippet": "s", "source": "x"}]}

    monkeypatch.setattr(SR, "federated_search", fake_federated)
    WS.web_search("q", max_results=99)
    assert captured["max_results"] == 10

    WS._SEARCH_CACHE.clear()
    WS.web_search("q2", max_results=0)
    assert captured["max_results"] == 5   # 0 视为未指定，取默认 5


def test_invalid_mode_falls_back_to_auto(monkeypatch) -> None:
    captured: dict = {}

    def fake_federated(query, max_results=5, mode="auto", **kw):
        captured["mode"] = mode
        return {"hits": [{"title": "t", "url": "u", "snippet": "s", "source": "x"}]}

    monkeypatch.setattr(SR, "federated_search", fake_federated)
    WS.web_search("q", mode="nonsense")
    assert captured["mode"] == "auto"


# ── 2. 降级可见性（最重要） ─────────────────────────────

def test_fallback_is_explicitly_labelled(monkeypatch) -> None:
    """联邦检索无命中时，兜底结果必须带明确提示，不得静默返回。

    这是本模块最容易退化的契约：把提示删掉、让兜底结果冒充权威结果，
    模型会误信低质量内容——正是 K2「静默失败」的同类问题。
    """
    monkeypatch.setattr(SR, "federated_search", lambda *a, **k: {"hits": []})
    monkeypatch.setattr(WS, "_search_bing_rss", lambda q, n: "FAKE_BING_RESULT")

    out = WS.web_search("q")
    assert "兜底" in out, f"降级未加提示，模型会误信低质量结果: {out[:200]}"
    assert "质量可能较低" in out
    assert "FAKE_BING_RESULT" in out


def test_federated_hit_has_no_fallback_banner(monkeypatch) -> None:
    """联邦检索成功时不应出现兜底提示（避免误报降级）。"""
    monkeypatch.setattr(
        SR, "federated_search",
        lambda *a, **k: {"hits": [{"title": "t", "url": "u", "snippet": "s", "source": "x"}]},
    )
    # 必须同时 patch format_results：mock 的 hits 字段不全，真实格式化会抛异常，
    # 而 web_search 用 except Exception: pass 吞掉后静默降级 —— 那会让这个测试
    # 测到兜底路径而不是联邦路径。
    monkeypatch.setattr(SR, "format_results", lambda fed: "FED_RESULT")
    out = WS.web_search("q")
    assert out == "FED_RESULT"
    assert "兜底" not in out


def test_federated_exception_degrades_not_crashes(monkeypatch) -> None:
    """联邦检索抛异常时应降级到兜底，而不是把异常抛给调用方。"""
    def boom(*a, **k):
        raise RuntimeError("router exploded")

    monkeypatch.setattr(SR, "federated_search", boom)
    monkeypatch.setattr(WS, "_search_bing_rss", lambda q, n: "FAKE_FALLBACK")

    out = WS.web_search("q")
    assert "FAKE_FALLBACK" in out
    assert "兜底" in out


# ── 3. 缓存 ─────────────────────────────────────────────

def test_fallback_result_is_cached(monkeypatch) -> None:
    calls = {"n": 0}

    def counting_bing(q, n):
        calls["n"] += 1
        return "CACHED_RESULT"

    monkeypatch.setattr(SR, "federated_search", lambda *a, **k: {"hits": []})
    monkeypatch.setattr(WS, "_search_bing_rss", counting_bing)

    WS.web_search("same-query")
    WS.web_search("same-query")
    assert calls["n"] == 1, f"兜底结果未命中缓存，重复请求了 {calls['n']} 次"


def test_cache_does_not_affect_federated_path(monkeypatch) -> None:
    """联邦检索每次都应被调用（它自带按 mode 区分的缓存）。"""
    calls = {"n": 0}

    def counting_fed(*a, **k):
        calls["n"] += 1
        return {"hits": [{"title": "t", "url": "u", "snippet": "s", "source": "x"}]}

    monkeypatch.setattr(SR, "federated_search", counting_fed)
    WS.web_search("q")
    WS.web_search("q")
    assert calls["n"] == 2
