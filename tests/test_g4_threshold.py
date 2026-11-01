"""G4 噪声治理测试（T2839）。

修复的真实问题：
  G4 的 20% 阈值落在**实测噪声带内部**——同一份代码连测 12 轮，
  三个查询极差分别为 19.6% / 23.3% / 29.9%。
  结果是随机假警报：曾报「语义检索 +20%」而我当时的改动完全不涉及检索，
  重试即通过。

  更糟的是，**基线本身也是单次测量**（0.0430），比当时的 12 轮最小值
  (0.0504) 还低——用噪声样本当基准，等于把噪声固化。

修复：
  1. 阈值 20% → 50%，相对 30% 噪声留 1.67x 余量
  2. 基线改为连续 3 轮取中位数，并把轮间极差作为 noise_band 写入基线文件
  3. 保留 CV 自检（>25% 跳过判定）

红绿双向已验证（memory/cmd_output/g4_redgreen.py）：
  基线×0.6（约 +67% 退化）→ 捕获
  基线×0.98（约 +2% 变化）→ 不误报
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_gate():
    spec = importlib.util.spec_from_file_location("gate_g4_test", ROOT / "scripts" / "gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gate_g4_test"] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


# ── 1. 阈值必须高于噪声带 ───────────────────────────────

def test_threshold_above_measured_noise() -> None:
    """阈值必须大于实测噪声带（29.9%），否则假警报是必然的。"""
    assert gate.PERF_THRESHOLD >= 0.30, "阈值低于实测噪声带，会随机误报"
    assert gate.PERF_THRESHOLD == 0.50


def test_threshold_still_catches_real_regression() -> None:
    """阈值放宽后仍必须能抓住量级退化。

    真实退化通常在 100% 以上（knowledge 改造前 0.237s vs 0.09s ≈ +160%）。
    """
    assert 1 + gate.PERF_THRESHOLD < 2.0, "阈值过宽，抓不住翻倍级退化"


# ── 2. 基线必须记录噪声带 ───────────────────────────────

def test_baseline_records_noise_band() -> None:
    """基线文件必须带 noise_band_pct，让后来者知道测量可信度。"""
    p = ROOT / "eval" / "governance" / "perf_baseline.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "noise_band_pct" in data, "基线未记录噪声带"
    assert isinstance(data["noise_band_pct"], dict) and data["noise_band_pct"]
    for q, band in data["noise_band_pct"].items():
        assert 0 <= band < 100, f"{q} 噪声带异常: {band}"


def test_baseline_uses_multiple_rounds() -> None:
    """基线必须声明用了多少轮——单轮基线与噪声无异。"""
    p = ROOT / "eval" / "governance" / "perf_baseline.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("rounds", 1) >= 3, "基线未采用多轮测量，会把噪声固化"
    assert data.get("threshold") == gate.PERF_THRESHOLD, "基线记录阈值与代码不一致"


# ── 3. 判定边界行为 ─────────────────────────────────────

def _judge(cur: float, base: float) -> bool:
    """复刻 gate.check_g4 的比较逻辑。"""
    ratio = cur / base if base else 1.0
    return ratio > 1 + gate.PERF_THRESHOLD


def test_judgement_boundaries() -> None:
    base = 0.1
    assert _judge(0.1, base) is False          # 持平
    assert _judge(0.13, base) is False         # +30%（噪声带内）
    assert _judge(0.149, base) is False        # +49%（仍未超阈值）
    assert _judge(0.16, base) is True          # +60%（超阈值）
    assert _judge(0.3, base) is True           # +200%（翻倍退化）


def test_old_threshold_would_have_falsely_alarmed() -> None:
    """回归：+20~30% 的波动在旧阈值下会误报，新阈值下不会。

    这直接对应实测到的假警报（语义检索 0.0430→0.0518，约 +20%）。
    """
    base = 0.0430
    noisy = 0.0518
    old_alarm = (noisy / base) > 1 + 0.20
    new_alarm = (noisy / base) > 1 + gate.PERF_THRESHOLD
    assert old_alarm is True, "该样本本应触发旧阈值的误报"
    assert new_alarm is False, "新阈值下仍误报"
