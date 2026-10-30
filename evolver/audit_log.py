"""
进化审计日志 — AuditLog (E-C3)

元治理维度。记录每次进化决策的完整上下文，形成可审计的进化历史。

设计原则：
  - 不可变性：已记录的条目不可修改（追加写入）
  - 完整性：记录决策时的完整上下文（who / what / why / when / effect）
  - 可追溯：支持按时间、标签、影响范围查询
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 数据目录 ─────────────────────────────────────────────
AUDIT_DIR = Path(__file__).resolve().parent.parent / "memory" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_FILE = AUDIT_DIR / "audit_log.json"


class DecisionOutcome(str, Enum):
    """决策结果"""
    SUCCESS       = "success"
    PARTIAL       = "partial"        # 部分成功
    FAILED        = "failed"
    ROLLED_BACK   = "rolled_back"
    PENDING       = "pending"


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class AuditEntry:
    """单条审计记录"""
    entry_id: str
    timestamp: str
    decision: str                        # 决策描述（做了什么）
    rationale: str                       # 决策理由（为什么做）
    strategy_mode: str                   # 当时的策略模式
    files_changed: List[str] = field(default_factory=list)
    expected_effect: str = ""            # 预期效果
    actual_effect: str = ""              # 实际效果（事后填写）
    outcome: DecisionOutcome = DecisionOutcome.PENDING
    rollback_hash: str = ""              # 回滚到的 git hash（若回滚）
    tags: List[str] = field(default_factory=list)
    related_tasks: List[str] = field(default_factory=list)
    health_before: Optional[float] = None  # 变更前健康评分
    health_after: Optional[float] = None   # 变更后健康评分
    effect_score: Optional[float] = None   # 量化效果评分 -1.0~+1.0（来自 EffectEvaluator）
    effect_verdict: str = ""               # improved / degraded / unchanged
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if isinstance(self.outcome, DecisionOutcome):
            d["outcome"] = self.outcome.value
        else:
            d["outcome"] = str(self.outcome)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AuditEntry":
        d = dict(d)
        d["outcome"] = DecisionOutcome(d.pop("outcome", "pending"))
        return cls(**d)


# ── 主类 ──────────────────────────────────────────────────

class AuditLog:
    """
    进化审计日志。

    用法：
        audit = AuditLog()

        # 记录决策
        entry = audit.log(
            decision="新增 health_dashboard.py",
            rationale="统一系统自监控，提升可观测性",
            strategy_mode="aggressive",
            files_changed=["evolver/health_dashboard.py"],
            expected_effect="系统健康评分可视化",
        )

        # 事后更新结果
        audit.update_outcome(entry.entry_id, DecisionOutcome.SUCCESS, actual_effect="...")

        # 查询
        recent = audit.query(days=30, tags=["environment-awareness"])
        
        # 统计
        stats = audit.stats()
    """

    MAX_ENTRIES = 1000

    def __init__(self):
        self._entries: Dict[str, AuditEntry] = {}
        self._load()

    # ── 记录 ────────────────────────────────────────────

    def log(
        self,
        decision: str,
        rationale: str,
        strategy_mode: str,
        files_changed: Optional[List[str]] = None,
        expected_effect: str = "",
        tags: Optional[List[str]] = None,
        related_tasks: Optional[List[str]] = None,
        health_before: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """
        记录一次进化决策。

        Returns:
            创建的审计条目
        """
        entry = AuditEntry(
            entry_id=f"audit-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now().isoformat(),
            decision=decision,
            rationale=rationale,
            strategy_mode=strategy_mode,
            files_changed=files_changed or [],
            expected_effect=expected_effect,
            tags=tags or [],
            related_tasks=related_tasks or [],
            health_before=health_before,
            metadata=metadata or {},
        )

        self._entries[entry.entry_id] = entry
        self._enforce_limit()
        self._save()
        return entry

    # ── 更新结果 ────────────────────────────────────────

    def update_outcome(
        self,
        entry_id: str,
        outcome: DecisionOutcome,
        actual_effect: str = "",
        rollback_hash: str = "",
        health_after: Optional[float] = None,
        effect_score: Optional[float] = None,
        effect_verdict: str = "",
    ) -> Optional[AuditEntry]:
        """
        事后更新决策结果（追加写入，不修改原始决策）。

        Returns:
            更新后的条目，若条目不存在则返回 None。
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return None

        entry.outcome = outcome
        entry.actual_effect = actual_effect
        entry.rollback_hash = rollback_hash
        if health_after is not None:
            entry.health_after = health_after
        if effect_score is not None:
            entry.effect_score = effect_score
        if effect_verdict:
            entry.effect_verdict = effect_verdict

        self._save()
        return entry

    # ── 查询 ────────────────────────────────────────────

    def query(
        self,
        days: Optional[int] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        tags: Optional[List[str]] = None,
        outcome: Optional[DecisionOutcome] = None,
        strategy_mode: Optional[str] = None,
        limit: int = 50,
    ) -> List[AuditEntry]:
        """
        按条件查询审计记录。

        Args:
            days: 最近 N 天
            start/end: ISO 时间范围
            tags: 按标签筛选（包含任一匹配）
            outcome: 按结果筛选
            strategy_mode: 按策略模式筛选
            limit: 最大返回数
        """
        # 时间范围
        if days:
            start_dt = datetime.now() - timedelta(days=days)
        elif start:
            start_dt = datetime.fromisoformat(start)
        else:
            start_dt = None

        if end:
            end_dt = datetime.fromisoformat(end)
        else:
            end_dt = None

        results = []
        for entry in self._entries.values():
            ts = datetime.fromisoformat(entry.timestamp)

            if start_dt and ts < start_dt:
                continue
            if end_dt and ts > end_dt:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            if outcome and entry.outcome != outcome:
                continue
            if strategy_mode and entry.strategy_mode != strategy_mode:
                continue
            results.append(entry)

        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get(self, entry_id: str) -> Optional[AuditEntry]:
        """按 ID 获取单条记录。"""
        return self._entries.get(entry_id)

    def report(self, entry_id: str) -> str:
        """生成单条记录的详细报告。"""
        entry = self._entries.get(entry_id)
        if not entry:
            return f"⚠️ 未找到审计条目 {entry_id}"

        lines = [
            f"# 审计记录：{entry.entry_id}",
            f"- **时间**：{entry.timestamp}",
            f"- **策略模式**：{entry.strategy_mode}",
            f"- **决策**：{entry.decision}",
            f"- **理由**：{entry.rationale}",
            f"- **预期效果**：{entry.expected_effect or '（未填写）'}",
            f"- **实际效果**：{entry.actual_effect or '（待评估）'}",
            f"- **结果**：{entry.outcome.value}",
        ]
        if entry.files_changed:
            lines.append(f"- **变更文件**：{', '.join(entry.files_changed)}")
        if entry.rollback_hash:
            lines.append(f"- **回滚 Hash**：{entry.rollback_hash}")
        if entry.health_before is not None:
            lines.append(f"- **变更前健康评分**：{entry.health_before}")
        if entry.health_after is not None:
            lines.append(f"- **变更后健康评分**：{entry.health_after}")
        if entry.effect_score is not None:
            lines.append(f"- **量化效果评分**：{entry.effect_score:+.3f}")
        if entry.effect_verdict:
            lines.append(f"- **效果判定**：{entry.effect_verdict}")
        if entry.tags:
            lines.append(f"- **标签**：{', '.join(entry.tags)}")
        if entry.related_tasks:
            lines.append(f"- **关联任务**：{', '.join(entry.related_tasks)}")

        return "\n".join(lines)

    # ── 统计 ────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """审计统计信息。"""
        total = len(self._entries)
        outcomes = {o.value: 0 for o in DecisionOutcome}
        mode_counts: Dict[str, int] = {}
        tag_counts: Dict[str, int] = {}

        for entry in self._entries.values():
            outcomes[entry.outcome.value] += 1
            mode_counts[entry.strategy_mode] = mode_counts.get(entry.strategy_mode, 0) + 1
            for tag in entry.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        success_count = outcomes.get("success", 0)
        rollback_count = outcomes.get("rolled_back", 0)

        return {
            "total_decisions": total,
            "by_outcome": outcomes,
            "success_rate": round(success_count / total * 100, 1) if total > 0 else 0,
            "rollback_rate": round(rollback_count / total * 100, 1) if total > 0 else 0,
            "by_strategy_mode": mode_counts,
            "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        }

    # ── 持久化 ──────────────────────────────────────────

    def _save(self):
        data = {eid: entry.to_dict() for eid, entry in self._entries.items()}
        AUDIT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        if not AUDIT_FILE.exists():
            return
        try:
            data = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
            self._entries = {eid: AuditEntry.from_dict(d) for eid, d in data.items()}
        except (json.JSONDecodeError, KeyError, TypeError):
            self._entries = {}

    def reload(self) -> "AuditLog":
        """从文件重新加载（用于跨进程修改后的缓存一致性）。

        场景：审计文件被子进程（如 self_improver 离线修复、独立脚本）修改后，
        当前进程的单例仍持有旧数据。调用此方法可强制刷新为最新状态。
        """
        self._load()
        return self

    def _enforce_limit(self):
        if len(self._entries) > self.MAX_ENTRIES:
            sorted_entries = sorted(self._entries.values(), key=lambda x: x.timestamp)
            to_remove = sorted_entries[: len(self._entries) - self.MAX_ENTRIES]
            for entry in to_remove:
                del self._entries[entry.entry_id]


# ── 全局单例 ───────────────────────────────────────────────

_audit = AuditLog()


# ── 工具函数 ──────────────────────────────────────────────

def execute_audit_log_tool(arguments: dict) -> str:
    """审计日志工具入口。"""
    action = arguments.get("action", "stats")

    # 读操作前刷新缓存，避免跨进程修改后的不一致（v2.1）
    if action in ("stats", "query", "get", "report"):
        _audit.reload()

    try:
        if action == "log":
            decision = arguments.get("decision", "")
            rationale = arguments.get("rationale", "")
            strategy_mode = arguments.get("strategy_mode", "unknown")
            if not decision:
                return "❌ 请提供 decision 参数（决策描述）。"

            files = arguments.get("files_changed", [])
            if isinstance(files, str):
                import json as _json
                files = _json.loads(files)
            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                import json as _json
                tags = _json.loads(tags)

            entry = _audit.log(
                decision=decision,
                rationale=rationale,
                strategy_mode=strategy_mode,
                files_changed=files,
                expected_effect=arguments.get("expected_effect", ""),
                tags=tags,
                related_tasks=arguments.get("related_tasks", []),
                health_before=arguments.get("health_before"),
                metadata=arguments.get("metadata", {}),
            )
            return f"📝 审计记录已创建: {entry.entry_id}\n决策: {entry.decision}"

        elif action == "update":
            entry_id = arguments.get("entry_id", "")
            outcome_str = arguments.get("outcome", "success")
            try:
                outcome = DecisionOutcome(outcome_str)
            except ValueError:
                valid = ", ".join(o.value for o in DecisionOutcome)
                return f"❌ 无效结果: {outcome_str}。可用: {valid}"

            entry = _audit.update_outcome(
                entry_id=entry_id,
                outcome=outcome,
                actual_effect=arguments.get("actual_effect", ""),
                rollback_hash=arguments.get("rollback_hash", ""),
                health_after=arguments.get("health_after"),
                effect_score=arguments.get("effect_score"),
                effect_verdict=arguments.get("effect_verdict", ""),
            )
            if entry:
                return f"✅ 审计记录 {entry_id} 已更新: {outcome.value}"
            return f"❌ 未找到审计条目: {entry_id}"

        elif action == "query":
            days = arguments.get("days")
            if days is not None:
                days = int(days)
            tags = arguments.get("tags", [])
            if isinstance(tags, str):
                import json as _json
                tags = _json.loads(tags)
            outcome_str = arguments.get("outcome", "")
            outcome = DecisionOutcome(outcome_str) if outcome_str else None
            mode = arguments.get("strategy_mode", "")
            limit = int(arguments.get("limit", 50))

            results = _audit.query(
                days=days,
                tags=tags,
                outcome=outcome,
                strategy_mode=mode or None,
                limit=limit,
            )
            if not results:
                return "📭 未找到匹配的审计记录。"

            lines = [f"📋 找到 {len(results)} 条审计记录:"]
            for r in results:
                icon = {"success": "✅", "failed": "❌", "rolled_back": "🔄", "partial": "⚠️", "pending": "⏳"}.get(
                    r.outcome.value, "•")
                lines.append(
                    f"  {icon} [{r.timestamp[:19]}] {r.decision[:60]}"
                    f"{'...' if len(r.decision) > 60 else ''}"
                )
            return "\n".join(lines)

        elif action == "get":
            entry_id = arguments.get("entry_id", "")
            entry = _audit.get(entry_id)
            if entry:
                return _audit.report(entry_id)
            return f"❌ 未找到审计条目: {entry_id}"

        elif action == "report":
            entry_id = arguments.get("entry_id", "")
            return _audit.report(entry_id)

        elif action == "stats":
            stats = _audit.stats()
            import json as _json
            return _json.dumps(stats, ensure_ascii=False, indent=2)

        else:
            return f"未知操作: {action}。可用: log, update, query, get, report, stats"

    except Exception as exc:
        return f"审计日志错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "audit_log",
        "description": (
            "进化审计日志。记录每次进化决策的完整上下文（who/what/why/when/effect），"
            "支持按时间、标签、结果、策略模式查询。不可篡改，追加写入。"
            "Evolver 每次修改代码后应调用 log 记录决策，事后调用 update 更新实际效果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["log", "update", "query", "get", "report", "stats"],
                    "description": (
                        "操作类型：log — 记录进化决策；"
                        "update — 事后更新结果；"
                        "query — 按条件查询；"
                        "get — 按 ID 获取详情；"
                        "report — 生成单条详细报告；"
                        "stats — 审计统计"
                    ),
                    "default": "stats",
                },
                "decision": {
                    "type": "string",
                    "description": "决策描述（做了什么）— log 操作必需",
                    "default": "",
                },
                "rationale": {
                    "type": "string",
                    "description": "决策理由（为什么做）",
                    "default": "",
                },
                "strategy_mode": {
                    "type": "string",
                    "description": "当时的策略模式: aggressive / conservative / maintenance",
                    "default": "",
                },
                "files_changed": {
                    "type": "string",
                    "description": "变更文件列表 JSON，如 '[\"evolver/health_dashboard.py\"]'",
                    "default": "[]",
                },
                "expected_effect": {
                    "type": "string",
                    "description": "预期效果描述",
                    "default": "",
                },
                "actual_effect": {
                    "type": "string",
                    "description": "实际效果描述（update 时填写）",
                    "default": "",
                },
                "tags": {
                    "type": "string",
                    "description": "标签 JSON 数组，如 '[\"evolution\",\"tool\"]'",
                    "default": "[]",
                },
                "entry_id": {
                    "type": "string",
                    "description": "审计条目 ID（用于 update/get/report）",
                    "default": "",
                },
                "outcome": {
                    "type": "string",
                    "enum": ["success", "partial", "failed", "rolled_back", "pending"],
                    "description": "决策结果",
                    "default": "success",
                },
                "days": {
                    "type": "integer",
                    "description": "查询最近 N 天（用于 query）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大返回数",
                    "default": 50,
                },
                "health_before": {
                    "type": "number",
                    "description": "变更前健康评分",
                },
                "health_after": {
                    "type": "number",
                    "description": "变更后健康评分（update 时填写）",
                },
                "rollback_hash": {
                    "type": "string",
                    "description": "回滚到的标识（update 时填写）",
                    "default": "",
                },
                "effect_score": {
                    "type": "number",
                    "description": "量化效果评分 -1.0~+1.0（update 时填写，来自 EffectEvaluator）",
                    "default": 0.0,
                },
                "effect_verdict": {
                    "type": "string",
                    "description": "效果判定: improved / degraded / unchanged（update 时填写）",
                    "default": "",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


# ── 便捷函数 ──────────────────────────────────────────────

def get_audit_log() -> AuditLog:
    """获取审计日志实例。"""
    return _audit
