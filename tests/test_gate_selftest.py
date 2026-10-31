"""门禁自检套件（T2799 / P1-⑤）：验证 G1-G5 该红时必红、该绿时必绿。

存在理由
--------
我们已经两次被门禁的**假警报**误导（G1 观察者效应、G4 CPU 余热），
却从未验证过它**真能抓贼**。一个不会红的门禁，和没有门禁是一回事——
它只是给人虚假的安全感。

本套件对每道门禁做双向验证：
  红向（negative）—— 制造该门禁本应捕获的违规，断言它确实变红
  绿向（positive）—— 正常状态下断言它保持绿色（避免"永远红所以看起来有效"）

通过 pytest 纳入 CI 的 tests job，与业务测试一起执行。
"""
from __future__ import annotations

import importlib.util
import json
import platform
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name: str, rel: str):
    """从 scripts/ 加载非包模块。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load("gate_under_test", "scripts/gate.py")
audit = _load("test_audit_under_test", "scripts/test_audit.py")


# ══════════════════════════════════════════════════════════
# G1 数据隔离
# ══════════════════════════════════════════════════════════

def test_g1_red_when_existing_file_rewritten():
    """红向：已存在的生产文件被改写 → 必须判定为污染。"""
    before = {"knowledge/knowledge_store.json": {"exists": True, "size": 100, "sha256": "aaa"}}
    after = {"knowledge/knowledge_store.json": {"exists": True, "size": 200, "sha256": "bbb"}}
    drifted, created = gate._compare_fingerprints(before, after)
    assert len(drifted) == 1, "改写已存在文件未被判为污染"
    assert not created


def test_g1_green_when_unchanged():
    """绿向：指纹不变 → 不得误报。"""
    fp = {"memory/tasks.json": {"exists": True, "size": 10, "sha256": "same"}}
    drifted, created = gate._compare_fingerprints(fp, dict(fp))
    assert not drifted and not created


def test_g1_green_when_absent_file_created():
    """绿向：原本缺失的文件被初始化创建 → 归入 created，不算污染。

    这是 CI 全新 clone 时的必然现象（TaskTracker 首次写入即创建文件）。
    """
    before = {"memory/tasks.json": {"exists": False}}
    after = {"memory/tasks.json": {"exists": True, "size": 5, "sha256": "new"}}
    drifted, created = gate._compare_fingerprints(before, after)
    assert not drifted, "初始化创建被误判为污染"
    assert len(created) == 1


# ══════════════════════════════════════════════════════════
# G2 确定性
# ══════════════════════════════════════════════════════════

def test_g2_red_when_id_collision(monkeypatch):
    """红向：ID 生成不去重（同秒覆盖）→ G2 必须变红。"""
    import tools.knowledge_store as K

    def broken_store(self, title, content, category="", tags="",
                     kind="declarative", semantic_tags=""):
        now = time.time()
        entry_id = f"K{int(now)}"  # 故意去掉去重后缀
        self._data[entry_id] = {
            "id": entry_id, "title": title, "content": content,
            "category": category or "general", "tags": [], "kind": kind,
            "semantic_tags": [], "created_at": now, "updated_at": now,
        }
        return f"ok {entry_id}"

    monkeypatch.setattr(K.KnowledgeStore, "store", broken_store)
    result = gate.check_g2()
    assert result["passed"] is False, "ID 冲突未被 G2 捕获"
    assert any("丢数据" in p or "重复" in p for p in result["extra"]["problems"]), result["detail"]


def test_g2_red_when_silent_failure(monkeypatch):
    """红向：失败返回无机器可判定标记（静默失败）→ G2 必须变红。"""
    import tools.runner as R

    monkeypatch.setattr(R, "execute_runner_tool", lambda args: "返回码: 1")
    result = gate.check_g2()
    assert result["passed"] is False, "静默失败未被 G2 捕获"


# ══════════════════════════════════════════════════════════
# G3 契约漂移
# ══════════════════════════════════════════════════════════

def test_g3_red_when_falsely_closed(monkeypatch, tmp_path):
    """红向：基线标记 closed，但实测探测失败（虚假关闭）→ G3 必须变红。"""
    import tools.calculator as C
    import tools.task_tracker as T

    # 让 K1 探测失败：错误返回不带 ❌
    monkeypatch.setattr(C, "execute_calculator_tool", lambda args: "计算错误: x")
    monkeypatch.setattr(T, "execute_task_tracker_tool", lambda args: "未知操作: x")

    baseline = tmp_path / "contract_baseline.json"
    baseline.write_text(json.dumps({"known_issues": [{"id": "K1", "status": "closed"}]}),
                        encoding="utf-8")
    monkeypatch.setattr(gate, "CONTRACT_BASELINE", baseline)
    monkeypatch.setattr(gate, "KNOWN_FAILURES", tmp_path / "absent.json")

    result = gate.check_g3()
    assert result["passed"] is False, "虚假关闭未被 G3 捕获"


def test_g3_red_when_fixed_but_not_marked(monkeypatch, tmp_path):
    """红向：已修复但仍标记 open（基线漂移）→ G3 必须变红。"""
    baseline = tmp_path / "contract_baseline.json"
    baseline.write_text(json.dumps({"known_issues": [{"id": "K1", "status": "open"}]}),
                        encoding="utf-8")
    monkeypatch.setattr(gate, "CONTRACT_BASELINE", baseline)
    monkeypatch.setattr(gate, "KNOWN_FAILURES", tmp_path / "absent.json")

    result = gate.check_g3()  # K1 实际已修复，探测通过
    assert result["passed"] is False, "已修未标记未被 G3 捕获"


def test_g3_green_with_real_baseline():
    """绿向：真实基线（K1/K2 closed 且探测通过、K3/K4 accepted）→ 必须绿。"""
    result = gate.check_g3()
    assert result["passed"] is True, result["detail"]


# ══════════════════════════════════════════════════════════
# G4 性能回归
# ══════════════════════════════════════════════════════════

def test_g4_red_when_regressed(monkeypatch, tmp_path):
    """红向：基线值远小于当前实测 → G4 必须变红。"""
    cur_platform = f"{platform.system()}-{platform.python_version()}"
    baseline = tmp_path / "perf_baseline.json"
    baseline.write_text(json.dumps({
        "platform": cur_platform,
        "values": {q: 0.000001 for q in
                   ["缓存 优化 性能", "语义检索", "如何设计契约测试"]},
    }), encoding="utf-8")
    monkeypatch.setattr(gate, "PERF_BASELINE", baseline)

    result = gate.check_g4()
    assert result["passed"] is False, "性能退化未被 G4 捕获"


def test_g4_green_when_recorded_platform_differs(monkeypatch, tmp_path):
    """绿向：跨平台基线不可比 → 跳过判定并保持绿，而不是误报退化。"""
    baseline = tmp_path / "perf_baseline.json"
    baseline.write_text(json.dumps({
        "platform": "NonexistentOS-0.0",
        "values": {q: 0.000001 for q in
                   ["缓存 优化 性能", "语义检索", "如何设计契约测试"]},
    }), encoding="utf-8")
    monkeypatch.setattr(gate, "PERF_BASELINE", baseline)

    result = gate.check_g4()
    assert result["passed"] is True
    assert result["extra"].get("skipped") is True


# ══════════════════════════════════════════════════════════
# G5 测试完整性
# ══════════════════════════════════════════════════════════

def test_g5_red_when_tests_not_collected():
    """红向：收集数骤降（测试静默消失）→ 必须报问题。"""
    problems = audit._judge({"collected": 3}, quick=True)
    assert problems, "收集数过低未被捕获"


def test_g5_red_when_mass_skip():
    """红向：大范围 skip 伪装成通过 → 必须报问题。"""
    problems = audit._judge({"passed": 100, "skipped": 500}, quick=False)
    assert problems, "大范围 skip 未被捕获"


def test_g5_red_when_too_few_passed():
    """红向：通过数低于阈值（疑似未真正执行）→ 必须报问题。"""
    problems = audit._judge({"passed": 10, "skipped": 0}, quick=False)
    assert problems, "通过数过低未被捕获"


def test_g5_green_when_normal():
    """绿向：正常统计 → 不得误报。"""
    assert audit._judge({"collected": 602}, quick=True) == []
    assert audit._judge({"passed": 598, "skipped": 2}, quick=False) == []
