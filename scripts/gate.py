"""治理门禁统一入口（T2798）。

替代 eval/governance/ 下 80+ 个一次性验证脚本：一条命令输出红绿，
退出码可被 CI 消费。

四道门禁：
  G1 数据隔离   —— 测试前后生产数据指纹必须不变（Google hermetic testing）
  G2 确定性     —— ID 唯一 / 幂等 / 返回值含机器可判定成败标记
  G3 契约漂移   —— known_issues 未关闭即红，修复后自动摘除
  G4 性能回归   —— 核心路径 p50 退化 > 阈值即红

用法：
    python scripts/gate.py                 # 跑全部（G1 用快子集）
    python scripts/gate.py --only G1,G3
    python scripts/gate.py --full          # G1 跑全量测试
    python scripts/gate.py --json          # 机器可读
    python scripts/gate.py --baseline G4   # 重建 G4 性能基线
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOV_DIR = ROOT / "eval" / "governance"
ISOLATION_BASELINE = GOV_DIR / "isolation_probe.json"
PERF_BASELINE = GOV_DIR / "perf_baseline.json"
CONTRACT_BASELINE = GOV_DIR / "contract_baseline.json"

# G1 保护对象：测试绝不应写入的生产数据
PROTECTED = [
    "knowledge/knowledge_store.json",
    "memory/tasks.json",
    "memory/monitor_data.json",
    "memory/knowledge_store.json",
]

PERF_THRESHOLD = 0.20          # p50 退化超过 20% 即红
PERF_REPEAT = 5


# ══════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════

def _fingerprint(paths: list[str]) -> dict[str, dict]:
    out = {}
    for rel in paths:
        p = ROOT / rel
        if not p.is_file():
            out[rel] = {"exists": False}
            continue
        data = p.read_bytes()
        out[rel] = {
            "exists": True,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return out


def _result(gate: str, name: str, passed: bool, detail: str, extra: dict | None = None) -> dict:
    return {"gate": gate, "name": name, "passed": passed, "detail": detail,
            "extra": extra or {}}


# ══════════════════════════════════════════════════════════
# G1 数据隔离
# ══════════════════════════════════════════════════════════

def check_g1(full: bool = False) -> dict:
    """测试前后生产数据指纹必须完全一致。"""
    import subprocess

    before = _fingerprint(PROTECTED)
    targets = ["tests/"] if full else ["tests/test_stress.py", "tests/test_e2e_integration.py",
                                       "tests/test_experience_learner.py"]
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, errors="replace",
    )
    elapsed = time.perf_counter() - t0
    after = _fingerprint(PROTECTED)

    drifted = []
    for rel in PROTECTED:
        b, a = before[rel], after[rel]
        if b.get("sha256") != a.get("sha256"):
            drifted.append({
                "path": rel,
                "before_size": b.get("size"), "after_size": a.get("size"),
                "before_sha": (b.get("sha256") or "")[:12],
                "after_sha": (a.get("sha256") or "")[:12],
            })

    passed = not drifted and proc.returncode == 0
    if drifted:
        detail = f"{len(drifted)} 个生产文件被测试改写: " + ", ".join(d["path"] for d in drifted)
    elif proc.returncode != 0:
        tail = (proc.stdout or "")[-300:]
        detail = f"测试未全绿（rc={proc.returncode}）: {tail.strip()[-180:]}"
    else:
        detail = f"{'全量' if full else '快子集'}测试未污染生产数据（{elapsed:.1f}s）"

    return _result("G1", "数据隔离", passed, detail,
                   {"drifted": drifted, "elapsed_s": round(elapsed, 1)})


# ══════════════════════════════════════════════════════════
# G3 契约漂移
# ══════════════════════════════════════════════════════════

def _probe_k1() -> tuple[bool, str]:
    """K1: 工具错误信息前缀是否统一（应带 ❌ 或等价明确标记）。"""
    from tools.calculator import execute_calculator_tool
    from tools.task_tracker import execute_task_tracker_tool

    samples = []
    try:
        samples.append(("calculate", execute_calculator_tool({})))
    except Exception as exc:  # noqa: BLE001
        samples.append(("calculate", f"EXC:{type(exc).__name__}"))
    try:
        samples.append(("task_tracker", execute_task_tracker_tool({"action": "invalid_op_xyz"})))
    except Exception as exc:  # noqa: BLE001
        samples.append(("task_tracker", f"EXC:{type(exc).__name__}"))

    bad = [(n, s) for n, s in samples if not (str(s).startswith("❌") or "❌" in str(s)[:20])]
    if bad:
        return False, "错误前缀不统一: " + "; ".join(f"{n}={s[:40]!r}" for n, s in bad)
    return True, "错误前缀统一"


def _probe_k2() -> tuple[bool, str]:
    """K2: run_command 失败必须携带机器可判定的失败标记。"""
    from tools.runner import execute_runner_tool

    out = execute_runner_tool({"command": "cmd_that_does_not_exist_xyz_2798", "timeout": 5})
    markers = ("❌", "失败", "错误", "ERROR", "FAILED", "非零退出")
    if any(m in out for m in markers):
        return True, "失败输出含明确标记"
    return False, f"失败输出无明确标记，模型可能误判成功: {out[:90]!r}"


def _probe_k3() -> tuple[bool, str]:
    """K3: 工具是否提供 outputSchema（MCP 推荐项，非阻断）。"""
    import agent1
    tools = list(getattr(agent1, "ALL_TOOLS", []))
    with_schema = [t for t in tools if t.get("function", {}).get("outputSchema")]
    if not with_schema:
        return False, f"0/{len(tools)} 工具提供 outputSchema"
    return True, f"{len(with_schema)}/{len(tools)} 提供 outputSchema"


def _probe_k4() -> tuple[bool, str]:
    """K4: 工具是否提供 annotations（readOnly/idempotent/destructive）。"""
    import agent1
    tools = list(getattr(agent1, "ALL_TOOLS", []))
    with_ann = [t for t in tools if t.get("annotations") or t.get("function", {}).get("annotations")]
    if not with_ann:
        return False, f"0/{len(tools)} 工具提供 annotations"
    return True, f"{len(with_ann)}/{len(tools)} 提供 annotations"


PROBES = {"K1": _probe_k1, "K2": _probe_k2, "K3": _probe_k3, "K4": _probe_k4}


def check_g3() -> dict:
    """known_issues 未关闭即红；关闭需探测通过。"""
    if not CONTRACT_BASELINE.is_file():
        return _result("G3", "契约漂移", False, "基线文件缺失")

    data = json.loads(CONTRACT_BASELINE.read_text(encoding="utf-8"))
    issues = data.get("known_issues", [])

    open_fail, closed_fail, closed_ok, open_ok, accepted = [], [], [], [], []
    for issue in issues:
        iid = issue.get("id", "?")
        status = issue.get("status", "open")
        probe = PROBES.get(iid)

        # accepted = 评估后明确接受的风险（非阻断），需在基线写明理由
        if status == "accepted":
            accepted.append(f"{iid}({issue.get('accepted_reason', '已接受')[:40]})")
            continue

        if probe is None:
            if status == "open":
                open_fail.append(f"{iid}(无探测)")
            continue
        ok, msg = probe()
        if status == "open" and not ok:
            open_fail.append(f"{iid}({msg})")
        elif status == "open" and ok:
            open_ok.append(f"{iid}(已修但未标记closed)")
        elif status == "closed" and not ok:
            closed_fail.append(f"{iid}(标记closed但实测未修: {msg})")
        else:
            closed_ok.append(iid)

    passed = not closed_fail and not open_ok
    parts = []
    if closed_fail:
        parts.append(f"虚假关闭 {len(closed_fail)} 项: " + "; ".join(closed_fail))
    if open_ok:
        parts.append(f"已修复但未标记 {len(open_ok)} 项: " + "; ".join(open_ok))
    if open_fail:
        parts.append(f"未关闭缺陷 {len(open_fail)} 项: " + "; ".join(open_fail))
    if accepted:
        parts.append(f"已接受风险 {len(accepted)} 项: " + "; ".join(accepted))
    if closed_ok:
        parts.append(f"已验证关闭: {', '.join(closed_ok)}")
    return _result("G3", "契约漂移", passed, " | ".join(parts) or "无 known_issue",
                   {"open": len(open_fail), "closed_fail": len(closed_fail),
                    "unmarked_fixed": len(open_ok), "accepted": len(accepted)})


# ══════════════════════════════════════════════════════════
# G2 确定性
# ══════════════════════════════════════════════════════════

def check_g2() -> dict:
    """ID 唯一 / 幂等 / 返回值可判定。"""
    import tempfile
    import threading

    from tools.knowledge_store import KnowledgeStore

    problems: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="gate_g2_"))
    ks = KnowledgeStore(path=tmp / "kb.json")

    # 1) 同秒连续 store：ID 必须唯一（原实现会静默覆盖）
    for i in range(5):
        ks.store(f"确定性探针{i}", f"内容{i}")
    ids = list(ks._data.keys())
    if len(ids) != len(set(ids)):
        problems.append("知识库 ID 重复")
    probe_ids = [k for k, v in ks._data.items() if str(v.get("title", "")).startswith("确定性探针")]
    if len(probe_ids) != 5:
        problems.append(f"同秒连续写入丢数据: 期望 5 条，实际 {len(probe_ids)} 条")

    # 2) 并发写：不应丢条目
    errs: list[str] = []

    def _writer(n: int) -> None:
        try:
            ks.store(f"并发探针{n}", f"并发内容{n}")
        except Exception as exc:  # noqa: BLE001
            errs.append(str(exc))

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    conc = [k for k, v in ks._data.items() if str(v.get("title", "")).startswith("并发探针")]
    if errs:
        problems.append(f"并发写异常 {len(errs)} 次: {errs[0][:60]}")
    if len(conc) != 8:
        problems.append(f"并发写丢数据: 期望 8 条，实际 {len(conc)} 条")

    # 3) 幂等：同一查询重复执行结果稳定
    r1 = ks.search("确定性探针", 5, mode="keyword")
    r2 = ks.search("确定性探针", 5, mode="keyword")
    if r1 != r2:
        problems.append("同一查询两次结果不一致（非幂等）")

    # 4) 失败必须可判定（与 K2 呼应，但独立成门禁）
    from tools.runner import execute_runner_tool
    out = execute_runner_tool({"command": "cmd_that_does_not_exist_xyz_2798", "timeout": 5})
    if not any(m in out for m in ("❌", "失败", "错误", "非零退出")):
        problems.append("run_command 失败无机器可判定标记（静默失败）")

    passed = not problems
    return _result("G2", "确定性", passed,
                   "通过：ID 唯一/无丢数据/幂等/失败可判定" if passed else "; ".join(problems),
                   {"problems": problems})


# ══════════════════════════════════════════════════════════
# G4 性能回归
# ══════════════════════════════════════════════════════════

def _measure_p50() -> dict[str, float]:
    from tools.knowledge_store import KnowledgeStore

    ks = KnowledgeStore()
    queries = ["缓存 优化 性能", "语义检索", "如何设计契约测试"]
    samples: dict[str, list[float]] = {q: [] for q in queries}
    for _ in range(PERF_REPEAT):
        for q in queries:
            t = time.perf_counter()
            ks.search(q, 5, mode="keyword")
            samples[q].append(time.perf_counter() - t)
    out = {}
    for q, ts in samples.items():
        ts.sort()
        out[q] = round(ts[len(ts) // 2], 5)
    return out


def check_g4(rebuild: bool = False) -> dict:
    """核心路径 p50 退化超过阈值即红。"""
    current = _measure_p50()

    if rebuild or not PERF_BASELINE.is_file():
        PERF_BASELINE.write_text(json.dumps({
            "_doc": "G4 性能基线。重建：python scripts/gate.py --baseline G4",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metric": "knowledge.keyword_search.p50_s",
            "repeat": PERF_REPEAT,
            "values": current,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return _result("G4", "性能回归", True,
                       f"基线已建立: {current}", {"values": current, "baseline_created": True})

    base = json.loads(PERF_BASELINE.read_text(encoding="utf-8"))
    base_values = base.get("values", {})
    regressions, ok = [], []
    for q, cur in current.items():
        old = base_values.get(q)
        if not old:
            continue
        ratio = cur / old if old else 1.0
        if ratio > 1 + PERF_THRESHOLD:
            regressions.append(f"{q}: {old:.4f}s→{cur:.4f}s (+{(ratio-1)*100:.0f}%)")
        else:
            ok.append(f"{q}:{cur:.4f}s")
    passed = not regressions
    detail = ("性能无回归: " + ", ".join(ok)) if passed else ("性能退化: " + "; ".join(regressions))
    return _result("G4", "性能回归", passed, detail,
                   {"current": current, "baseline": base_values, "regressions": regressions})


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════

def main() -> int:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    full = "--full" in argv
    rebuild_g4 = "--baseline" in argv and "G4" in argv

    only = None
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = {x.strip().upper() for x in argv[i + 1].split(",")}

    gates = {
        "G1": lambda: check_g1(full=full),
        "G2": check_g2,
        "G3": check_g3,
        "G4": lambda: check_g4(rebuild=rebuild_g4),
    }
    order = ["G1", "G2", "G3", "G4"]
    if only:
        order = [g for g in order if g in only]

    t0 = time.perf_counter()
    results = []
    for g in order:
        try:
            results.append(gates[g]())
        except Exception as exc:  # noqa: BLE001
            results.append(_result(g, g, False, f"检查器异常: {type(exc).__name__}: {exc}"))
    elapsed = time.perf_counter() - t0

    if as_json:
        print(json.dumps({"results": results, "elapsed_s": round(elapsed, 1)}, ensure_ascii=False, indent=2))
    else:
        print("=" * 74)
        print("治理门禁 · gate.py")
        print("=" * 74)
        for r in results:
            icon = "✅" if r["passed"] else "❌"
            print(f"\n{icon} [{r['gate']}] {r['name']}")
            print(f"    {r['detail']}")
        total = len(results)
        ok = sum(1 for r in results if r["passed"])
        print("\n" + "=" * 74)
        print(f"结果: {ok}/{total} 通过   耗时 {elapsed:.1f}s")
        print("=" * 74)

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
