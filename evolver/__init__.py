"""Evolver — 进化引擎模块包"""

from evolver.health_dashboard import HealthDashboard
from evolver.safe_deploy import SafeDeploy
from evolver.usage_analyzer import UsageAnalyzer
from evolver.tech_radar import TechRadar, RadarBriefing, RadarEntry, RadarCategory, ImpactLevel, run_tech_radar
from evolver.env_awareness import EnvironmentAwareness, UnifiedReport, AwarenessLayer, quick_pulse
from evolver.evolution_strategy import EvolutionStrategy, StrategyMode, get_strategy
from evolver.audit_log import AuditLog, AuditEntry, DecisionOutcome, get_audit_log
from evolver.effect_evaluator import EffectEvaluator, EffectReport, MetricSnapshot, get_evaluator
from evolver.improvement_generator import ImprovementGenerator, ImprovementIdea, ImprovementType, get_generator
from evolver.self_improver import SelfImprover, CycleLog, CycleStatus, CyclePhase, get_improver
from evolver.cycle_tracker import CycleTracker, CycleSnapshot, DegradationAlert, DegradationType, TrackerStatus, ImprovementPattern, get_tracker
from evolver.automated_patcher import AutomatedPatcher, PatchResult, apply_patch
from evolver.self_healing import SelfHealingWatchdog, HealingSession, execute_self_healing_tool

__all__ = [
    # 阶段一
    "HealthDashboard",
    "SafeDeploy",
    "UsageAnalyzer",
    # 阶段二
    "TechRadar", "RadarBriefing", "RadarEntry", "RadarCategory", "ImpactLevel", "run_tech_radar",
    "EnvironmentAwareness", "UnifiedReport", "AwarenessLayer", "quick_pulse",
    # 阶段三
    "EvolutionStrategy", "StrategyMode", "get_strategy",
    "AuditLog", "AuditEntry", "DecisionOutcome", "get_audit_log",
    # 阶段四: Gödel Machine 自改进闭环
    "EffectEvaluator", "EffectReport", "MetricSnapshot", "get_evaluator",
    "ImprovementGenerator", "ImprovementIdea", "ImprovementType", "get_generator",
    "SelfImprover", "CycleLog", "CycleStatus", "CyclePhase", "get_improver",
    "CycleTracker", "CycleSnapshot", "DegradationAlert", "DegradationType", "TrackerStatus", "ImprovementPattern", "get_tracker",
    "AutomatedPatcher", "PatchResult", "apply_patch",
    "SelfHealingWatchdog", "HealingSession",
]
