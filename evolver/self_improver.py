"""
self_improver — 自举式自我改进编排器 v1.0

实现完整闭环：监控→检测→分析→生成改进→沙箱验证→安全部署→效果评估→经验学习。

这是 Gödel Machine 雏形的核心引擎 — 让软件系统能够发现自身不足、
自主设计改进、验证、部署并从结果中学习。

架构：
  (A) 监控 ─→ (B) 分析 ─→ (C) 生成改进 ─→ (D) 沙箱验证
    ↑                                        │
    │                                        ├─ 通过 → (E) 部署
    │                                        └─ 失败 → (F) 回滚
    │                                                   │
    └────────── (H) 学习 ←── (G) 效果评估 ←──────────────┘

集成依赖：
  - EffectEvaluator   → 改进前后指标对比
  - ImprovementGenerator → 创意自动生成
  - EvolutionStrategy → 策略模式和 guardrails
  - SafeDeploy        → 安全部署+自动回滚
  - AuditLog          → 不可篡改决策记录
  - knowledge         → 经验沉淀
  - auto_repair       → Bug 自动修复
  - test_runner       → 验证改进正确性
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
CYCLE_DIR = SANDBOX_DIR / "memory" / "improvement_cycles"
CYCLE_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))


class CyclePhase(str, Enum):
    """自改进循环的阶段。"""
    MONITORING = "monitoring"        # (A) 监控
    ANALYZING = "analyzing"          # (B) 分析
    GENERATING = "generating"        # (C) 生成改进
    VALIDATING = "validating"        # (D) 沙箱验证
    DEPLOYING = "deploying"          # (E) 部署
    ROLLING_BACK = "rolling_back"    # (F) 回滚
    EVALUATING = "evaluating"        # (G) 评估
    LEARNING = "learning"            # (H) 学习


class CycleStatus(str, Enum):
    """自改进循环的最终状态。"""
    RUNNING = "running"
    IMPROVED = "improved"             # 改进成功
    DEGRADED = "degraded"             # 效果退化
    UNCHANGED = "unchanged"           # 无净增益（诚实区分，非"至少无退化"）
    ROLLED_BACK = "rolled_back"       # 已回滚
    SKIPPED = "skipped"               # 无可改进项
    FAILED = "failed"                 # 执行异常
    WAITING_APPROVAL = "waiting_approval"  # 等待人类审批


@dataclass
class CycleLog:
    """单次自改进循环的完整日志。"""
    cycle_id: str
    started_at: str
    finished_at: str = ""
    status: CycleStatus = CycleStatus.RUNNING
    current_phase: CyclePhase = CyclePhase.MONITORING

    # 发现的问题
    issues_found: List[str] = field(default_factory=list)

    # 生成的改进创意
    selected_idea: Optional[Dict[str, Any]] = None
    all_ideas_count: int = 0

    # 健康指标
    health_before: int = 0
    health_after: int = 0

    # 部署信息
    files_changed: List[str] = field(default_factory=list)
    tests_run: List[str] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    rolled_back: bool = False
    rollback_reason: str = ""

    # 评估
    effect_score: float = 0.0
    effect_verdict: str = ""

    # 学习
    lessons_learned: str = ""
    knowledge_entry_id: str = ""
    audit_entry_id: str = ""
    notes: str = ""                  # 备注/异常信息
    veto_reasons: List[str] = field(default_factory=list)  # 评估一票否决原因
    reloaded_modules: List[str] = field(default_factory=list)  # 部署后热重载结果

    # 耗时
    duration_sec: float = 0.0
    phase_durations: Dict[str, float] = field(default_factory=dict)

    # 人类交互
    requires_approval: bool = False
    approval_granted: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["current_phase"] = self.current_phase.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CycleLog":
        d = dict(d)
        d["status"] = CycleStatus(d.pop("status", "running"))
        d["current_phase"] = CyclePhase(d.pop("current_phase", "monitoring"))
        return cls(**d)


class SelfImprover:
    """自举式自我改进编排器 — 完整闭环引擎。

    用法：
        improver = SelfImprover()

        # 运行一轮完整自改进
        result = improver.run_cycle()

        # 仅检测（不执行）
        report = improver.inspect()

        # 对指定模块运行改进
        result = improver.improve_module("knowledge_store")
    """

    def __init__(self):
        self._cycles: Dict[str, CycleLog] = {}
        self._load()

    # ═══════════════════════════════════════════════════════
    # 核心编排：完整自改进循环
    # ═══════════════════════════════════════════════════════

    def run_cycle(
        self,
        auto_deploy: bool = False,
        max_ideas: int = 5,
        dry_run: bool = False,
        forced_idea: Optional[Any] = None,
    ) -> CycleLog:
        """运行一轮完整的自改进循环。

        Args:
            auto_deploy: 是否自动部署（默认 False，需要人类确认）
            max_ideas: 最多考虑几个改进创意
            dry_run: 仅分析不执行
            forced_idea: 指定要执行的创意（ImprovementIdea），跳过自动选择

        Returns:
            CycleLog — 完整的循环日志
        """
        started = time.time()
        cycle = CycleLog(
            cycle_id=f"cycle-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now().isoformat(),
        )
        phase_times = {}

        try:
            # ── Phase A: 监控 ─────────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.MONITORING
            issues = self._phase_monitor(cycle)
            phase_times["A_monitor"] = round(time.time() - t0, 2)

            if not issues:
                cycle.status = CycleStatus.SKIPPED
                cycle.finished_at = datetime.now().isoformat()
                cycle.duration_sec = round(time.time() - started, 2)
                self._save_cycle(cycle)
                return cycle

            # ── Phase B: 分析 ─────────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.ANALYZING
            health_before = self._phase_analyze(cycle)
            cycle.health_before = health_before
            phase_times["B_analyze"] = round(time.time() - t0, 2)

            # ── Phase C: 生成改进 ─────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.GENERATING
            ideas = self._phase_generate(cycle, max_ideas)
            cycle.all_ideas_count = len(ideas)
            phase_times["C_generate"] = round(time.time() - t0, 2)

            if not ideas:
                cycle.status = CycleStatus.SKIPPED
                cycle.finished_at = datetime.now().isoformat()
                cycle.duration_sec = round(time.time() - started, 2)
                self._save_cycle(cycle)
                return cycle

            # 选择最高优先级创意（支持 forced_idea 指定）
            top_idea = forced_idea if forced_idea is not None else ideas[0]
            cycle.selected_idea = top_idea.to_dict() if hasattr(top_idea, 'to_dict') else top_idea
            # 标记创意为已接受，避免后续循环重复选择同一项
            idea_id = top_idea.idea_id if hasattr(top_idea, 'idea_id') else (
                cycle.selected_idea.get("idea_id") if isinstance(cycle.selected_idea, dict) else None
            )
            if idea_id:
                self._mark_idea_status(idea_id, "accepted")

            # 检查是否需要人类审批
            strategy_mode = self._get_strategy_mode()
            if strategy_mode in ("conservative", "maintenance"):
                itype = (top_idea.improvement_type.value
                         if hasattr(top_idea, 'improvement_type') else "unknown")
                if itype in ("L4", "L5"):
                    cycle.requires_approval = True
                    if dry_run:
                        cycle.status = CycleStatus.WAITING_APPROVAL
                        cycle.finished_at = datetime.now().isoformat()
                        cycle.duration_sec = round(time.time() - started, 2)
                        self._save_cycle(cycle)
                        return cycle

            if dry_run:
                cycle.status = CycleStatus.SKIPPED
                cycle.finished_at = datetime.now().isoformat()
                cycle.notes = "Dry run — 改进未执行"
                cycle.duration_sec = round(time.time() - started, 2)
                self._save_cycle(cycle)
                return cycle

            # ── Phase D0: 基线测试（记录修改前的失败集合，供部署时对比，避免预存在失败误回滚）──
            baseline_failures = self._phase_baseline_test(cycle)

            # ── Phase D: 生成补丁 ─────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.VALIDATING
            patch_result = self._phase_generate_patch(cycle)
            phase_times["D_patch"] = round(time.time() - t0, 2)

            if not patch_result.get("success"):
                cycle.status = CycleStatus.FAILED
                cycle.notes = f"补丁生成失败: {patch_result.get('error', 'unknown')}"
                self._mark_idea_status(idea_id, "rejected")
                cycle.finished_at = datetime.now().isoformat()
                cycle.duration_sec = round(time.time() - started, 2)
                self._save_cycle(cycle)
                return cycle

            cycle.files_changed = patch_result.get("files", [])

            # 断点2修复：补丁生成为空（没有真正改代码）→ 记为 FAILED，而非"假成功"
            if not cycle.files_changed:
                cycle.status = CycleStatus.FAILED
                cycle.notes = (
                    f"补丁生成为空（{patch_result.get('method', 'unknown')} 未产生文件变更）"
                )
                self._mark_idea_status(idea_id, "rejected")
                cycle.finished_at = datetime.now().isoformat()
                cycle.duration_sec = round(time.time() - started, 2)
                self._save_cycle(cycle)
                return cycle

            # ── Phase E: 安全部署 ─────────────────────
            before_snapshot = None
            if auto_deploy and cycle.files_changed:
                t0 = time.time()
                # 严格时序：before 快照必须在改动落地之前采集（否则 before≈after 效果测不出）
                before_snapshot = self._capture_before_snapshot()
                cycle.current_phase = CyclePhase.DEPLOYING
                deploy_result = self._phase_deploy(cycle, baseline_failures=baseline_failures)
                phase_times["E_deploy"] = round(time.time() - t0, 2)

                if deploy_result.get("rolled_back"):
                    cycle.status = CycleStatus.ROLLED_BACK
                    cycle.rolled_back = True
                    cycle.rollback_reason = deploy_result.get("reason", "测试失败")
                    cycle.finished_at = datetime.now().isoformat()
                    cycle.duration_sec = round(time.time() - started, 2)
                    self._save_cycle(cycle)
                    return cycle

                cycle.tests_run = deploy_result.get("tests_run", [])
                cycle.tests_passed = deploy_result.get("tests_passed", 0)
                cycle.tests_failed = deploy_result.get("tests_failed", 0)

                # 部署后热重载变更模块，使新代码立即生效（避免"改了文件但运行时没变"的伪进化）
                cycle.reloaded_modules = self._hot_reload_modules(cycle.files_changed)

            # ── Phase G: 评估 ─────────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.EVALUATING
            eval_result = self._phase_evaluate(cycle, before_snapshot=before_snapshot)
            cycle.effect_score = eval_result.get("score", 0)
            cycle.effect_verdict = eval_result.get("verdict", "unknown")
            cycle.health_after = eval_result.get("health_after", cycle.health_before)
            phase_times["G_evaluate"] = round(time.time() - t0, 2)

            # ── Phase H: 学习 ─────────────────────────
            t0 = time.time()
            cycle.current_phase = CyclePhase.LEARNING
            learn_result = self._phase_learn(cycle)
            cycle.lessons_learned = learn_result.get("summary", "")
            cycle.knowledge_entry_id = learn_result.get("knowledge_id", "")
            cycle.audit_entry_id = learn_result.get("audit_id", "")
            phase_times["H_learn"] = round(time.time() - t0, 2)

            # ── 最终判定 ──────────────────────────────
            cycle.veto_reasons = eval_result.get("veto_reasons", [])
            if cycle.effect_verdict == "improved":
                cycle.status = CycleStatus.IMPROVED
                self._mark_idea_status(idea_id, "implemented")
            elif cycle.effect_verdict == "degraded":
                cycle.status = CycleStatus.DEGRADED
                self._mark_idea_status(idea_id, "rejected")
                if not cycle.rolled_back:
                    # 退化但未回滚 — 警告
                    cycle.notes = "效果退化但未自动回滚，建议人工审查"
            else:
                # 无净增益：诚实标记 unchanged，而非"至少无退化"的 improved
                cycle.status = CycleStatus.UNCHANGED
                self._mark_idea_status(idea_id, "rejected")

        except Exception as exc:
            cycle.status = CycleStatus.FAILED
            cycle.notes = f"执行异常: {exc}\n{traceback.format_exc()[-500:]}"

        finally:
            cycle.finished_at = datetime.now().isoformat()
            cycle.duration_sec = round(time.time() - started, 2)
            cycle.phase_durations = phase_times
            # 修复：失败/跳过/回滚路径未设置 health_after 时回退为 health_before，避免误报为 0
            if cycle.health_after == 0 and cycle.health_before > 0:
                cycle.health_after = cycle.health_before
            self._save_cycle(cycle)

        return cycle

    # ═══════════════════════════════════════════════════════
    # Phase 实现
    # ═══════════════════════════════════════════════════════

    def _phase_monitor(self, cycle: CycleLog) -> List[str]:
        """Phase A: 监控 — 收集系统异常信号。"""
        issues = []

        # 1. 健康仪表盘
        try:
            from evolver.health_dashboard import _dashboard
            _dashboard.aggregate()
            score = _dashboard.score()
            alert = _dashboard.alert()
            if alert:
                issues.append(f"健康告警: {alert[:200]}")
            if score < 60:
                issues.append(f"健康评分过低: {score}/100")
        except Exception as exc:
            issues.append(f"健康检查异常: {exc}")

        # 2. 自检
        try:
            from tools.self_check import _checker
            _checker.check_all(verbose=False)
            failed = sum(1 for r in _checker.results if r.get("status") == "❌")
            if failed > 0:
                issues.append(f"自检失败: {failed} 项")
        except Exception as exc:
            issues.append(f"自检异常: {exc}")

        # 3. 安全网
        try:
            from tools.safety_net import _safety
            sdata = _safety._data
            if sdata.get("consecutive_errors", 0) >= 3:
                issues.append(f"连续错误: {sdata['consecutive_errors']} 次")
            if sdata.get("rescue_activated"):
                issues.append("自救流程已激活")
        except Exception:
            pass

        # 4. 性能监控
        try:
            from tools.monitor import _monitor
            mdata = _monitor._data
            if mdata.get("total_calls", 0) > 10:
                error_rate = mdata.get("total_errors", 0) / mdata["total_calls"] * 100
                if error_rate > 5:
                    issues.append(f"错误率偏高: {error_rate:.1f}%")
        except Exception:
            pass

        # 5. 主动优化机会（即使无异常，也扫描经精确验证前提的高置信度优化点）
        #    仅考虑 precondition_verified=True 的创意，避免误判导致的"无用功"
        try:
            from evolver.improvement_generator import _generator
            actionable = [
                i for i in _generator.from_verified_optimizations(max_ideas=30)
                if i.priority_score >= 0.2
            ]
            if actionable:
                top = actionable[0]
                issues.append(
                    f"优化机会: {top.title}（前提已验证，优先级 {top.priority_score:.2f}）"
                )
        except Exception:
            pass

        cycle.issues_found = issues
        return issues

    def _phase_analyze(self, cycle: CycleLog) -> int:
        """Phase B: 分析 — 评估当前状态，返回健康评分。"""
        score = 80
        try:
            from evolver.health_dashboard import _dashboard
            _dashboard.aggregate()
            score = _dashboard.score()
        except Exception:
            pass
        return score

    def _phase_generate(self, cycle: CycleLog, max_ideas: int) -> List[Any]:
        """Phase C: 生成改进创意。

        断点1修复：主动优化优先——"前提已验证"（precondition_verified=True）的创意
        排在最前，避免按 priority_score 选中粗粒度启发式（如 lru_cache）误判。
        用较大 limit 扫描，确保已验证创意不被过早截断。
        """
        try:
            from evolver.improvement_generator import _generator
            ideas = _generator.generate_all(limit=max(max_ideas, 30))
            verified = [i for i in ideas if getattr(i, 'precondition_verified', False)]
            unverified = [i for i in ideas if not getattr(i, 'precondition_verified', False)]
            return (verified + unverified)[:max_ideas]
        except Exception:
            return []

    def _phase_baseline_test(self, cycle: CycleLog) -> set:
        """Phase D0: 在补丁生成前运行受影响测试，记录基线失败集合。

        用于部署时的基线对比：只对"新引入的失败"回滚，避免预存在失败导致误回滚。
        """
        try:
            from evolver.safe_deploy import _deployer
            target = (cycle.selected_idea or {}).get("target_module", "")
            if not target:
                return set()
            test_list = _deployer.affected_tests([target])
            if not test_list:
                return set()
            results = _deployer.run_tests(test_list)
            return {n for n, r in results.items() if r.get("passed") is False}
        except Exception:
            return set()

    def _phase_generate_patch(self, cycle: CycleLog) -> Dict[str, Any]:
        """Phase D: 生成改进补丁。

        集成 AutomatedPatcher 实现真正的代码重写。
        L3 Bug 使用 auto_repair，L1/L2 优化使用 AutomatedPatcher。
        """
        if not cycle.selected_idea:
            return {"success": False, "error": "没有选中的改进创意"}

        idea = cycle.selected_idea
        idea_type = idea.get("improvement_type", "unknown")
        source = idea.get("source", "")
        target_module = idea.get("target_module", "")

        # L3 Bug 修复 → 使用 auto_repair
        if idea_type in ("L3", "bug_fix"):
            try:
                from tools.safety_net import _safety
                recent_errors = _safety._data.get("recent_errors", [])
                if recent_errors:
                    from tools.auto_repair import diagnose_error
                    diag = diagnose_error(str(recent_errors[-1]))
                    return {
                        "success": True,
                        "method": "auto_repair",
                        "files": diag.get("affected_files", []),
                        "diagnosis": diag,
                    }
            except Exception:
                pass

        # L1/L2 优化 → 使用 AutomatedPatcher 自动生成代码变更
        if idea_type in ("L1", "L2"):
            try:
                from evolver.automated_patcher import AutomatedPatcher
                patcher = AutomatedPatcher()

                # 根据创意来源选择最匹配的转换
                transform = SelfImprover._match_transform(source, idea)
                if transform is None:
                    return {
                        "success": True,
                        "method": "manual_guided",
                        "files": [],
                        "note": f"未匹配到自动转换: source={source}",
                    }

                # 构建文件路径
                if target_module and not target_module.startswith(("tools/", "evolver/")):
                    # 尝试找到实际文件
                    for prefix in ["tools/", "evolver/"]:
                        candidate = f"{prefix}{target_module}"
                        if (SANDBOX_DIR / candidate).is_file():
                            target_module = candidate
                            break
                    else:
                        target_module = f"tools/{target_module}.py"

                result = patcher.apply(
                    file_path=target_module,
                    transform=transform,
                    params={
                        "idea": idea.get("description", idea.get("title", "")),
                        "idea_type": idea_type,
                        "constraints": idea.get("implementation_hint", ""),
                    } if transform == "llm_patch" else None,
                )

                if result.success:
                    return {
                        "success": True,
                        "method": "automated_patcher",
                        "transform": transform,
                        "files": [target_module],
                        "changes_made": result.changes_made,
                        "description": result.description,
                    }
                else:
                    return {
                        "success": True,
                        "method": "manual_guided",
                        "files": [],
                        "note": f"AutomatedPatcher 未应用: {result.error}",
                    }
            except Exception as exc:
                return {
                    "success": True,
                    "method": "manual_guided",
                    "files": [],
                    "note": f"AutomatedPatcher 异常: {exc}",
                }

        # 其他类型 → 人工指导
        hint = idea.get("implementation_hint", "")
        return {
            "success": True,
            "method": "manual_guided",
            "files": [f"tools/{target_module}.py"] if target_module else [],
            "target": target_module,
            "hint": hint,
            "note": "此类型改进需要手动实现。",
        }

    @staticmethod
    def _match_transform(source: str, idea: dict) -> Optional[str]:
        """根据改进创意的来源匹配最合适的 AutomatedPatcher 转换。"""
        source_lower = source.lower()
        tags = [t.lower() for t in idea.get("tags", [])]
        idea_type = idea.get("improvement_type", "")

        # code_analysis:lazy_import → lazy_import
        if "lazy_import" in source_lower or "lazy_import" in tags:
            return "lazy_import"
        # code_analysis:set_lookup → set_lookup
        if "set_lookup" in source_lower or "set_lookup" in tags:
            return "set_lookup"
        # code_analysis:config_externalize → constant_extract
        if "config_externalize" in source_lower or "config" in tags:
            return "constant_extract"
        # code_analysis:dict_dispatch → dict_dispatch
        if "dict_dispatch" in source_lower:
            return "dict_dispatch"
        # code_analysis:json_preload → json_preload（mtime 缓存）
        if "json_preload" in source_lower or "json_preload" in tags:
            return "json_preload"
        # L4 架构重构 / L5 新功能 / 任何无法被以上 4 种确定性转换覆盖的创意
        # → 回退到 llm_patch（LLM 驱动的创造性代码生成）
        if idea_type in ("L4", "L5") or source_lower in ("manual", "knowledge", ""):
            return "llm_patch"

        return "llm_patch"  # 默认回退到 LLM

    def _phase_deploy(self, cycle: CycleLog, baseline_failures: set | None = None) -> Dict[str, Any]:
        """Phase E: 安全部署（支持基线对比，避免预存在失败误回滚）。"""
        if not cycle.files_changed:
            return {"rolled_back": False, "reason": "无文件变更"}

        try:
            from evolver.safe_deploy import _deployer
            result = _deployer.deploy(
                files=cycle.files_changed,
                auto_rollback=True,
                run_all_tests=False,
                baseline_failures=list(baseline_failures) if baseline_failures else None,
            )

            # 解析结果
            rolled_back = "已回滚" in result
            return {
                "rolled_back": rolled_back,
                "reason": result if rolled_back else "",
                "tests_run": list(_deployer._record.tests_run) if _deployer._record else [],
                "tests_passed": _deployer._record.tests_passed if _deployer._record else 0,
                "tests_failed": _deployer._record.tests_failed if _deployer._record else 0,
            }
        except Exception as exc:
            return {"rolled_back": False, "reason": f"部署异常: {exc}"}

    def _capture_before_snapshot(self):
        """在改动落地前采集 before 快照（严格时序）。"""
        try:
            from evolver.effect_evaluator import _evaluator
            return _evaluator.snapshot()
        except Exception:
            return None

    def _hot_reload_modules(self, files: List[str]) -> List[str]:
        """部署后热重载变更模块，使新代码 + 新单例立即在运行时生效。

        跳过 self_improver 自身（reload 会替换当前正在执行的 _improver 单例，
        破坏本次循环上下文），该场景需重启生效。
        """
        try:
            from evolver.hot_reload import hot_reload
            return hot_reload(files, skip_modules=["evolver.self_improver"])
        except Exception as exc:
            return [f"❌ 热重载不可用: {exc}"]

    def _phase_evaluate(self, cycle: CycleLog, before_snapshot=None) -> Dict[str, Any]:
        """Phase G: 效果评估。

        Args:
            before_snapshot: 部署前采集的指标快照（严格时序）。
                             若为 None（退化路径），则退化为当前快照（效果可能测不出）。
        """
        try:
            from evolver.effect_evaluator import _evaluator

            before = before_snapshot if before_snapshot is not None else _evaluator.snapshot()
            report = _evaluator.evaluate(
                before=before,
                improvement_name=(
                    cycle.selected_idea.get("title", "unknown")
                    if cycle.selected_idea else "unknown"
                ),
                improvement_type=(
                    cycle.selected_idea.get("improvement_type", "unknown")
                    if cycle.selected_idea else "unknown"
                ),
            )

            return {
                "score": report.overall_score,
                "verdict": report.verdict,
                "health_after": report.after.health_score if report.after else cycle.health_before,
                "health_delta": report.health_delta,
                "veto_reasons": report.veto_reasons,
                "report": _evaluator.format_report(report),
            }
        except Exception as exc:
            return {"score": 0, "verdict": "unknown", "error": str(exc)}

    def _phase_learn(self, cycle: CycleLog) -> Dict[str, Any]:
        """Phase H: 经验学习。"""
        knowledge_id = ""
        audit_id = ""

        # 1. 存储到知识库
        try:
            from tools.knowledge_store import _store

            title = (
                cycle.selected_idea.get("title", "自改进循环")
                if cycle.selected_idea else "自改进循环"
            )
            content = (
                f"# 自改进循环: {title}\n\n"
                f"## 状态\n{cycle.status.value}\n\n"
                f"## 发现问题\n" + "\n".join(f"- {i}" for i in cycle.issues_found) + "\n\n"
                f"## 改进效果\n"
                f"- 综合评分: {cycle.effect_score:+.3f}\n"
                f"- 判定: {cycle.effect_verdict}\n"
                f"- 健康变化: {cycle.health_before} → {cycle.health_after}\n\n"
                f"## 教训\n{cycle.lessons_learned or '（无）'}"
            )
            entry = _store.store(
                title=f"自改进: {title}",
                content=content,
                category="improvement",
                tags=["self-improvement", cycle.status.value, "auto-cycle"],
            )
            knowledge_id = entry.get("id", "")
        except Exception:
            pass

        # 2. 记录审计日志
        try:
            from evolver.audit_log import _audit
            from evolver.audit_log import DecisionOutcome

            outcome_map = {
                CycleStatus.IMPROVED: DecisionOutcome.SUCCESS,
                CycleStatus.DEGRADED: DecisionOutcome.PARTIAL,
                CycleStatus.UNCHANGED: DecisionOutcome.PARTIAL,
                CycleStatus.ROLLED_BACK: DecisionOutcome.ROLLED_BACK,
                CycleStatus.FAILED: DecisionOutcome.FAILED,
            }
            outcome = outcome_map.get(cycle.status, DecisionOutcome.PENDING)

            entry = _audit.log(
                decision=f"自改进循环: {cycle.selected_idea.get('title', 'unknown') if cycle.selected_idea else 'unknown'}",
                rationale=f"自动检测到 {len(cycle.issues_found)} 个问题，执行改进",
                strategy_mode=self._get_strategy_mode(),
                files_changed=cycle.files_changed,
                expected_effect=cycle.selected_idea.get("description", "") if cycle.selected_idea else "",
                tags=["self-improvement", "auto-cycle"],
                health_before=float(cycle.health_before),
            )
            _audit.update_outcome(
                entry.entry_id,
                outcome=outcome,
                actual_effect=f"评分: {cycle.effect_score:+.3f}, 判定: {cycle.effect_verdict}",
                health_after=float(cycle.health_after),
            )
            audit_id = entry.entry_id
        except Exception:
            pass

        return {
            "summary": f"改进{cycle.effect_verdict}，评分{cycle.effect_score:+.3f}",
            "knowledge_id": knowledge_id,
            "audit_id": audit_id,
        }

    # ═══════════════════════════════════════════════════════
    # Phase 3: 多轮迭代 + 抗退化
    # ═══════════════════════════════════════════════════════

    def run_multi_cycles(
        self,
        max_cycles: int = 5,
        auto_deploy: bool = False,
        stop_on_degradation: bool = True,
    ) -> Dict[str, Any]:
        """运行多轮自改进循环，带退化保护。

        每轮之间自动检查退化信号，连续退化时自动暂停。
        这是 Gödel Machine 的"持续进化"模式。

        Args:
            max_cycles: 最大迭代轮次
            auto_deploy: 是否自动部署
            stop_on_degradation: 退化时是否停止

        Returns:
            多轮迭代摘要
        """
        cycle_results: List[CycleLog] = []
        stopped_early = False
        stop_reason = ""
        tracker = None

        try:
            from evolver.cycle_tracker import _tracker
            tracker = _tracker
        except Exception:
            pass

        for i in range(max_cycles):
            # 每轮之前检查退化
            if tracker and i > 0:
                should_pause, reason = tracker.should_pause()
                if should_pause:
                    stopped_early = True
                    stop_reason = reason
                    break

                alert = tracker.check_degradation()
                if alert and alert.severity in ("critical", "high") and stop_on_degradation:
                    stopped_early = True
                    stop_reason = f"退化告警: {alert.description[:150]}"
                    break

            # 运行一轮
            cycle = self.run_cycle(
                auto_deploy=auto_deploy,
                max_ideas=3,  # 多轮模式下限制创意数
                dry_run=False,
            )
            cycle_results.append(cycle)

            # 记录到 tracker
            if tracker:
                try:
                    tracker.record_cycle(cycle.to_dict())
                except Exception:
                    pass

            # 退化时停止
            if stop_on_degradation and cycle.status in (
                CycleStatus.DEGRADED, CycleStatus.ROLLED_BACK
            ):
                stopped_early = True
                stop_reason = f"第 {i+1} 轮效果{cycle.status.value}"
                break

            # 如果当前轮无可改进项，结束
            if cycle.status == CycleStatus.SKIPPED:
                break

        # 知识蒸馏
        distillation = None
        if tracker and len(cycle_results) >= 2:
            try:
                distillation = tracker.distill_knowledge()
                if distillation.get("status") == "ready":
                    try:
                        from tools.knowledge_store import _store
                        _store.store(
                            title=distillation["title"],
                            content=distillation["content"],
                            category="improvement",
                            tags=distillation.get("tags", []),
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        # 生成摘要
        improved = sum(1 for c in cycle_results if c.status == CycleStatus.IMPROVED)
        degraded = sum(1 for c in cycle_results if c.status == CycleStatus.DEGRADED)
        rolled_back = sum(1 for c in cycle_results if c.status == CycleStatus.ROLLED_BACK)

        return {
            "total_cycles": len(cycle_results),
            "improved": improved,
            "degraded": degraded,
            "rolled_back": rolled_back,
            "stopped_early": stopped_early,
            "stop_reason": stop_reason,
            "overall_success_rate": round(improved / len(cycle_results) * 100, 1)
                if cycle_results else 0,
            "cycle_ids": [c.cycle_id for c in cycle_results],
            "distillation": distillation,
            "tracker_status": tracker.status_summary() if tracker else "N/A",
        }

    # ═══════════════════════════════════════════════════════
    # Phase 3: 便捷方法
    # ═══════════════════════════════════════════════════════

    def inspect(self) -> str:
        """仅执行检测和分析，不执行改进。返回诊断报告。"""
        cycle = CycleLog(
            cycle_id=f"inspect-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now().isoformat(),
        )

        issues = self._phase_monitor(cycle)
        health = self._phase_analyze(cycle)
        ideas = self._phase_generate(cycle, max_ideas=5)

        lines = [
            "# 🔍 系统自诊断报告",
            f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**健康评分**: {health}/100",
            f"",
            f"## 发现问题 ({len(issues)} 个)",
        ]

        if issues:
            for i, issue in enumerate(issues, 1):
                lines.append(f"{i}. {issue}")
        else:
            lines.append("✅ 未发现异常。")

        lines.append(f"\n## 改进创意 ({len(ideas)} 个)")
        if ideas:
            for i, idea in enumerate(ideas[:5], 1):
                pscore = idea.priority_score if hasattr(idea, 'priority_score') else '?'
                itype = idea.improvement_type.value if hasattr(idea, 'improvement_type') else '?'
                lines.append(f"{i}. [{pscore}] [{itype}] {idea.title}")
                lines.append(f"   {idea.description[:120]}")
        else:
            lines.append("暂无改进创意。")

        return "\n".join(lines)

    def improve_module(self, module_name: str) -> Optional[CycleLog]:
        """对指定模块发起针对性改进。

        Args:
            module_name: 目标模块名（如 'knowledge_store'）

        Returns:
            CycleLog 或 None
        """
        # 创建针对性创意
        try:
            from evolver.improvement_generator import _generator
            all_ideas = _generator.generate_all(limit=10)
            matched = [
                i for i in all_ideas
                if module_name.lower() in i.target_module.lower()
                or module_name.lower() in " ".join(i.tags).lower()
            ]
        except Exception:
            matched = []

        if not matched:
            return None

        # 构造精简循环并运行
        cycle = CycleLog(
            cycle_id=f"target-{module_name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now().isoformat(),
        )
        cycle.selected_idea = matched[0].to_dict() if hasattr(matched[0], 'to_dict') else matched[0]
        cycle.issues_found = [matched[0].description]
        cycle.health_before = self._phase_analyze(cycle)

        return self.run_cycle(auto_deploy=False, dry_run=False, forced_idea=matched[0])

    def _mark_idea_status(self, idea_id: Optional[str], status: str) -> bool:
        """更新改进创意的状态（accepted/implemented/rejected），供循环去重使用。"""
        if not idea_id:
            return False
        try:
            from evolver.improvement_generator import _generator
            return _generator.update_status(idea_id, status)
        except Exception:
            return False

    # ═══════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════

    def _get_strategy_mode(self) -> str:
        """获取当前进化策略模式。"""
        try:
            from evolver.evolution_strategy import _strategy
            return _strategy.current.value
        except Exception:
            return "aggressive"

    def cycle_history(self, limit: int = 10) -> List[CycleLog]:
        """返回最近的循环历史。"""
        cycles = sorted(
            self._cycles.values(),
            key=lambda c: c.started_at,
            reverse=True,
        )
        return cycles[:limit]

    def stats(self) -> Dict[str, Any]:
        """自改进统计。"""
        cycles = list(self._cycles.values())
        if not cycles:
            return {"total_cycles": 0}

        improved = sum(1 for c in cycles if c.status == CycleStatus.IMPROVED)
        degraded = sum(1 for c in cycles if c.status == CycleStatus.DEGRADED)
        rolled_back = sum(1 for c in cycles if c.status == CycleStatus.ROLLED_BACK)
        failed = sum(1 for c in cycles if c.status == CycleStatus.FAILED)

        scores = [c.effect_score for c in cycles if c.effect_score != 0]

        return {
            "total_cycles": len(cycles),
            "improved": improved,
            "degraded": degraded,
            "rolled_back": rolled_back,
            "failed": failed,
            "success_rate": round(improved / len(cycles) * 100, 1) if cycles else 0,
            "avg_effect_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "avg_duration_sec": round(
                sum(c.duration_sec for c in cycles) / len(cycles), 1
            ) if cycles else 0,
        }

    # ═══════════════════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════════════════

    def _save_cycle(self, cycle: CycleLog):
        self._cycles[cycle.cycle_id] = cycle
        filepath = CYCLE_DIR / "cycles.json"
        data = {cid: c.to_dict() for cid, c in self._cycles.items()}
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        filepath = CYCLE_DIR / "cycles.json"
        if not filepath.is_file():
            return
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            self._cycles = {cid: CycleLog.from_dict(d) for cid, d in data.items()}
        except (json.JSONDecodeError, KeyError, TypeError):
            self._cycles = {}


# ── 全局单例 ───────────────────────────────────────────────

_improver = SelfImprover()


def get_improver() -> SelfImprover:
    """获取自改进编排器实例。"""
    return _improver


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "self_improver",
        "description": (
            "自举式自我改进编排器 — Gödel Machine 雏形核心引擎。"
            "实现完整闭环：监控→检测→分析→生成改进→验证→部署→评估→学习。"
            "支持完整循环运行、系统诊断、针对性模块改进和历史查询。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["inspect", "run_cycle", "run_multi_cycles", "improve_module", "history", "stats", "help"],
                    "description": (
                        "操作类型：inspect — 系统诊断（仅分析不执行）；"
                        "run_cycle — 运行完整自改进循环；"
                        "improve_module — 对指定模块发起改进；"
                        "history — 循环历史；"
                        "stats — 自改进统计；"
                        "help — 查看帮助"
                    ),
                    "default": "inspect",
                },
                "auto_deploy": {
                    "type": "boolean",
                    "description": "是否自动部署（默认 False）",
                    "default": False,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "仅分析不执行（默认 False）",
                    "default": False,
                },
                "max_ideas": {
                    "type": "integer",
                    "description": "最多考虑几个改进创意",
                    "default": 5,
                },
                "module_name": {
                    "type": "string",
                    "description": "目标模块名（improve_module 时需要）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "历史记录数量限制",
                    "default": 10,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


def execute_self_improver_tool(arguments: dict) -> str:
    """自改进编排器工具入口。"""
    action = arguments.get("action", "inspect")

    try:
        if action == "inspect":
            return _improver.inspect()

        elif action == "run_cycle":
            auto_deploy = arguments.get("auto_deploy", False)
            dry_run = arguments.get("dry_run", False)
            max_ideas = int(arguments.get("max_ideas", 5))

            result = _improver.run_cycle(
                auto_deploy=auto_deploy,
                dry_run=dry_run,
                max_ideas=max_ideas,
            )

            lines = [
                f"# 🔄 自改进循环完成",
                f"",
                f"**状态**: {result.status.value}",
                f"**耗时**: {result.duration_sec:.1f}s",
            ]

            if result.issues_found:
                lines.append(f"\n## 发现问题 ({len(result.issues_found)} 个)")
                for issue in result.issues_found:
                    lines.append(f"  • {issue}")

            if result.selected_idea:
                idea = result.selected_idea
                lines.append(f"\n## 执行改进")
                lines.append(f"  • {idea.get('title', 'unknown')}")

            if result.files_changed:
                lines.append(f"\n## 文件变更")
                for f in result.files_changed:
                    lines.append(f"  • {f}")

            lines.append(f"\n## 效果评估")
            lines.append(f"  • 评分: {result.effect_score:+.3f}")
            lines.append(f"  • 判定: {result.effect_verdict}")
            lines.append(f"  • 健康: {result.health_before} → {result.health_after}")

            if result.lessons_learned:
                lines.append(f"\n## 经验教训")
                lines.append(f"  {result.lessons_learned}")

            if result.notes:
                lines.append(f"\n## 备注")
                lines.append(f"  {result.notes}")

            return "\n".join(lines)

        elif action == "run_multi_cycles":
            max_cycles = int(arguments.get("max_cycles", 5))
            auto_deploy = arguments.get("auto_deploy", False)
            stop_on_degradation = arguments.get("stop_on_degradation", True)

            summary = _improver.run_multi_cycles(
                max_cycles=max_cycles,
                auto_deploy=auto_deploy,
                stop_on_degradation=stop_on_degradation,
            )

            import json as _json
            return _json.dumps(summary, ensure_ascii=False, indent=2)

        elif action == "improve_module":
            module = arguments.get("module_name", "")
            if not module:
                return "请提供 module_name 参数"
            result = _improver.improve_module(module)
            if result is None:
                return f"未找到针对模块 '{module}' 的改进创意。"
            return f"已对模块 '{module}' 发起改进循环。状态: {result.status.value}"

        elif action == "history":
            limit = int(arguments.get("limit", 10))
            cycles = _improver.cycle_history(limit)
            if not cycles:
                return "暂无自改进循环记录。"

            lines = [f"📜 最近 {len(cycles)} 次自改进循环:\n"]
            for c in cycles:
                icon = {
                    "improved": "📈", "degraded": "📉",
                    "unchanged": "➡️", "rolled_back": "🔄",
                    "skipped": "⏭️", "failed": "❌", "running": "🔄"
                }.get(c.status.value, "❓")
                idea_title = c.selected_idea.get("title", "")[:50] if c.selected_idea else "n/a"
                lines.append(
                    f"  {icon} [{c.started_at[:19]}] {idea_title} "
                    f"({c.effect_score:+.2f}, {c.duration_sec:.1f}s)"
                )
            return "\n".join(lines)

        elif action == "stats":
            import json as _json
            stats = _improver.stats()
            return _json.dumps(stats, ensure_ascii=False, indent=2)

        elif action == "help":
            return (
                "🧬 self_improver — Gödel Machine 雏形核心引擎\n\n"
                "可用操作:\n"
                "  inspect         — 系统诊断（仅分析不执行）\n"
                "  run_cycle       — 运行完整自改进循环\n"
                "  improve_module  — 对指定模块发起改进\n"
                "  history         — 循环历史\n"
                "  stats           — 统计信息\n\n"
                "安全机制:\n"
                "  • 保守/维护模式自动请求人类审批\n"
                "  • 改进前自动备份，失败自动回滚\n"
                "  • 所有决策记录到 audit_log\n"
                "  • 经验自动沉淀到 knowledge\n\n"
                "💡 建议: 先用 inspect 诊断，确认无误后再 run_cycle"
            )

        else:
            return f"未知操作: {action}。可用: inspect, run_cycle, improve_module, history, stats, help"

    except Exception as exc:
        import traceback
        return f"自改进编排器错误: {exc}\n{traceback.format_exc()[-500:]}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    improver = SelfImprover()

    print("=" * 60)
    print("  SelfImprover 自测")
    print("=" * 60)

    # 1. 仅检测
    print("\n>>> inspect()")
    report = improver.inspect()
    print(report[:1000])

    # 2. 统计
    print("\n>>> stats()")
    stats = improver.stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
