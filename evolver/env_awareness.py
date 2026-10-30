"""
环境感知统一入口 — EnvironmentAwareness (E-B2)

整合三个子层：
  - 子层 A：系统自感知（HealthDashboard）
  - 子层 B：行为环境感知（UsageAnalyzer）
  - 子层 C：技术生态感知（TechRadar）

设计参考：
  - Agentic AI 综述（arXiv:2510.25445）提出的"感知-推理-行动"闭环
  - 多层感知架构：任务环境 → 系统环境 → 外部环境
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 数据目录 ─────────────────────────────────────────────
AWARENESS_DIR = Path(__file__).resolve().parent.parent / "memory" / "reports"
AWARENESS_DIR.mkdir(parents=True, exist_ok=True)


class AwarenessLayer(str, Enum):
    """环境感知三层"""
    SELF       = "self"         # 子层 A：系统自感知
    BEHAVIORAL = "behavioral"   # 子层 B：行为环境
    ECOLOGICAL = "ecological"   # 子层 C：技术生态


class Severity(str, Enum):
    """异常严重程度"""
    INFO     = "info"
    WARNING  = "warning"
    ERROR    = "error"
    CRITICAL = "critical"


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class LayerReport:
    """单层感知报告"""
    layer: AwarenessLayer
    status: str                         # "healthy" / "degraded" / "unavailable"
    score: float                        # 0-100
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    anomalies: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Anomaly:
    """跨层异常"""
    id: str
    severity: Severity
    description: str
    related_layers: List[AwarenessLayer]
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedReport:
    """统一环境报告"""
    report_id: str
    timestamp: str
    layers: Dict[str, LayerReport]
    overall_score: float               # 0-100 综合评分
    overall_status: str                 # "healthy" / "degraded" / "unstable" / "critical"
    anomalies: List[Anomaly]
    evolution_advice: List[str]         # 给 Evolver 的建议
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "layers": {k: asdict(v) for k, v in self.layers.items()},
            "overall_score": self.overall_score,
            "overall_status": self.overall_status,
            "anomalies": [asdict(a) for a in self.anomalies],
            "evolution_advice": self.evolution_advice,
            "raw_data": self.raw_data,
        }


# ── 主类 ──────────────────────────────────────────────────

class EnvironmentAwareness:
    """
    环境感知统一调度器（单例模式）。

    用法：
        ea = EnvironmentAwareness()
        report = ea.pulse()                # 执行全层扫描
        anomalies = ea.detect_anomalies(report)
        advice = ea.advise(report)
    """

    _instance: Optional["EnvironmentAwareness"] = None

    def __new__(cls) -> "EnvironmentAwareness":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._last_report: Optional[UnifiedReport] = None
        self._pulse_count: int = 0

        # 扫描周期配置（单位：小时）
        self.schedule_config = {
            AwarenessLayer.SELF: 1,         # 每小时自检
            AwarenessLayer.BEHAVIORAL: 24,  # 每天分析使用模式
            AwarenessLayer.ECOLOGICAL: 168, # 每周扫描技术生态
        }

    # ── 全层扫描 ────────────────────────────────────────

    def pulse(self) -> UnifiedReport:
        """
        执行一轮全层扫描，返回统一环境报告。

        三层依次执行：
        1. SELF       → HealthDashboard.aggregate()
        2. BEHAVIORAL → UsageAnalyzer.report()
        3. ECOLOGICAL → TechRadar.latest()
        """
        self._pulse_count += 1
        layers: Dict[str, LayerReport] = {}

        # ── 子层 A：系统自感知 ──
        try:
            from evolver.health_dashboard import HealthDashboard
            hd = HealthDashboard()
            hd_result = hd.aggregate()
            layers["self"] = LayerReport(
                layer=AwarenessLayer.SELF,
                status=hd_result.get("status", "unknown"),
                score=hd_result.get("score", 0),
                summary=f"健康评分 {hd_result.get('score', '?')}/100，状态 {hd_result.get('status', '?')}",
                details=hd_result,
            )
        except Exception as e:
            layers["self"] = LayerReport(
                layer=AwarenessLayer.SELF,
                status="unavailable",
                score=0,
                summary=f"自感知层不可用：{e}",
            )

        # ── 子层 B：行为环境 ──
        try:
            from evolver.usage_analyzer import UsageAnalyzer
            ua = UsageAnalyzer()
            ua.load_data(days=7)
            usage_summary = ua.summary()
            score = 70  # 默认分
            if usage_summary.get("hot_spots"):
                score = min(100, 70 + len(usage_summary.get("hot_spots", [])) * 5)
            layers["behavioral"] = LayerReport(
                layer=AwarenessLayer.BEHAVIORAL,
                status="healthy" if score >= 60 else "degraded",
                score=score,
                summary=f"热点工具 {len(usage_summary.get('hot_spots', []))} 个，冷门工具 {len(usage_summary.get('cold_spots', []))} 个",
                details=usage_summary,
            )
        except Exception as e:
            layers["behavioral"] = LayerReport(
                layer=AwarenessLayer.BEHAVIORAL,
                status="unavailable",
                score=0,
                summary=f"行为感知层不可用：{e}",
            )

        # ── 子层 C：技术生态 ──
        try:
            from evolver.tech_radar import TechRadar
            radar = TechRadar()
            latest_briefing = radar.latest()
            if latest_briefing:
                score = max(0, 80 - latest_briefing.critical_count * 20 - latest_briefing.high_count * 10)
                status = "healthy" if latest_briefing.critical_count == 0 else "degraded"
                summary = latest_briefing.executive_summary
                details = {
                    "briefing_id": latest_briefing.briefing_id,
                    "scan_time": latest_briefing.scan_time,
                    "critical": latest_briefing.critical_count,
                    "high": latest_briefing.high_count,
                    "medium": latest_briefing.medium_count,
                    "low": latest_briefing.low_count,
                }
            else:
                score = 50
                status = "degraded"
                summary = "暂无技术雷达简报，建议执行首次扫描。"
                details = {}
            layers["ecological"] = LayerReport(
                layer=AwarenessLayer.ECOLOGICAL,
                status=status,
                score=score,
                summary=summary,
                details=details,
            )
        except Exception as e:
            layers["ecological"] = LayerReport(
                layer=AwarenessLayer.ECOLOGICAL,
                status="unavailable",
                score=0,
                summary=f"生态感知层不可用：{e}",
            )

        # ── 综合评分 ──
        scores = [lr.score for lr in layers.values() if lr.status != "unavailable"]
        overall_score = sum(scores) / len(scores) if scores else 0

        if overall_score >= 80:
            overall_status = "healthy"
        elif overall_score >= 60:
            overall_status = "degraded"
        elif overall_score >= 40:
            overall_status = "unstable"
        else:
            overall_status = "critical"

        report = UnifiedReport(
            report_id=f"env-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            layers=layers,
            overall_score=round(overall_score, 1),
            overall_status=overall_status,
            anomalies=self.detect_anomalies(layers),
            evolution_advice=self.advise_from_layers(layers, overall_status),
        )

        self._last_report = report
        self._save_report(report)
        return report

    # ── 跨层异常检测 ────────────────────────────────────

    def detect_anomalies(self, layers: Optional[Dict[str, LayerReport]] = None) -> List[Anomaly]:
        """
        跨层异常关联检测。

        检测模式：
        1. 安全漏洞 + 受影响内部模块 → 关联告警
        2. 高频错误工具 + 系统健康下降 → 关联告警
        3. 三层同时降级 → 系统级告警
        """
        if layers is None:
            if self._last_report:
                layers = self._last_report.layers
            else:
                return []

        anomalies: List[Anomaly] = []

        # 模式 1：安全漏洞 + 系统自检异常
        eco = layers.get("ecological")
        slf = layers.get("self")
        if (
            eco and slf
            and eco.status == "degraded"
            and slf.status in ("degraded", "unstable")
            and eco.details.get("critical", 0) > 0
        ):
            anomalies.append(Anomaly(
                id=f"anom-{len(anomalies)+1:03d}",
                severity=Severity.CRITICAL,
                description="技术雷达发现安全警报，且系统健康度下降 → 可能存在受影响组件",
                related_layers=[AwarenessLayer.ECOLOGICAL, AwarenessLayer.SELF],
                evidence={"eco_critical": eco.details.get("critical"), "self_status": slf.status},
            ))

        # 模式 2：行为层发现瓶颈 + 系统健康下降
        beh = layers.get("behavioral")
        if (
            beh and slf
            and beh.status == "degraded"
            and slf.status in ("degraded", "unstable")
            and beh.details.get("bottlenecks")
        ):
            anomalies.append(Anomaly(
                id=f"anom-{len(anomalies)+1:03d}",
                severity=Severity.ERROR,
                description="工具性能瓶颈与系统健康下降同时发生 → 建议优化热点工具",
                related_layers=[AwarenessLayer.BEHAVIORAL, AwarenessLayer.SELF],
                evidence={"bottlenecks": beh.details.get("bottlenecks"), "self_score": slf.score},
            ))

        # 模式 3：三层同时降级
        degraded_count = sum(1 for lr in (layers or {}).values() if lr.status in ("degraded", "unstable", "unavailable"))
        if degraded_count >= 3:
            anomalies.append(Anomaly(
                id=f"anom-{len(anomalies)+1:03d}",
                severity=Severity.CRITICAL,
                description="三层环境感知同时处于降级状态 → 系统整体运行状况需立即关注",
                related_layers=list(AwarenessLayer),
                evidence={"degraded_layers": degraded_count},
            ))

        return anomalies

    # ── 进化建议 ─────────────────────────────────────────

    def advise_from_layers(self, layers: Dict[str, LayerReport], overall_status: str) -> List[str]:
        """基于环境状态生成进化建议。"""
        advice: List[str] = []

        slf = layers.get("self")
        beh = layers.get("behavioral")
        eco = layers.get("ecological")

        # 自感知建议
        if slf and slf.score < 60:
            advice.append("🔴 系统健康评分过低，建议暂缓功能开发，优先排查根因。")
        elif slf and slf.score < 80:
            advice.append("🟡 系统健康评分偏低，建议关注近期错误模式。")

        # 行为感知建议
        if beh and beh.details.get("cold_spots"):
            cold_count = len(beh.details.get("cold_spots", []))
            if cold_count >= 3:
                advice.append(f"📉 发现 {cold_count} 个冷门工具，建议评估是否可合并或废弃。")
        if beh and beh.details.get("bottlenecks"):
            advice.append("⚡ 检测到工具性能瓶颈，建议为核心工具添加缓存或异步支持。")

        # 生态感知建议
        if eco and eco.details.get("critical", 0) > 0:
            advice.append(f"🚨 技术雷达有 {eco.details['critical']} 条 CRITICAL 警报，建议立即启动安全响应。")
        if eco and eco.details.get("high", 0) > 0:
            advice.append(f"⚠️ 技术雷达有 {eco.details['high']} 条 HIGH 级别动态需要跟进。")

        # 综合建议
        if overall_status == "critical":
            advice.append("🆘 环境综合状态为 CRITICAL，建议启动自救流程。")
        elif overall_status == "unstable":
            advice.append("⚠️ 环境综合状态不稳定，建议减少变更频率，加强监控。")
        elif overall_status == "healthy":
            advice.append("✅ 环境健康，适合推进计划中的进化任务。")

        return advice

    # ── 公开 advise 方法 ─────────────────────────────────

    def advise(self, report: Optional[UnifiedReport] = None) -> List[str]:
        """基于环境报告给 Evolver 提供进化建议。"""
        r = report or self._last_report
        if not r:
            return ["⚠️ 暂无环境报告，建议先执行 pulse()。"]
        return r.evolution_advice

    # ── 调度管理 ─────────────────────────────────────────

    def should_scan(self, layer: AwarenessLayer) -> bool:
        """检查某层是否到了扫描时间。"""
        if not self._last_report:
            return True
        layer_report = self._last_report.layers.get(layer.value)
        if not layer_report:
            return True
        try:
            last_time = datetime.fromisoformat(layer_report.timestamp)
            interval = timedelta(hours=self.schedule_config.get(layer, 24))
            return datetime.now() - last_time >= interval
        except (ValueError, TypeError):
            return True

    def schedule(self) -> Dict[str, str]:
        """返回各层的扫描建议（"due" / "ok"）。"""
        result = {}
        for layer in AwarenessLayer:
            result[layer.value] = "due" if self.should_scan(layer) else "ok"
        return result

    # ── 报告管理 ─────────────────────────────────────────

    @property
    def last_report(self) -> Optional[UnifiedReport]:
        return self._last_report

    def aggregate_report(self) -> Optional[UnifiedReport]:
        """获取最近的统一报告（同 pulse() 但不强制重新扫描）。"""
        if self._last_report:
            return self._last_report
        return self.pulse()

    # ── 持久化 ──────────────────────────────────────────

    REPORT_FILE = AWARENESS_DIR / "env_awareness_latest.json"

    def _save_report(self, report: UnifiedReport):
        try:
            self.REPORT_FILE.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 静默失败，不影响主流程


# ── 便捷函数 ──────────────────────────────────────────────

def quick_pulse() -> UnifiedReport:
    """便捷入口：执行全层扫描并返回报告。"""
    return EnvironmentAwareness().pulse()


# ── 全局单例 ───────────────────────────────────────────────

_awareness = EnvironmentAwareness()


# ── 工具函数 ──────────────────────────────────────────────

def execute_env_awareness_tool(arguments: dict) -> str:
    """环境感知工具入口。"""
    action = arguments.get("action", "status")

    try:
        if action == "pulse":
            report = _awareness.pulse()
            lines = [
                f"🌍 环境全层扫描完成",
                f"综合评分: {report.overall_score}/100 ({report.overall_status})",
                f"",
            ]
            for layer_name, lr in report.layers.items():
                icon = {"healthy": "✅", "degraded": "🟡", "unavailable": "❌"}.get(lr.status, "•")
                lines.append(f"  {icon} {layer_name}: {lr.summary}")
            if report.anomalies:
                lines.append(f"\n⚠️ 检测到 {len(report.anomalies)} 个跨层异常:")
                for a in report.anomalies[:5]:
                    lines.append(f"  [{a.severity.value}] {a.description}")
            if report.evolution_advice:
                lines.append(f"\n💡 进化建议:")
                for adv in report.evolution_advice[:5]:
                    lines.append(f"  • {adv}")
            return "\n".join(lines)

        elif action == "status":
            sched = _awareness.schedule()
            report = _awareness.last_report
            lines = ["🌍 环境感知状态"]
            if report:
                lines.append(f"最近扫描: {report.timestamp[:19]}")
                lines.append(f"综合评分: {report.overall_score}/100 ({report.overall_status})")
            lines.append(f"\n扫描周期:")
            for layer, status in sched.items():
                icon = "⏰" if status == "due" else "✅"
                lines.append(f"  {icon} {layer}: {status}")
            return "\n".join(lines)

        elif action == "advise":
            advice = _awareness.advise()
            if not advice:
                return "✅ 暂无进化建议。环境健康，可继续推进计划。"
            return "💡 环境进化建议:\n" + "\n".join(f"  • {a}" for a in advice)

        elif action == "schedule":
            sched = _awareness.schedule()
            return "📅 各层扫描计划:\n" + "\n".join(
                f"  {'⏰' if s == 'due' else '✅'} {layer}: {s}"
                for layer, s in sched.items()
            )

        else:
            return f"未知操作: {action}。可用: pulse, status, advise, schedule"

    except Exception as exc:
        return f"环境感知错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "env_awareness",
        "description": (
            "环境感知统一入口。整合系统自感知、行为环境、技术生态三层数据，"
            "执行全层扫描、跨层异常关联检测、生成进化建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pulse", "status", "advise", "schedule"],
                    "description": (
                        "操作类型：pulse — 全层扫描并产出报告；"
                        "status — 查看当前环境状态+扫描计划；"
                        "advise — 仅生成进化建议；"
                        "schedule — 仅查看扫描计划"
                    ),
                    "default": "status",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}
