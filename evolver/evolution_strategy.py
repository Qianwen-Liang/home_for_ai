"""
进化策略引擎 — EvolutionStrategy (E-C2)

元治理维度。实现可切换的进化策略，基于系统健康状态自动推荐或切换策略模式。

三种策略模式（借鉴软件发布策略 + 强化学习的探索-利用权衡）：

  模式          特征                          适用场景
  ───────────  ─────────────────────────────  ──────────────────────
  AGGRESSIVE   快速迭代，低验证门槛，自动执行   早期探索、实验性功能
  CONSERVATIVE 多重验证，人工审批，逐步推进     核心模块修改、生产环境
  MAINTENANCE  仅修复 Bug，不做功能增强         稳定期、冻结期
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 数据目录 ─────────────────────────────────────────────
STRATEGY_DIR = Path(__file__).resolve().parent.parent / "memory"
STRATEGY_FILE = STRATEGY_DIR / "evolution_strategy.json"


class StrategyMode(str, Enum):
    """进化策略模式"""
    AGGRESSIVE   = "aggressive"    # 激进：快速迭代，自动执行
    CONSERVATIVE = "conservative"  # 保守：多重验证，人工审批
    MAINTENANCE  = "maintenance"   # 维护：仅修 Bug，不做增强


# ── Guardrails 定义 ───────────────────────────────────────

# 各模式下的行为约束
GUARDRAILS: Dict[StrategyMode, Dict[str, Any]] = {
    StrategyMode.AGGRESSIVE: {
        "description": "激进模式 — 快速迭代，低验证门槛",
        "max_files_per_change": 5,
        "auto_deploy": True,
        "require_approval": False,
        "min_test_count": 1,
        "rollback_on_failure": True,
        "allow_architecture_change": True,
        "allow_new_dependency": True,
        "allow_experimental_features": True,
        "max_simultaneous_tasks": 5,
    },
    StrategyMode.CONSERVATIVE: {
        "description": "保守模式 — 多重验证，人工审批",
        "max_files_per_change": 2,
        "auto_deploy": False,
        "require_approval": True,
        "min_test_count": 3,
        "rollback_on_failure": True,
        "allow_architecture_change": False,
        "allow_new_dependency": False,
        "allow_experimental_features": False,
        "max_simultaneous_tasks": 2,
    },
    StrategyMode.MAINTENANCE: {
        "description": "维护模式 — 仅修复 Bug，不做功能增强",
        "max_files_per_change": 1,
        "auto_deploy": False,
        "require_approval": True,
        "min_test_count": 2,
        "rollback_on_failure": True,
        "allow_architecture_change": False,
        "allow_new_dependency": False,
        "allow_experimental_features": False,
        "max_simultaneous_tasks": 1,
    },
}


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class StrategySwitch:
    """策略切换记录"""
    from_mode: StrategyMode
    to_mode: StrategyMode
    reason: str
    trigger: str                         # "auto" / "manual"
    health_score: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from_mode"] = self.from_mode.value
        d["to_mode"] = self.to_mode.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StrategySwitch":
        d = dict(d)
        d["from_mode"] = StrategyMode(d.pop("from_mode"))
        d["to_mode"] = StrategyMode(d.pop("to_mode"))
        return cls(**d)


# ── 主类 ──────────────────────────────────────────────────

class EvolutionStrategy:
    """
    进化策略引擎。

    用法：
        es = EvolutionStrategy()

        # 自动推荐
        mode = es.recommend(health_score=45)

        # 切换模式
        es.switch(StrategyMode.CONSERVATIVE, reason="核心模块重构")

        # 查询约束
        guard = es.guardrails()
        print(guard["max_files_per_change"])  # → 2

        # 查看历史
        for switch in es.history():
            print(f"{switch.from_mode} → {switch.to_mode}")
    """

    def __init__(self):
        self._current: StrategyMode = StrategyMode.AGGRESSIVE
        self._switch_history: List[StrategySwitch] = []
        self._load()

    # ── 当前模式 ────────────────────────────────────────

    @property
    def current(self) -> StrategyMode:
        """当前策略模式。"""
        return self._current

    @property
    def mode_name(self) -> str:
        """当前模式的中文描述。"""
        return {
            StrategyMode.AGGRESSIVE: "激进",
            StrategyMode.CONSERVATIVE: "保守",
            StrategyMode.MAINTENANCE: "维护",
        }.get(self._current, "未知")

    # ── 推荐 ────────────────────────────────────────────

    def recommend(self, health_score: float) -> StrategyMode:
        """
        基于健康评分推荐策略模式。

        规则：
          health_score >= 80  → AGGRESSIVE（系统稳定，可大胆迭代）
          60 <= score < 80    → CONSERVATIVE（适度谨慎）
          score < 60          → MAINTENANCE（仅修复问题）
        """
        if health_score >= 80:
            return StrategyMode.AGGRESSIVE
        elif health_score >= 60:
            return StrategyMode.CONSERVATIVE
        else:
            return StrategyMode.MAINTENANCE

    # ── 切换 ────────────────────────────────────────────

    def switch(
        self,
        mode: StrategyMode,
        reason: str = "",
        trigger: str = "manual",
        health_score: Optional[float] = None,
    ) -> StrategySwitch:
        """
        切换进化策略模式。

        Args:
            mode: 目标模式
            reason: 切换原因
            trigger: 触发方式（"auto" 或 "manual"）
            health_score: 触发时的健康评分（自动切换时提供）

        Returns:
            切换记录
        """
        if mode == self._current:
            return StrategySwitch(
                from_mode=self._current,
                to_mode=mode,
                reason="模式未改变",
                trigger=trigger,
            )

        switch_record = StrategySwitch(
            from_mode=self._current,
            to_mode=mode,
            reason=reason or f"自动推荐：健康评分 {health_score}" if health_score else "手动切换",
            trigger=trigger,
            health_score=health_score,
        )
        self._switch_history.append(switch_record)
        self._current = mode
        self._save()

        return switch_record

    def auto_switch(self, health_score: float) -> Optional[StrategySwitch]:
        """
        自动切换：基于健康评分推荐并执行切换。

        Args:
            health_score: 当前系统健康评分

        Returns:
            切换记录（若未切换则返回 None）
        """
        recommended = self.recommend(health_score)
        if recommended != self._current:
            return self.switch(
                mode=recommended,
                reason=f"自动切换：健康评分 {health_score}，推荐 {recommended.value}",
                trigger="auto",
                health_score=health_score,
            )
        return None

    # ── Guardrails ───────────────────────────────────────

    def guardrails(self, mode: Optional[StrategyMode] = None) -> Dict[str, Any]:
        """
        获取当前（或指定）模式下的行为约束规则。

        Returns:
            {
                "max_files_per_change": int,
                "auto_deploy": bool,
                "require_approval": bool,
                "min_test_count": int,
                ...
            }
        """
        m = mode or self._current
        return dict(GUARDRAILS.get(m, GUARDRAILS[StrategyMode.CONSERVATIVE]))

    def check_action(self, action: str, **kwargs) -> tuple[bool, str]:
        """
        检查某操作在当前模式下是否允许。

        Args:
            action: 操作类型（"modify_files", "new_dependency", "architecture_change", ...）
            **kwargs: 操作参数

        Returns:
            (允许?, 原因说明)
        """
        g = self.guardrails()

        if action == "modify_files":
            count = kwargs.get("count", 1)
            if count > g["max_files_per_change"]:
                return False, f"当前为 {self.mode_name} 模式，单次最多修改 {g['max_files_per_change']} 个文件（本次 {count} 个）"
            if kwargs.get("architecture_change") and not g["allow_architecture_change"]:
                return False, f"当前为 {self.mode_name} 模式，不允许架构变更"
            if kwargs.get("experimental") and not g["allow_experimental_features"]:
                return False, f"当前为 {self.mode_name} 模式，不允许实验性功能"

        elif action == "new_dependency":
            if not g["allow_new_dependency"]:
                return False, f"当前为 {self.mode_name} 模式，不允许新增依赖"

        elif action == "architecture_change":
            if not g["allow_architecture_change"]:
                return False, f"当前为 {self.mode_name} 模式，不允许架构变更"

        elif action == "deploy":
            if not g["auto_deploy"]:
                return False, f"当前为 {self.mode_name} 模式，不允许自动部署"

        return True, "允许"

    # ── 历史 ────────────────────────────────────────────

    def history(self, limit: int = 20) -> List[StrategySwitch]:
        """返回模式切换历史（按时间倒序）。"""
        return list(reversed(self._switch_history[-limit:]))

    def stats(self) -> Dict[str, Any]:
        """策略统计信息。"""
        mode_counts = {m.value: 0 for m in StrategyMode}
        for sw in self._switch_history:
            mode_counts[sw.to_mode.value] += 1

        return {
            "current_mode": self._current.value,
            "total_switches": len(self._switch_history),
            "auto_switches": sum(1 for s in self._switch_history if s.trigger == "auto"),
            "manual_switches": sum(1 for s in self._switch_history if s.trigger == "manual"),
            "mode_distribution": mode_counts,
            "latest_switch": self._switch_history[-1].to_dict() if self._switch_history else None,
        }

    # ── 持久化 ──────────────────────────────────────────

    def _save(self):
        data = {
            "current_mode": self._current.value,
            "switch_history": [s.to_dict() for s in self._switch_history],
        }
        STRATEGY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        if not STRATEGY_FILE.exists():
            return
        try:
            data = json.loads(STRATEGY_FILE.read_text(encoding="utf-8"))
            self._current = StrategyMode(data.get("current_mode", "aggressive"))
            self._switch_history = [StrategySwitch.from_dict(s) for s in data.get("switch_history", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass


# ── 全局单例 ───────────────────────────────────────────────

_strategy = EvolutionStrategy()


# ── 工具函数 ──────────────────────────────────────────────

def execute_evolution_strategy_tool(arguments: dict) -> str:
    """进化策略引擎工具入口。"""
    action = arguments.get("action", "current")

    try:
        if action == "current":
            mode = _strategy.current.value
            name = _strategy.mode_name
            guard = _strategy.guardrails()
            lines = [
                f"🎯 当前进化策略: {name} ({mode})",
                f"",
                f"行为约束:",
                f"  • 单次最大文件数: {guard['max_files_per_change']}",
                f"  • 自动部署: {'✅' if guard['auto_deploy'] else '❌'}",
                f"  • 需人工审批: {'✅' if guard['require_approval'] else '❌'}",
                f"  • 最小测试数: {guard['min_test_count']}",
                f"  • 允许架构变更: {'✅' if guard['allow_architecture_change'] else '❌'}",
                f"  • 允许新增依赖: {'✅' if guard['allow_new_dependency'] else '❌'}",
                f"  • 允许实验功能: {'✅' if guard['allow_experimental_features'] else '❌'}",
                f"  • 最大并行任务: {guard['max_simultaneous_tasks']}",
            ]
            return "\n".join(lines)

        elif action == "recommend":
            health_score = float(arguments.get("health_score", 50))
            recommended = _strategy.recommend(health_score)
            return (
                f"💡 基于健康评分 {health_score}/100，"
                f"推荐策略: {recommended.value} ({_strategy.mode_name})"
            )

        elif action == "switch":
            mode_str = arguments.get("mode", "")
            reason = arguments.get("reason", "")
            trigger = arguments.get("trigger", "manual")
            health_score = arguments.get("health_score")

            try:
                mode = StrategyMode(mode_str)
            except ValueError:
                valid = ", ".join(m.value for m in StrategyMode)
                return f"❌ 无效模式: {mode_str}。可用: {valid}"

            health = float(health_score) if health_score is not None else None
            record = _strategy.switch(mode, reason=reason, trigger=trigger, health_score=health)
            return (
                f"🔄 策略已切换: {record.from_mode.value} → {record.to_mode.value}\n"
                f"原因: {record.reason}"
            )

        elif action == "auto_switch":
            health_score = float(arguments.get("health_score", 50))
            result = _strategy.auto_switch(health_score)
            if result:
                return (
                    f"🔄 自动切换: {result.from_mode.value} → {result.to_mode.value}\n"
                    f"原因: {result.reason}"
                )
            return f"✅ 当前模式 {_strategy.current.value} 无需切换（健康评分 {health_score}）"

        elif action == "guardrails":
            mode_str = arguments.get("mode", "")
            if mode_str:
                try:
                    mode = StrategyMode(mode_str)
                except ValueError:
                    mode = None
            else:
                mode = None
            guard = _strategy.guardrails(mode)
            import json as _json
            return _json.dumps(guard, ensure_ascii=False, indent=2)

        elif action == "check_action":
            act = arguments.get("check_action", "")
            kwargs = {k: v for k, v in arguments.items()
                      if k not in ("action", "check_action")}
            allowed, reason = _strategy.check_action(act, **kwargs)
            icon = "✅" if allowed else "❌"
            return f"{icon} {reason}"

        elif action == "history":
            limit = int(arguments.get("limit", 20))
            switches = _strategy.history(limit)
            if not switches:
                return "暂无策略切换历史。"
            lines = [f"📜 最近 {len(switches)} 次策略切换:"]
            for sw in switches:
                lines.append(
                    f"  • {sw.timestamp[:19]} | {sw.from_mode.value} → {sw.to_mode.value} "
                    f"({sw.trigger}) — {sw.reason[:60]}"
                )
            return "\n".join(lines)

        elif action == "stats":
            stats = _strategy.stats()
            import json as _json
            return _json.dumps(stats, ensure_ascii=False, indent=2)

        else:
            return (
                f"未知操作: {action}。"
                f"可用: current, recommend, switch, auto_switch, guardrails, check_action, history, stats"
            )

    except Exception as exc:
        return f"进化策略错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "evolution_strategy",
        "description": (
            "进化策略引擎。管理系统进化策略模式（激进/保守/维护），"
            "基于健康评分自动推荐或切换策略，提供各模式下的行为约束规则。"
            "Evolver 修改代码前应查询 guardrails 确认操作在当前模式下是否允许。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "current", "recommend", "switch",
                        "auto_switch", "guardrails", "check_action",
                        "history", "stats",
                    ],
                    "description": (
                        "操作类型：current — 查看当前策略及约束；"
                        "recommend — 基于健康评分推荐策略；"
                        "switch — 手动切换策略；"
                        "auto_switch — 自动切换（评分驱动）；"
                        "guardrails — 查看行为约束规则；"
                        "check_action — 检查某操作是否允许；"
                        "history — 切换历史；"
                        "stats — 策略统计"
                    ),
                    "default": "current",
                },
                "mode": {
                    "type": "string",
                    "enum": ["aggressive", "conservative", "maintenance"],
                    "description": "策略模式（用于 switch 和 guardrails）",
                    "default": "",
                },
                "health_score": {
                    "type": "number",
                    "description": "系统健康评分 0-100（用于 recommend / auto_switch）",
                },
                "reason": {
                    "type": "string",
                    "description": "切换原因说明（用于 switch）",
                    "default": "",
                },
                "trigger": {
                    "type": "string",
                    "enum": ["auto", "manual"],
                    "description": "触发方式",
                    "default": "manual",
                },
                "check_action": {
                    "type": "string",
                    "description": "要检查的操作类型: modify_files / new_dependency / architecture_change / deploy",
                    "default": "",
                },
                "count": {
                    "type": "integer",
                    "description": "修改文件数量（用于 check_action=modify_files）",
                },
                "architecture_change": {
                    "type": "boolean",
                    "description": "是否涉及架构变更",
                },
                "experimental": {
                    "type": "boolean",
                    "description": "是否为实验性功能",
                },
                "limit": {
                    "type": "integer",
                    "description": "历史记录数量限制",
                    "default": 20,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


# ── 便捷函数 ──────────────────────────────────────────────

def get_strategy() -> EvolutionStrategy:
    """获取进化策略引擎实例。"""
    return _strategy
