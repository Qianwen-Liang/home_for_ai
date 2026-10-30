"""
effect_evaluator — 改进效果量化评估器 v1.0

量化每次自改进的效果：对比改进前后的关键指标变化，
输出结构化的效果评估报告。支持多种指标维度。

设计原则：
  - 可对比：每次评估都是"改进前 vs 改进后"的对比
  - 多维度：覆盖性能、质量、健康、测试四个维度
  - 可追溯：评估结果持久化，支持历史趋势分析
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
EVAL_DIR = SANDBOX_DIR / "memory" / "evaluations"
EVAL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))

# ── 导入性能基准测试目标模块 ────────────────────────────
# 这些是系统关键路径，每次 self_check 都会触发导入
IMPORT_BENCHMARK_MODULES = [
    "tools.knowledge_store",
    "tools.self_check",
    "tools.monitor",
]


@dataclass
class MetricSnapshot:
    """单个时间点的指标快照。"""
    # 性能指标
    total_tool_calls: int = 0
    total_errors: int = 0
    error_rate: float = 0.0
    avg_response_ms: float = 0.0
    slow_tool_count: int = 0         # 响应 > 500ms 的工具数

    # 健康指标
    health_score: int = 0
    health_status: str = "unknown"
    self_check_passed: int = 0
    self_check_failed: int = 0
    self_check_warnings: int = 0

    # 测试指标
    test_total: int = 0
    test_passed: int = 0
    test_failed: int = 0
    test_pass_rate: float = 0.0

    # 安全指标
    consecutive_errors: int = 0
    rescue_activated: bool = False

    # 知识指标
    knowledge_entries: int = 0
    decision_count: int = 0

    # 系统指标
    tool_count: int = 0
    python_file_count: int = 0
    total_code_lines: int = 0

    # 导入性能指标（v2.0 新增：子进程测量绕过模块缓存）
    module_import_ms: float = 0.0          # 关键模块的平均导入耗时（ms）
    module_import_details: dict = field(default_factory=dict)  # {module_name: ms}

    # 功能回归指标（v2.1 新增：核心工具 smoke test）
    smoke_failures: List[str] = field(default_factory=list)   # smoke test 失败项列表

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MetricSnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EffectReport:
    """单次改进的效果评估报告。"""
    eval_id: str
    timestamp: str
    improvement_name: str
    improvement_type: str         # L1~L5 或自定义
    improvement_description: str = ""

    before: Optional[MetricSnapshot] = None
    after: Optional[MetricSnapshot] = None

    # 各维度变化（正数为改进，负数为退化）
    health_delta: int = 0
    error_rate_delta: float = 0.0
    perf_delta_ms: float = 0.0       # 平均响应时间变化
    test_pass_delta: int = 0
    knowledge_delta: int = 0
    import_delta_ms: float = 0.0       # 导入耗时变化（正数=加速）
    import_delta_pct: float = 0.0      # 导入耗时变化百分比

    overall_score: float = 0.0       # -1.0 ~ +1.0，正数为净改进
    verdict: str = "pending"         # improved / degraded / unchanged / pending
    notes: str = ""
    veto_reasons: List[str] = field(default_factory=list)  # 一票否决项命中记录
    smoke_failures: List[str] = field(default_factory=list)  # smoke test 失败项

    def to_dict(self) -> dict:
        d = asdict(self)
        d["before"] = self.before.to_dict() if self.before else None
        d["after"] = self.after.to_dict() if self.after else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EffectReport":
        d = dict(d)
        before = MetricSnapshot.from_dict(d.pop("before")) if d.get("before") else None
        after = MetricSnapshot.from_dict(d.pop("after")) if d.get("after") else None
        return cls(before=before, after=after, **d)


class EffectEvaluator:
    """改进效果量化评估器。

    用法：
        evaluator = EffectEvaluator()

        # 改进前拍快照
        before = evaluator.snapshot()

        # ... 执行改进 ...

        # 改进后拍快照并对比
        report = evaluator.evaluate(
            before=before,
            improvement_name="knowledge_store 延迟加载",
            improvement_type="L2",
            improvement_description="将 sentence-transformers 改为惰性加载",
        )
        print(report.verdict)  # → improved / degraded / unchanged
    """

    def __init__(self):
        self._reports: Dict[str, EffectReport] = {}
        self._load()

    # ── 快照 ────────────────────────────────────────────

    def snapshot(self) -> MetricSnapshot:
        """采集当前系统状态的完整指标快照。"""
        snap = MetricSnapshot()

        # 1. 从 monitor 采集性能指标
        try:
            from tools.monitor import _monitor
            data = _monitor._data
            snap.total_tool_calls = data.get("total_calls", 0)
            snap.total_errors = data.get("total_errors", 0)

            tools_data = data.get("tools", {})
            total_dur = sum(t.get("total_duration", 0) for t in tools_data.values())
            snap.avg_response_ms = round(
                total_dur / snap.total_tool_calls * 1000, 2
            ) if snap.total_tool_calls > 0 else 0
            snap.error_rate = round(
                snap.total_errors / snap.total_tool_calls * 100, 2
            ) if snap.total_tool_calls > 0 else 0

            snap.slow_tool_count = sum(
                1 for t in tools_data.values()
                if t.get("total_calls", 0) > 0
                and t.get("total_duration", 0) / t["total_calls"] * 1000 > 500
            )
            snap.tool_count = len(tools_data)
        except Exception:
            pass

        # 2. 从 health_dashboard 采集健康指标
        try:
            from evolver.health_dashboard import _dashboard
            _dashboard.aggregate()
            snap.health_score = _dashboard.score()
            snap.health_status = str(_dashboard.aggregate().label)
        except Exception:
            pass

        # 3. 从 self_check 采集
        try:
            from tools.self_check import _checker
            _checker.check_all(verbose=False)
            results = _checker.results
            snap.self_check_passed = sum(1 for r in results if r.get("status") == "✅")
            snap.self_check_failed = sum(1 for r in results if r.get("status") == "❌")
            snap.self_check_warnings = sum(1 for r in results if r.get("status") in ("⚠️", "ℹ️"))
        except Exception:
            pass

        # 4. 从 safety_net 采集
        try:
            from tools.safety_net import _safety
            sdata = _safety._data
            snap.consecutive_errors = sdata.get("consecutive_errors", 0)
            snap.rescue_activated = sdata.get("rescue_activated", False)
        except Exception:
            pass

        # 5. 从 test_runner + pytest 采集测试指标（实际运行，禁止估算/默认全过）
        try:
            from tools.test_runner import _runner
            _runner.run_all(verbose=False)
            snap.test_total = len(_runner.results)
            snap.test_passed = sum(1 for r in _runner.results if r.passed)
            snap.test_failed = snap.test_total - snap.test_passed

            # 追加 pytest 单元测试结果（tests/ 目录，覆盖 repair_executors 等真实逻辑）
            py_passed, py_failed, py_total = self._measure_pytest()
            snap.test_total += py_total
            snap.test_passed += py_passed
            snap.test_failed += py_failed

            snap.test_pass_rate = (
                round(snap.test_passed / snap.test_total * 100, 2)
                if snap.test_total else 0.0
            )
            # 同时统计测试文件数量（保留原有统计口径）
            test_dir = SANDBOX_DIR / "tests"
            test_files = list(test_dir.glob("test_*.py")) if test_dir.is_dir() else []
            snap.python_file_count = len(test_files)
        except Exception:
            pass

        # 6. 从 knowledge 采集
        try:
            from tools.knowledge_store import _store
            snap.knowledge_entries = len(_store._data) if hasattr(_store, '_data') else 0
        except Exception:
            pass

        # 7. 代码统计
        try:
            tools_dir = SANDBOX_DIR / "tools"
            py_files = list(tools_dir.glob("*.py"))
            snap.tool_count = len(py_files)

            total_lines = 0
            for pf in py_files:
                try:
                    total_lines += len(pf.read_text(encoding="utf-8").splitlines())
                except Exception:
                    pass
            snap.total_code_lines = total_lines
        except Exception:
            pass

        # 8. 导入性能测量（v2.0 — 子进程绕过缓存）
        try:
            details = {}
            times = []
            for mod in IMPORT_BENCHMARK_MODULES:
                ms = self._measure_module_import_time(mod, runs=2)
                details[mod] = ms
                times.append(ms)
            snap.module_import_details = details
            snap.module_import_ms = round(sum(times) / len(times), 1) if times else 0.0
        except Exception:
            pass

        # 9. 功能回归 smoke test（v2.1 — 实际调用核心工具，捕获"测试未覆盖但功能已坏"）
        snap.smoke_failures = self._run_smoke_test()

        return snap

    # ── 导入性能测量（v2.0 新增）────────────────────────

    @staticmethod
    def _measure_module_import_time(module_name: str, runs: int = 3) -> float:
        """用全新子进程测量模块导入耗时（绕过 Python 模块缓存）。

        每个模块测量 runs 次，取中位数以避免冷启动偏差。

        Args:
            module_name: 如 'tools.knowledge_store'
            runs: 测量次数

        Returns:
            导入耗时（毫秒）
        """
        measurements = []
        for _ in range(runs):
            t0 = time.time()
            try:
                subprocess.run(
                    [sys.executable, "-c", f"import {module_name}"],
                    capture_output=True,
                    timeout=15,
                    cwd=str(SANDBOX_DIR),
                )
                elapsed_ms = (time.time() - t0) * 1000
                measurements.append(elapsed_ms)
            except (subprocess.TimeoutExpired, Exception):
                measurements.append(15000.0)  # 超时记 15s

        if not measurements:
            return 0.0

        measurements.sort()
        # 取中位数
        mid = len(measurements) // 2
        return round(measurements[mid], 1)

    # ── 功能回归 smoke test（v2.1 新增）─────────────────

    @staticmethod
    def _measure_pytest() -> tuple[int, int, int]:
        """运行 tests/ 目录的 pytest 单元测试，返回 (passed, failed, total)。

        用子进程运行，避免污染当前进程状态；带超时保护。
        这是"正确性"维度的补充数据源——test_runner 只测工具模块导入，
        pytest 测的是 tests/ 目录的真实单元测试（如 repair_executors 等）。
        """
        test_dir = SANDBOX_DIR / "tests"
        if not test_dir.is_dir():
            return 0, 0, 0
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_dir), "-q",
                 "--no-header", "--tb=no", "-p", "no:cacheprovider"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(SANDBOX_DIR),
            )
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            # pytest -q 末行形如 "25 failed, 418 passed, 1 warning"
            # 或 "42 passed, 3 failed in 0.57s"——分别匹配 passed/failed 更稳健
            passed = 0
            failed = 0
            m = re.search(r'(\d+)\s+passed', output)
            if m:
                passed = int(m.group(1))
            m = re.search(r'(\d+)\s+failed', output)
            if m:
                failed = int(m.group(1))
            if passed or failed:
                return passed, failed, passed + failed
        except (subprocess.TimeoutExpired, Exception):
            pass
        return 0, 0, 0

    @staticmethod
    def _run_smoke_test() -> List[str]:
        """实际调用核心工具，验证其不报错、返回结构正常。

        用于捕获"单元测试未覆盖、但改进已破坏功能"的改动。
        返回失败项列表（空列表 = 全部通过）。
        """
        failures: List[str] = []

        def _try(label: str, fn):
            try:
                fn()
            except Exception as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")

        # 1. knowledge 语义搜索
        _try("knowledge.search", lambda: (
            __import__("tools.knowledge_store", fromlist=["_store"])._store.search(
                "test", max_results=1
            )
        ))

        # 2. task_tracker 列表
        _try("task_tracker.list", lambda: (
            __import__("tools.task_tracker", fromlist=["_tracker"])._tracker.list_tasks()
        ))

        # 3. self_check 全量检查
        _try("self_check.check_all", lambda: (
            __import__("tools.self_check", fromlist=["_checker"])._checker.check_all(
                verbose=False
            )
        ))

        # 4. decision_engine 建议
        _try("decision_engine.advise", lambda: (
            __import__("tools.decision_engine", fromlist=["_engine"])._engine.advise(
                "smoke test"
            )
        ))

        return failures

    # ═══════════════════════════════════════════════════════

    # ── 评估 ────────────────────────────────────────────

    def evaluate(
        self,
        before: MetricSnapshot,
        improvement_name: str,
        improvement_type: str = "unknown",
        improvement_description: str = "",
    ) -> EffectReport:
        """拍 after 快照并与 before 对比，生成效果评估报告。

        Args:
            before: 改进前的指标快照
            improvement_name: 改进名称
            improvement_type: 改进类型（L1参数调优 / L2性能优化 / L3Bug修复 / L4架构改进 / L5新能力）
            improvement_description: 改进描述

        Returns:
            EffectReport 包含各维度 delta 和综合判定
        """
        after = self.snapshot()

        report = EffectReport(
            eval_id=f"eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            improvement_name=improvement_name,
            improvement_type=improvement_type,
            improvement_description=improvement_description,
            before=before,
            after=after,
        )

        # 计算各维度变化
        report.health_delta = after.health_score - before.health_score
        report.error_rate_delta = round(before.error_rate - after.error_rate, 2)  # 正数=改善
        report.perf_delta_ms = round(before.avg_response_ms - after.avg_response_ms, 2)
        report.knowledge_delta = after.knowledge_entries - before.knowledge_entries

        # 导入性能变化（v2.0 新增）
        if before.module_import_ms > 0 and after.module_import_ms > 0:
            report.import_delta_ms = round(before.module_import_ms - after.module_import_ms, 1)
            report.import_delta_pct = round(
                (before.module_import_ms - after.module_import_ms) / before.module_import_ms * 100, 1
            )
        elif after.module_import_ms > 0:
            report.import_delta_ms = round(-after.module_import_ms, 1)

        test_passed_delta = after.test_passed - before.test_passed
        test_failed_delta = before.test_failed - after.test_failed  # 正数=改善
        report.test_pass_delta = test_passed_delta

        # 计算综合评分（-1.0 ~ +1.0），按 evolution_eval_standards.md v2.0
        veto: List[str] = []
        scores: List[float] = []

        # ── 一票否决项检查（先于评分）──
        # 1. 测试失败数增加
        if after.test_failed > before.test_failed:
            veto.append(f"测试失败数增加: {before.test_failed}→{after.test_failed}")
        # 2. 新引入连续错误
        if before.consecutive_errors == 0 and after.consecutive_errors > 0:
            veto.append(f"新引入连续错误: {after.consecutive_errors} 次")
        # 3. 错误率飙升
        if after.error_rate - before.error_rate >= 10:
            veto.append(f"错误率飙升: {before.error_rate}%→{after.error_rate}%")
        # 4. smoke test 失败
        if after.smoke_failures:
            veto.append(f"smoke test 失败 {len(after.smoke_failures)} 项: {after.smoke_failures[0]}")

        # ── 正确性维度（权重 0.30）──
        if before.test_total > 0:
            test_delta = after.test_passed - before.test_passed
            if abs(test_delta) >= 1:  # 显著性阈值 ±1 个
                scores.append((test_delta / before.test_total) * 0.30)

        # ── 健康维度（权重 0.25）──
        if before.health_score > 0:
            health_delta = after.health_score - before.health_score
            if abs(health_delta) >= 1:  # 显著性阈值 ±1 分
                scores.append(
                    max(-1.0, min(1.0, health_delta / max(before.health_score, 1))) * 0.25
                )

        # ── 性能维度（权重 0.20 = 导入 0.10 + 响应 0.10）──
        # 导入耗时（显著性阈值 5% 或 5ms）
        if before.module_import_ms > 0 and after.module_import_ms > 0:
            import_change = before.module_import_ms - after.module_import_ms  # 正=加速
            if abs(import_change) >= max(before.module_import_ms * 0.05, 5.0):
                scores.append(
                    max(-1.0, min(1.0, import_change / before.module_import_ms)) * 0.10
                )
        # 平均响应时间（显著性阈值 5% 或 1ms）
        if before.avg_response_ms > 0:
            perf_change = before.avg_response_ms - after.avg_response_ms  # 正=加速
            if abs(perf_change) >= max(before.avg_response_ms * 0.05, 1.0):
                scores.append(
                    max(-1.0, min(1.0, perf_change / before.avg_response_ms)) * 0.10
                )

        # ── 健壮性维度（权重 0.15）──
        safety_before = before.consecutive_errors + (3 if before.rescue_activated else 0)
        safety_after = after.consecutive_errors + (3 if after.rescue_activated else 0)
        if safety_before != safety_after:
            safety_change = safety_before - safety_after  # 正=改善
            scores.append(
                max(-1.0, min(1.0, safety_change / max(safety_before, 1))) * 0.15
            )

        # ── 功能回归维度（权重 0.10）──
        # smoke test 从失败→通过，记为正向修复
        if not after.smoke_failures and before.smoke_failures:
            scores.append(0.10)

        report.overall_score = round(sum(scores), 4)
        report.veto_reasons = veto
        report.smoke_failures = after.smoke_failures

        # ── 判定 ──
        if veto:
            report.verdict = "degraded"
        elif report.overall_score >= 0.05:
            report.verdict = "improved"
        elif report.overall_score <= -0.05:
            report.verdict = "degraded"
        else:
            report.verdict = "unchanged"

        # ── 证据一致性验证（v2.2 借鉴 ReasFlow 离线证据验证器）──
        # 不调用 LLM，校验快照/判定/分数是否自洽；不一致则强制降级，
        # 避免"分数与事实不符"的伪改进被采信。
        try:
            from evolver.evidence_verifier import _verifier as _ev_verifier
            ev_report = _ev_verifier.verify_effect_report(report)
            if not ev_report.passed:
                report.verdict = "degraded"
                notes_parts = []
                if report.notes:
                    notes_parts.append(report.notes)
                for issue in ev_report.issues:
                    notes_parts.append(f"[证据校验] {issue.check}: {issue.message}")
                report.notes = " | ".join(notes_parts)
        except Exception:
            pass  # 证据验证器不可用不阻塞评估主流程

        # 保存
        self._reports[report.eval_id] = report
        self._save()

        return report

    # ── 报告生成 ────────────────────────────────────────

    def format_report(self, report: EffectReport) -> str:
        """格式化效果评估报告为可读文本。"""
        verdict_icon = {
            "improved": "📈 改进成功",
            "degraded": "📉 效果退化",
            "unchanged": "➡️ 无明显变化",
        }.get(report.verdict, "❓ 待评估")

        before = report.before
        after = report.after

        lines = [
            f"# 📊 改进效果评估: {report.improvement_name}",
            f"",
            f"**评估 ID**: {report.eval_id}",
            f"**时间**: {report.timestamp}",
            f"**类型**: {report.improvement_type}",
            f"**判定**: {verdict_icon} (综合评分: {report.overall_score:+.3f})",
            f"",
            f"---",
            f"",
            f"## 📈 指标变化",
            f"",
            f"| 维度 | Before | After | Δ |",
            f"|------|--------|-------|---|",
        ]

        if before and after:
            lines.append(
                f"| 🏥 健康评分 | {before.health_score} | {after.health_score} | "
                f"{report.health_delta:+d} |"
            )
            lines.append(
                f"| ❌ 错误率 | {before.error_rate}% | {after.error_rate}% | "
                f"{report.error_rate_delta:+.2f}pp |"
            )
            lines.append(
                f"| ⚡ 平均响应 | {before.avg_response_ms}ms | {after.avg_response_ms}ms | "
                f"{report.perf_delta_ms:+.2f}ms |"
            )
            lines.append(
                f"| 🧪 测试通过 | {before.test_passed} | {after.test_passed} | "
                f"{report.test_pass_delta:+d} |"
            )
            lines.append(
                f"| 📚 知识条目 | {before.knowledge_entries} | {after.knowledge_entries} | "
                f"{report.knowledge_delta:+d} |"
            )
            if before.module_import_ms > 0 or after.module_import_ms > 0:
                lines.append(
                    f"| ⏱️ 导入耗时 | {before.module_import_ms:.0f}ms | {after.module_import_ms:.0f}ms | "
                    f"{report.import_delta_ms:+.0f}ms ({report.import_delta_pct:+.1f}%) |"
                )

        lines.append("")
        lines.append(f"### 说明")
        lines.append(report.improvement_description or "（无描述）")

        if report.notes:
            lines.append(f"")
            lines.append(f"### 备注")
            lines.append(report.notes)

        return "\n".join(lines)

    # ── 历史查询 ────────────────────────────────────────

    def history(self, limit: int = 10) -> List[EffectReport]:
        """返回最近的效果评估报告。"""
        sorted_reports = sorted(
            self._reports.values(),
            key=lambda r: r.timestamp,
            reverse=True,
        )
        return sorted_reports[:limit]

    def trend(self) -> Dict[str, Any]:
        """分析改进趋势。"""
        reports = sorted(self._reports.values(), key=lambda r: r.timestamp)
        if not reports:
            return {"status": "no_data", "message": "暂无评估报告"}

        improved = sum(1 for r in reports if r.verdict == "improved")
        degraded = sum(1 for r in reports if r.verdict == "degraded")
        unchanged = sum(1 for r in reports if r.verdict == "unchanged")

        scores = [r.overall_score for r in reports[-10:]]
        avg_score = sum(scores) / len(scores) if scores else 0

        # 趋势方向
        if len(scores) >= 3:
            recent_avg = sum(scores[-3:]) / 3
            older_avg = sum(scores[:-3]) / (len(scores) - 3) if len(scores) > 3 else recent_avg
            trend_direction = "↗️ 上升" if recent_avg > older_avg + 0.03 else (
                "↘️ 下降" if recent_avg < older_avg - 0.03 else "→ 平稳"
            )
        else:
            trend_direction = "→ 数据不足"

        return {
            "total_evaluations": len(reports),
            "improved_count": improved,
            "degraded_count": degraded,
            "unchanged_count": unchanged,
            "improve_rate": round(improved / len(reports) * 100, 1) if reports else 0,
            "avg_score_recent_10": round(avg_score, 4),
            "trend_direction": trend_direction,
            "latest_verdict": reports[-1].verdict if reports else "n/a",
        }

    # ── 持久化 ──────────────────────────────────────────

    def _save(self):
        filepath = EVAL_DIR / "effect_reports.json"
        data = {eid: r.to_dict() for eid, r in self._reports.items()}
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        filepath = EVAL_DIR / "effect_reports.json"
        if not filepath.is_file():
            return
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            self._reports = {
                eid: EffectReport.from_dict(d) for eid, d in data.items()
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            self._reports = {}


# ── 全局单例 ───────────────────────────────────────────────

_evaluator = EffectEvaluator()


# ── 便捷函数 ──────────────────────────────────────────────

def get_evaluator() -> EffectEvaluator:
    """获取效果评估器实例。"""
    return _evaluator


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "effect_evaluator",
        "description": (
            "改进效果量化评估。采集系统快照并对比改进前后指标变化，"
            "生成效果评估报告。支持快照采集、效果评估、历史趋势分析。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["snapshot", "evaluate", "history", "trend", "report"],
                    "description": (
                        "操作类型：snapshot — 采集当前指标快照；"
                        "evaluate — 对比改进前后生成报告；"
                        "history — 历史评估记录；"
                        "trend — 趋势分析；"
                        "report — 格式化最近报告"
                    ),
                    "default": "snapshot",
                },
                "improvement_name": {
                    "type": "string",
                    "description": "改进名称（evaluate 时需要）",
                    "default": "",
                },
                "improvement_type": {
                    "type": "string",
                    "description": "改进类型 L1~L5",
                    "default": "",
                },
                "description": {
                    "type": "string",
                    "description": "改进描述",
                    "default": "",
                },
                "eval_id": {
                    "type": "string",
                    "description": "评估 ID（report 时需要）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制",
                    "default": 10,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


def execute_effect_evaluator_tool(arguments: dict) -> str:
    """效果评估器工具入口。"""
    action = arguments.get("action", "snapshot")

    try:
        if action == "snapshot":
            snap = _evaluator.snapshot()
            import json as _json
            return _json.dumps(snap.to_dict(), ensure_ascii=False, indent=2)

        elif action == "evaluate":
            name = arguments.get("improvement_name", "unnamed")
            itype = arguments.get("improvement_type", "unknown")
            desc = arguments.get("description", "")

            before = _evaluator.snapshot()
            report = _evaluator.evaluate(
                before=before,
                improvement_name=name,
                improvement_type=itype,
                improvement_description=desc,
            )
            return _evaluator.format_report(report)

        elif action == "history":
            limit = int(arguments.get("limit", 10))
            reports = _evaluator.history(limit)
            if not reports:
                return "暂无评估记录。"
            lines = [f"📊 最近 {len(reports)} 次评估:"]
            for r in reports:
                icon = {"improved": "📈", "degraded": "📉", "unchanged": "➡️"}.get(r.verdict, "❓")
                lines.append(
                    f"  {icon} [{r.timestamp[:19]}] {r.improvement_name} "
                    f"({r.overall_score:+.3f}) — {r.verdict}"
                )
            return "\n".join(lines)

        elif action == "trend":
            trend = _evaluator.trend()
            import json as _json
            return _json.dumps(trend, ensure_ascii=False, indent=2)

        elif action == "report":
            eval_id = arguments.get("eval_id", "")
            if not eval_id:
                # 返回最近一次
                reports = _evaluator.history(1)
                if reports:
                    return _evaluator.format_report(reports[0])
                return "暂无评估报告。"
            # 找指定 ID
            report = _evaluator._reports.get(eval_id)
            if report:
                return _evaluator.format_report(report)
            return f"未找到评估: {eval_id}"

        else:
            return f"未知操作: {action}。可用: snapshot, evaluate, history, trend, report"

    except Exception as exc:
        return f"效果评估器错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    ev = EffectEvaluator()
    before = ev.snapshot()
    print(f"Snapshot taken: health={before.health_score}, "
          f"errors={before.error_rate}%, avg_resp={before.avg_response_ms}ms")

    # 模拟评估
    report = ev.evaluate(
        before=before,
        improvement_name="测试评估",
        improvement_type="L1",
        improvement_description="这是一个自测评估",
    )
    print(ev.format_report(report))
    print(f"\nTrend: {ev.trend()}")
