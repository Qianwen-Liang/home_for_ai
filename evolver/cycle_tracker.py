"""
cycle_tracker — 多轮迭代追踪与抗退化引擎 v1.0

追踪多轮自改进循环的健康指标变化，检测退化模式，触发保护机制。
这是 Gödel Machine 的"免疫系统"——确保连续改进不会导致系统质量下降。

核心能力：
  1. 跨轮次指标追踪（健康、性能、错误率、测试通过率）
  2. 退化检测（单轮退化、连续退化、波动型退化）
  3. 自动保护（暂停改进、触发回滚序列、上报人类）
  4. 改进模式挖掘（哪些改进容易成功/失败）
  5. 知识蒸馏（从多轮改进中提炼可复用模式）
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
TRACKER_DIR = SANDBOX_DIR / "memory" / "cycle_tracker"
TRACKER_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))


class DegradationType(str, Enum):
    """退化类型。"""
    NONE = "none"                      # 无退化
    SINGLE_DROP = "single_drop"        # 单轮健康评分下降 > 5
    CONSECUTIVE_DROP = "consecutive"   # 连续 3 轮下降
    OSCILLATING = "oscillating"        # 波动型退化（改进-回滚-改进-回滚）
    TEST_REGRESSION = "test_regression"  # 测试通过率下降
    ERROR_SPIKE = "error_spike"        # 错误率飙升


class TrackerStatus(str, Enum):
    """追踪器状态。"""
    NORMAL = "normal"                  # 正常
    WARNING = "warning"                # 警告（检测到单轮退化）
    PAUSED = "paused"                  # 暂停（连续退化，需人工介入）
    ROLLING_BACK = "rolling_back"      # 正在回滚
    RECOVERED = "recovered"            # 已恢复


@dataclass
class CycleSnapshot:
    """单轮改进的指标快照，用于跨轮追踪。"""
    cycle_id: str
    timestamp: str
    improvement_name: str = ""
    improvement_type: str = ""

    # 核心指标
    health_score: int = 0
    error_rate: float = 0.0
    avg_response_ms: float = 0.0
    test_pass_rate: float = 100.0
    consecutive_errors: int = 0

    # 改进效果
    effect_score: float = 0.0
    effect_verdict: str = ""           # improved / degraded / unchanged

    # 文件信息
    files_changed: List[str] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    rolled_back: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CycleSnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DegradationAlert:
    """退化告警。"""
    alert_id: str
    timestamp: str
    degradation_type: DegradationType
    severity: str                      # low / medium / high / critical
    description: str
    affected_cycles: List[str] = field(default_factory=list)
    recommended_action: str = ""
    auto_resolved: bool = False
    resolved_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["degradation_type"] = self.degradation_type.value
        return d


@dataclass
class ImprovementPattern:
    """从多轮改进中提炼的可复用模式。"""
    pattern_id: str
    pattern_type: str                  # what_works / what_fails / anti_pattern
    description: str
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.0
    example_cycles: List[str] = field(default_factory=list)
    advice: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CycleTracker:
    """多轮迭代追踪与抗退化引擎。

    用法：
        tracker = CycleTracker()

        # 每轮改进后记录
        tracker.record_cycle(cycle_log)

        # 检查是否退化
        alert = tracker.check_degradation()
        if alert:
            print(f"退化告警: {alert.description}")

        # 分析改进模式
        patterns = tracker.analyze_patterns()

        # 知识蒸馏
        distilled = tracker.distill_knowledge()
    """

    # ── 退化阈值 ────────────────────────────────────────
    HEALTH_DROP_THRESHOLD = 5           # 健康评分下降 >= 5 视为退化
    CONSECUTIVE_DROP_LIMIT = 3          # 连续 N 轮下降触发暂停
    ERROR_SPIKE_THRESHOLD = 10.0        # 错误率上升 >= 10pp 触发告警
    ROLLBACK_RATIO_LIMIT = 0.5          # 回滚率 > 50% 触发警告

    def __init__(self):
        self._snapshots: List[CycleSnapshot] = []
        self._alerts: List[DegradationAlert] = []
        self._patterns: List[ImprovementPattern] = []
        self._status: TrackerStatus = TrackerStatus.NORMAL
        self._alert_counter = 0
        self._load()

    # ═══════════════════════════════════════════════════════
    # 记录
    # ═══════════════════════════════════════════════════════

    def record_cycle(self, cycle_data: Dict[str, Any]) -> CycleSnapshot:
        """记录一轮改进的指标快照。

        Args:
            cycle_data: 来自 SelfImprover.CycleLog 的字典或兼容格式

        Returns:
            创建的快照
        """
        snap = CycleSnapshot(
            cycle_id=cycle_data.get("cycle_id", f"snap-{len(self._snapshots)}"),
            timestamp=cycle_data.get("started_at", datetime.now().isoformat()),
            improvement_name=(
                cycle_data.get("selected_idea", {}).get("title", "")
                if isinstance(cycle_data.get("selected_idea"), dict)
                else ""
            ),
            improvement_type=(
                cycle_data.get("selected_idea", {}).get("improvement_type", "")
                if isinstance(cycle_data.get("selected_idea"), dict)
                else ""
            ),
            health_score=cycle_data.get("health_after", cycle_data.get("health_before", 0)),
            effect_score=cycle_data.get("effect_score", 0),
            effect_verdict=cycle_data.get("effect_verdict", ""),
            files_changed=cycle_data.get("files_changed", []),
            tests_passed=cycle_data.get("tests_passed", 0),
            tests_failed=cycle_data.get("tests_failed", 0),
            rolled_back=cycle_data.get("rolled_back", False),
        )

        self._snapshots.append(snap)

        # 保留最近 100 个快照
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]

        self._save()
        return snap

    # ═══════════════════════════════════════════════════════
    # 退化检测
    # ═══════════════════════════════════════════════════════

    def check_degradation(self) -> Optional[DegradationAlert]:
        """检测是否发生退化，返回告警（如果有）。"""
        if len(self._snapshots) < 2:
            return None

        recent = self._snapshots[-5:]  # 最近 5 轮
        if len(recent) < 2:
            return None

        # 检测 1: 单轮健康评分大幅下降
        alert = self._check_health_drop(recent)
        if alert:
            return alert

        # 检测 2: 连续退化
        alert = self._check_consecutive_drop(recent)
        if alert:
            return alert

        # 检测 3: 回滚率过高
        alert = self._check_high_rollback_rate(recent)
        if alert:
            return alert

        # 检测 4: 效果波动
        alert = self._check_oscillation(recent)
        if alert:
            return alert

        return None

    def _check_health_drop(self, recent: List[CycleSnapshot]) -> Optional[DegradationAlert]:
        """检测单轮健康评分下降。"""
        latest = recent[-1]
        prev = recent[-2]

        if prev.health_score > 0:
            drop = prev.health_score - latest.health_score
            if drop >= self.HEALTH_DROP_THRESHOLD:
                self._alert_counter += 1
                return DegradationAlert(
                    alert_id=f"alert-{self._alert_counter:04d}",
                    timestamp=datetime.now().isoformat(),
                    degradation_type=DegradationType.SINGLE_DROP,
                    severity="medium" if drop < 10 else "high",
                    description=(
                        f"健康评分从 {prev.health_score} 降至 {latest.health_score} "
                        f"（下降 {drop} 点）。改进: {latest.improvement_name}"
                    ),
                    affected_cycles=[latest.cycle_id],
                    recommended_action=(
                        "审查本轮改进的代码变更，使用 safe_deploy.rollback 回滚。"
                    ),
                )

        return None

    def _check_consecutive_drop(self, recent: List[CycleSnapshot]) -> Optional[DegradationAlert]:
        """检测连续退化。"""
        if len(recent) < 3:
            return None

        # 检查最近 3 轮的健康评分趋势
        health_scores = [s.health_score for s in recent[-3:] if s.health_score > 0]
        if len(health_scores) < 3:
            return None

        # 连续下降
        if health_scores[0] > health_scores[1] > health_scores[2]:
            total_drop = health_scores[0] - health_scores[2]
            if total_drop >= self.HEALTH_DROP_THRESHOLD * 2:
                self._status = TrackerStatus.PAUSED
                self._alert_counter += 1
                return DegradationAlert(
                    alert_id=f"alert-{self._alert_counter:04d}",
                    timestamp=datetime.now().isoformat(),
                    degradation_type=DegradationType.CONSECUTIVE_DROP,
                    severity="critical",
                    description=(
                        f"连续 {self.CONSECUTIVE_DROP_LIMIT} 轮健康评分下降！"
                        f"从 {health_scores[0]} → {health_scores[1]} → {health_scores[2]}"
                        f"（累计下降 {total_drop} 点）"
                    ),
                    affected_cycles=[s.cycle_id for s in recent[-3:]],
                    recommended_action=(
                        "🔴 紧急：暂停所有自动改进，人工审查最近的变更。"
                        "建议回滚最近 3 轮改进。"
                    ),
                )

        return None

    def _check_high_rollback_rate(self, recent: List[CycleSnapshot]) -> Optional[DegradationAlert]:
        """检测回滚率过高。"""
        if len(recent) < 4:
            return None

        rolled_back = sum(1 for s in recent if s.rolled_back)
        rollback_rate = rolled_back / len(recent)

        if rollback_rate > self.ROLLBACK_RATIO_LIMIT:
            self._alert_counter += 1
            return DegradationAlert(
                alert_id=f"alert-{self._alert_counter:04d}",
                timestamp=datetime.now().isoformat(),
                degradation_type=DegradationType.OSCILLATING,
                severity="high",
                description=(
                    f"回滚率过高: {rolled_back}/{len(recent)} ({rollback_rate:.0%})，"
                    f"改进方向可能有问题。"
                ),
                affected_cycles=[s.cycle_id for s in recent if s.rolled_back],
                recommended_action=(
                    "重新评估改进策略。可能是改进类型选择不当，建议切换到更保守的模式。"
                ),
            )

        return None

    def _check_oscillation(self, recent: List[CycleSnapshot]) -> Optional[DegradationAlert]:
        """检测改进-退化波动模式。"""
        if len(recent) < 4:
            return None

        verdicts = [s.effect_verdict for s in recent]
        # 检测"improved → degraded → improved → degraded" 模式
        oscillations = sum(
            1 for i in range(1, len(verdicts))
            if verdicts[i] != verdicts[i-1] and verdicts[i] in ("improved", "degraded")
        )

        if oscillations >= 3:
            self._alert_counter += 1
            return DegradationAlert(
                alert_id=f"alert-{self._alert_counter:04d}",
                timestamp=datetime.now().isoformat(),
                degradation_type=DegradationType.OSCILLATING,
                severity="medium",
                description=(
                    f"改进效果波动频繁: 最近 {len(recent)} 轮中 {oscillations} 次方向切换。"
                    f"系统可能在不稳定状态。"
                ),
                affected_cycles=[s.cycle_id for s in recent],
                recommended_action=(
                    "建议暂停并等待系统稳定。检查是否有两个相反的改进在互相抵消。"
                ),
            )

        return None

    # ═══════════════════════════════════════════════════════
    # 模式分析
    # ═══════════════════════════════════════════════════════

    def analyze_patterns(self) -> List[ImprovementPattern]:
        """从历史改进中挖掘可复用模式。

        分析维度：
          1. 哪种改进类型成功率最高？
          2. 哪种模块最容易出问题？
          3. 哪些改进组合效果好？
        """
        if len(self._snapshots) < 3:
            return []

        patterns = []

        # 模式 1: 按改进类型统计成功率
        type_stats: Dict[str, Dict[str, int]] = {}
        for snap in self._snapshots:
            itype = snap.improvement_type or "unknown"
            if itype not in type_stats:
                type_stats[itype] = {"total": 0, "success": 0, "failure": 0}
            type_stats[itype]["total"] += 1
            if snap.effect_verdict == "improved":
                type_stats[itype]["success"] += 1
            elif snap.effect_verdict == "degraded":
                type_stats[itype]["failure"] += 1

        for itype, stats in type_stats.items():
            if stats["total"] >= 2:
                success_rate = stats["success"] / stats["total"]
                if success_rate >= 0.7:
                    patterns.append(ImprovementPattern(
                        pattern_id=f"pat-type-{itype}",
                        pattern_type="what_works",
                        description=f"{itype} 类型改进成功率 {success_rate:.0%} "
                                    f"（{stats['success']}/{stats['total']}）",
                        success_count=stats["success"],
                        failure_count=stats["failure"],
                        confidence=success_rate,
                        advice=f"优先选择 {itype} 类型的改进 — 历史成功率高。",
                    ))
                elif success_rate <= 0.3:
                    patterns.append(ImprovementPattern(
                        pattern_id=f"pat-type-{itype}",
                        pattern_type="what_fails",
                        description=f"{itype} 类型改进成功率仅 {success_rate:.0%} "
                                    f"（{stats['success']}/{stats['total']}），需谨慎。",
                        success_count=stats["success"],
                        failure_count=stats["failure"],
                        confidence=1 - success_rate,
                        advice=f"避免 {itype} 类型改进，或增加保护措施后尝试。",
                    ))

        # 模式 2: 检测改进-回滚循环
        if len(self._snapshots) >= 5:
            rollback_ideas = set()
            for snap in self._snapshots:
                if snap.rolled_back:
                    rollback_ideas.add(snap.improvement_name)

            if len(rollback_ideas) >= 2:
                patterns.append(ImprovementPattern(
                    pattern_id="pat-rollback-loop",
                    pattern_type="anti_pattern",
                    description=f"检测到 {len(rollback_ideas)} 个不同的改进方向导致回滚。"
                                f"可能存在系统性问题。",
                    failure_count=len(rollback_ideas),
                    confidence=0.8,
                    advice="暂停自动改进，人工诊断根因。可能是环境限制而非代码问题。",
                ))

        self._patterns = patterns
        self._save()
        return patterns

    # ═══════════════════════════════════════════════════════
    # 知识蒸馏
    # ═══════════════════════════════════════════════════════

    def distill_knowledge(self) -> Dict[str, Any]:
        """从多轮改进中蒸馏可复用知识。

        Returns:
            蒸馏结果，可直接存入 knowledge 系统
        """
        if len(self._snapshots) < 2:
            return {"status": "insufficient_data", "message": "至少需要 2 轮改进才能蒸馏。"}

        recent = self._snapshots[-10:]
        improved = [s for s in recent if s.effect_verdict == "improved"]
        degraded = [s for s in recent if s.effect_verdict == "degraded"]

        # 1. 成功改进的共同特征
        success_patterns = []
        if improved:
            success_types = set(s.improvement_type for s in improved if s.improvement_type)
            success_modules = set(
                f.split("/")[-1].replace(".py", "")
                for s in improved for f in s.files_changed
            )
            success_patterns.append(
                f"成功改进集中在以下类型: {', '.join(success_types)}"
            )
            if success_modules:
                success_patterns.append(
                    f"稳定模块（改进后不回滚）: {', '.join(list(success_modules)[:5])}"
                )

        # 2. 失败改进的共同特征
        failure_patterns = []
        if degraded:
            fail_types = set(s.improvement_type for s in degraded if s.improvement_type)
            failure_patterns.append(
                f"失败改进集中在以下类型: {', '.join(fail_types)}"
            )

        # 3. 关键指标趋势
        if len(recent) >= 3:
            health_trend = [s.health_score for s in recent[-5:] if s.health_score > 0]
            if health_trend:
                trend_direction = "上升" if health_trend[-1] > health_trend[0] else (
                    "下降" if health_trend[-1] < health_trend[0] else "稳定"
                )

        # 4. 生成知识条目内容
        content = (
            f"# 自改进知识蒸馏\n"
            f"**蒸馏时间**: {datetime.now().isoformat()}\n"
            f"**分析轮次**: {len(recent)} 轮\n\n"
            f"## 成功模式\n"
            + "\n".join(f"- {p}" for p in success_patterns) + "\n\n"
            f"## 失败模式\n"
            + "\n".join(f"- {p}" for p in failure_patterns) + "\n\n"
            f"## 统计数据\n"
            f"- 改进成功: {len(improved)} 次\n"
            f"- 改进失败/退化: {len(degraded)} 次\n"
            f"- 回滚: {sum(1 for s in recent if s.rolled_back)} 次\n"
        )

        return {
            "status": "ready",
            "title": f"自改进知识蒸馏 ({len(recent)} 轮)",
            "content": content,
            "category": "improvement",
            "tags": ["knowledge-distillation", "improvement-pattern", "self-learning"],
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
            "improved_count": len(improved),
            "degraded_count": len(degraded),
        }

    # ═══════════════════════════════════════════════════════
    # 保护机制
    # ═══════════════════════════════════════════════════════

    def should_pause(self) -> Tuple[bool, str]:
        """判断是否应该暂停自动改进。

        Returns:
            (是否暂停, 原因)
        """
        if self._status == TrackerStatus.PAUSED:
            return True, "连续退化已触发暂停保护"

        if len(self._snapshots) >= 5:
            recent = self._snapshots[-5:]
            rollback_count = sum(1 for s in recent if s.rolled_back)
            if rollback_count >= 3:
                self._status = TrackerStatus.PAUSED
                return True, f"最近 5 轮回滚 {rollback_count} 次，触发暂停"

        return False, ""

    def reset_status(self):
        """重置追踪器状态（人工确认后）。"""
        self._status = TrackerStatus.NORMAL

    def status_summary(self) -> str:
        """返回追踪器状态摘要。"""
        lines = [
            f"📊 CycleTracker 状态: {self._status.value}",
            f"已追踪轮次: {len(self._snapshots)}",
            f"告警总数: {len(self._alerts)}",
        ]

        if self._snapshots:
            last = self._snapshots[-1]
            lines.append(f"最近一轮: {last.cycle_id} ({last.effect_verdict})")

        if self._alerts:
            unresolved = [a for a in self._alerts if not a.auto_resolved]
            if unresolved:
                lines.append(f"\n⚠️ 未解决告警: {len(unresolved)} 个")
                for a in unresolved[-3:]:
                    lines.append(f"  [{a.severity}] {a.description[:80]}")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════════════════

    def _save(self):
        data = {
            "snapshots": [s.to_dict() for s in self._snapshots],
            "alerts": [a.to_dict() for a in self._alerts],
            "patterns": [p.to_dict() for p in self._patterns],
            "status": self._status.value,
            "alert_counter": self._alert_counter,
        }
        filepath = TRACKER_DIR / "tracker_data.json"
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        filepath = TRACKER_DIR / "tracker_data.json"
        if not filepath.is_file():
            return
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            self._snapshots = [CycleSnapshot.from_dict(s) for s in data.get("snapshots", [])]
            self._alerts = [
                DegradationAlert(
                    alert_id=a.get("alert_id", ""),
                    timestamp=a.get("timestamp", ""),
                    degradation_type=DegradationType(a.get("degradation_type", "none")),
                    severity=a.get("severity", "low"),
                    description=a.get("description", ""),
                    affected_cycles=a.get("affected_cycles", []),
                    recommended_action=a.get("recommended_action", ""),
                    auto_resolved=a.get("auto_resolved", False),
                    resolved_at=a.get("resolved_at", ""),
                )
                for a in data.get("alerts", [])
            ]
            self._patterns = [
                ImprovementPattern(**p) for p in data.get("patterns", [])
            ]
            self._status = TrackerStatus(data.get("status", "normal"))
            self._alert_counter = data.get("alert_counter", 0)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass


# ── 全局单例 ───────────────────────────────────────────────

_tracker = CycleTracker()


def get_tracker() -> CycleTracker:
    """获取循环追踪器实例。"""
    return _tracker


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "cycle_tracker",
        "description": (
            "多轮迭代追踪与抗退化引擎。追踪自改进循环的健康指标变化，"
            "检测退化模式并触发保护机制。支持状态查询、模式分析和知识蒸馏。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "check", "patterns", "distill", "history", "reset", "help"],
                    "description": (
                        "操作类型：status — 追踪器状态摘要；"
                        "check — 检查退化信号；"
                        "patterns — 分析改进模式；"
                        "distill — 知识蒸馏；"
                        "history — 快照历史；"
                        "reset — 重置追踪器状态（人工确认后）"
                    ),
                    "default": "status",
                },
                "limit": {
                    "type": "integer",
                    "description": "历史快照数量限制",
                    "default": 10,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


def execute_cycle_tracker_tool(arguments: dict) -> str:
    """循环追踪器工具入口。"""
    action = arguments.get("action", "status")

    try:
        if action == "status":
            return _tracker.status_summary()

        elif action == "check":
            alert = _tracker.check_degradation()
            if alert:
                return (
                    f"⚠️ 退化告警: [{alert.severity}] {alert.degradation_type.value}\n"
                    f"{alert.description}\n\n"
                    f"建议: {alert.recommended_action}"
                )
            return "✅ 未检测到退化信号。系统运行正常。"

        elif action == "patterns":
            patterns = _tracker.analyze_patterns()
            if not patterns:
                return "📭 数据不足以分析模式（至少需要 3 轮改进）。"

            lines = [f"📊 改进模式分析 ({len(patterns)} 个):\n"]
            for p in patterns:
                icon = {"what_works": "✅", "what_fails": "❌", "anti_pattern": "⚠️"}.get(
                    p.pattern_type, "•")
                lines.append(
                    f"{icon} [{p.pattern_type}] {p.description}"
                )
                lines.append(f"   置信度: {p.confidence:.0%} | {p.advice}")
                lines.append("")
            return "\n".join(lines)

        elif action == "distill":
            distilled = _tracker.distill_knowledge()
            if distilled.get("status") != "ready":
                return distilled.get("message", "数据不足")

            # 存储到 knowledge
            try:
                from tools.knowledge_store import _store
                _store.store(
                    title=distilled["title"],
                    content=distilled["content"],
                    category="improvement",
                    tags=distilled.get("tags", []),
                )
                stored = True
            except Exception:
                stored = False

            return (
                f"🧪 知识蒸馏完成\n"
                f"分析轮次: {distilled.get('improved_count', 0) + distilled.get('degraded_count', 0)}\n"
                f"成功模式: {len(distilled.get('success_patterns', []))} 个\n"
                f"失败模式: {len(distilled.get('failure_patterns', []))} 个\n"
                f"已存储到知识库: {'✅' if stored else '❌'}\n\n"
                f"{distilled['content'][:500]}"
            )

        elif action == "history":
            limit = int(arguments.get("limit", 10))
            snaps = _tracker._snapshots[-limit:]
            if not snaps:
                return "暂无快照记录。"

            lines = [f"📈 最近 {len(snaps)} 轮快照:\n"]
            for s in snaps:
                icon = {"improved": "+", "degraded": "-", "unchanged": "="}.get(
                    s.effect_verdict, "?")
                lines.append(
                    f"  {icon} [{s.timestamp[:19]}] {s.improvement_name[:40]} "
                    f"(健康:{s.health_score}, 效果:{s.effect_score:+.2f})"
                )
            return "\n".join(lines)

        elif action == "reset":
            _tracker.reset_status()
            return "✅ 追踪器状态已重置。自动改进可以恢复。"

        elif action == "help":
            return (
                "🛡️ cycle_tracker — 抗退化引擎\n\n"
                "操作:\n"
                "  status   — 追踪器状态摘要\n"
                "  check    — 检查退化信号\n"
                "  patterns — 改进模式分析\n"
                "  distill  — 知识蒸馏（存入 knowledge）\n"
                "  history  — 快照历史\n"
                "  reset    — 重置状态（人工确认后）\n\n"
                "退化类型:\n"
                "  single_drop    — 单轮健康下降≥5\n"
                "  consecutive    — 连续3轮下降→暂停\n"
                "  oscillating    — 改进-回滚波动\n"
                "  test_regression — 测试通过率下降\n"
                "  error_spike    — 错误率飙升"
            )

        else:
            return f"未知操作: {action}。可用: status, check, patterns, distill, history, reset, help"

    except Exception as exc:
        return f"循环追踪器错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    tracker = CycleTracker()

    # 模拟几轮改进
    for i in range(3):
        tracker.record_cycle({
            "cycle_id": f"test-cycle-{i}",
            "started_at": datetime.now().isoformat(),
            "health_after": 80 - i * 3,
            "effect_score": 0.05 - i * 0.03,
            "effect_verdict": "improved" if i < 2 else "degraded",
            "improvement_type": "L2",
            "files_changed": ["test.py"],
        })

    alert = tracker.check_degradation()
    if alert:
        print(f"Alert: {alert.description}")

    patterns = tracker.analyze_patterns()
    print(f"Patterns found: {len(patterns)}")

    distilled = tracker.distill_knowledge()
    print(f"Distillation: {distilled['status']}")

    print(tracker.status_summary())
