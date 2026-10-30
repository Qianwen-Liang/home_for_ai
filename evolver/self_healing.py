"""
self_healing — LLM 驱动的自主愈疗守护者 v1.0

创新型功能：不同于 regex 匹配的 bug 修复器，本模块将真实的
错误日志、健康指标和受影响源代码一起喂给 LLM，让它推理根因
并生成创造性修复方案。这是 Gödel Machine 从"外科手术刀"
进化为"全科医生"的关键一步。

架构：
  症状采集 → 上下文构建 → LLM 诊断 → 补丁生成 → 沙箱验证 → 部署/回滚
     ↑                                                              │
     └──────────────── 记录到 audit_log + knowledge ────────────────┘

与 auto_repair 的区别：
  - auto_repair: 基于 traceback 解析 + 模板匹配（确定性）
  - self_healing: 基于 LLM 语义理解 + 上下文推理（创造性）
"""

from __future__ import annotations

import json
import sys
import time
import traceback as _traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
HEAL_DIR = SANDBOX_DIR / "memory" / "healing_sessions"
HEAL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))


@dataclass
class HealingSession:
    """一次愈疗会话的完整记录。"""
    session_id: str
    started_at: str
    finished_at: str = ""

    # 症状
    symptoms: Dict[str, Any] = field(default_factory=dict)
    health_score_before: int = 0

    # LLM 诊断
    diagnosis: str = ""
    root_cause: str = ""
    confidence: float = 0.0

    # 修复
    fix_description: str = ""
    files_changed: List[str] = field(default_factory=list)
    fix_applied: bool = False

    # 验证
    health_score_after: int = 0
    self_check_passed: bool = False
    fix_verified: bool = False
    rolled_back: bool = False

    # 学习
    lessons_learned: str = ""
    audit_entry_id: str = ""

    # 耗时
    duration_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HealingSession":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SelfHealingWatchdog:
    """LLM 驱动的自主愈疗守护者。

    用法：
        watchdog = SelfHealingWatchdog()

        # 完整愈疗流程
        session = watchdog.heal()

        # 仅诊断（不修复）
        diagnosis = watchdog.diagnose()
    """

    def __init__(self):
        self._sessions: Dict[str, HealingSession] = {}

    # ═══════════════════════════════════════════════════════
    # 核心流程：完整愈疗
    # ═══════════════════════════════════════════════════════

    def heal(self, auto_apply: bool = False) -> HealingSession:
        """执行完整的自主愈疗流程。

        1. 采集症状（健康报告 + 错误日志 + 性能数据）
        2. 构建 LLM 上下文
        3. LLM 诊断根因并生成修复方案
        4. 应用修复（如果 auto_apply=True）
        5. 验证修复效果
        6. 记录经验

        Args:
            auto_apply: 是否自动应用修复（默认 False，需人类确认）

        Returns:
            HealingSession 完整记录
        """
        started = time.time()
        session = HealingSession(
            session_id=f"heal-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now().isoformat(),
        )

        try:
            # ── Phase 1: 采集症状 ─────────────────────
            symptoms = self._collect_symptoms()
            session.symptoms = symptoms
            session.health_score_before = symptoms.get("health_score", 0)

            # 如果没有症状，跳过
            if not symptoms.get("has_issues"):
                session.finished_at = datetime.now().isoformat()
                session.diagnosis = "系统健康，无需愈疗。"
                session.duration_sec = round(time.time() - started, 2)
                self._save_session(session)
                return session

            # ── Phase 2: LLM 诊断 ─────────────────────
            diagnosis_result = self._llm_diagnose(symptoms)
            session.diagnosis = diagnosis_result.get("diagnosis", "")
            session.root_cause = diagnosis_result.get("root_cause", "")
            session.confidence = diagnosis_result.get("confidence", 0.0)
            session.fix_description = diagnosis_result.get("fix_plan", "")

            if not session.diagnosis:
                session.finished_at = datetime.now().isoformat()
                session.duration_sec = round(time.time() - started, 2)
                self._save_session(session)
                return session

            # ── Phase 3: 应用修复 ─────────────────────
            if auto_apply and session.fix_description:
                apply_result = self._apply_fix(
                    diagnosis_result.get("target_file", ""),
                    session.fix_description,
                    symptoms,
                )
                session.fix_applied = apply_result.get("success", False)
                session.files_changed = apply_result.get("files", [])
                session.rolled_back = apply_result.get("rolled_back", False)

            # ── Phase 4: 验证 ─────────────────────────
            if session.fix_applied:
                verify_result = self._verify_fix(session)
                session.health_score_after = verify_result.get("health_score", 0)
                session.self_check_passed = verify_result.get("self_check_ok", False)
                session.fix_verified = verify_result.get("overall_ok", False)

            # ── Phase 5: 记录经验 ─────────────────────
            learning = self._record_learning(session)
            session.lessons_learned = learning.get("summary", "")
            session.audit_entry_id = learning.get("audit_id", "")

        except Exception as exc:
            session.diagnosis = f"愈疗过程异常: {exc}"
            session.lessons_learned = _traceback.format_exc()[-300:]

        finally:
            session.finished_at = datetime.now().isoformat()
            session.duration_sec = round(time.time() - started, 2)
            self._save_session(session)

        return session

    def diagnose(self) -> str:
        """仅诊断，不修复。返回诊断报告文本。"""
        symptoms = self._collect_symptoms()
        if not symptoms.get("has_issues"):
            return "✅ 系统健康，未检测到需要愈疗的问题。"

        result = self._llm_diagnose(symptoms)
        return (
            f"## 🩺 自主愈疗诊断\n\n"
            f"**健康评分**: {symptoms.get('health_score', '?')}/100\n\n"
            f"### 症状\n{symptoms.get('summary', '无')}\n\n"
            f"### 诊断\n{result.get('diagnosis', '无法诊断')}\n\n"
            f"### 根因\n{result.get('root_cause', '未知')}\n\n"
            f"### 修复方案\n{result.get('fix_plan', '无')}\n\n"
            f"**置信度**: {result.get('confidence', 0):.0%}"
        )

    # ═══════════════════════════════════════════════════════
    # 症状采集
    # ═══════════════════════════════════════════════════════

    def _collect_symptoms(self) -> Dict[str, Any]:
        """采集系统症状：健康报告 + 错误 + 性能数据。"""
        symptoms: Dict[str, Any] = {
            "has_issues": False,
            "health_score": 0,
            "errors": [],
            "slow_tools": [],
            "summary": "",
        }

        # 1. 健康仪表盘
        try:
            from evolver.health_dashboard import _dashboard
            _dashboard.aggregate()
            symptoms["health_score"] = _dashboard.score()
            alert = _dashboard.alert()
            if alert:
                symptoms["has_issues"] = True
                symptoms["health_alert"] = alert
        except Exception as exc:
            symptoms["errors"].append(f"健康检查失败: {exc}")

        # 2. 自检结果
        try:
            from tools.self_check import _checker
            _checker.check_all(verbose=False)
            failed = sum(1 for r in _checker.results if r.get("status") == "❌")
            if failed > 0:
                symptoms["has_issues"] = True
                symptoms["self_check_failed"] = failed
        except Exception:
            pass

        # 3. 安全网
        try:
            from tools.safety_net import _safety
            sdata = _safety._data
            consecutive = sdata.get("consecutive_errors", 0)
            if consecutive >= 3:
                symptoms["has_issues"] = True
                symptoms["consecutive_errors"] = consecutive
            if sdata.get("rescue_activated"):
                symptoms["has_issues"] = True
                symptoms["rescue_activated"] = True
            # 获取最近错误
            recent = sdata.get("recent_events", [])[-5:]
            symptoms["recent_events"] = [
                {"type": e.get("event_type", ""), "detail": str(e.get("event_detail", ""))[:200]}
                for e in recent
            ]
        except Exception:
            pass

        # 4. 性能监控
        try:
            from tools.monitor import _monitor
            mdata = _monitor._data
            tools_data = mdata.get("tools", {})
            for tool_name, stats in tools_data.items():
                total_calls = stats.get("total_calls", 0)
                total_dur = stats.get("total_duration", 0)
                if total_calls > 0:
                    avg_ms = total_dur / total_calls * 1000
                    if avg_ms > 500:
                        symptoms["has_issues"] = True
                        symptoms["slow_tools"].append({
                            "name": tool_name,
                            "avg_ms": round(avg_ms, 1),
                            "calls": total_calls,
                        })
        except Exception:
            pass

        # 5. 生成摘要
        parts = []
        if symptoms.get("health_alert"):
            parts.append("健康告警")
        if symptoms.get("self_check_failed", 0) > 0:
            parts.append(f"自检失败{symptoms['self_check_failed']}项")
        if symptoms.get("consecutive_errors", 0) >= 3:
            parts.append(f"连续错误{symptoms['consecutive_errors']}次")
        if symptoms.get("slow_tools"):
            parts.append(f"{len(symptoms['slow_tools'])}个慢工具")
        if symptoms.get("recent_events"):
            parts.append(f"{len(symptoms['recent_events'])}个最近事件")

        symptoms["summary"] = "；".join(parts) if parts else "无明显症状"

        return symptoms

    # ═══════════════════════════════════════════════════════
    # LLM 诊断
    # ═══════════════════════════════════════════════════════

    def _llm_diagnose(self, symptoms: Dict[str, Any]) -> Dict[str, Any]:
        """将症状数据喂给 LLM，获取诊断和修复方案。

        返回: {diagnosis, root_cause, confidence, fix_plan, target_file}
        """
        # 构建上下文：症状 + 相关模块的源代码
        context = self._build_diagnosis_context(symptoms)

        # 构建 prompt
        prompt = self._build_diagnosis_prompt(symptoms, context)

        # 调用 LLM
        try:
            from evolver.automated_patcher import AutomatedPatcher
            raw = AutomatedPatcher._call_deepseek(
                system_prompt=(
                    "你是一个资深的 Python 系统诊断专家。"
                    "根据提供的症状数据和源代码，推理根因并给出修复方案。"
                    "用 JSON 格式回复，包含 diagnosis/root_cause/confidence/fix_plan/target_file 字段。"
                ),
                user_message=prompt,
            )
            if raw:
                return self._parse_diagnosis(raw, symptoms)
        except Exception:
            pass

        return {"diagnosis": "LLM 调用失败", "root_cause": "", "confidence": 0, "fix_plan": ""}

    def _build_diagnosis_context(self, symptoms: Dict[str, Any]) -> str:
        """收集可能相关的模块源代码作为诊断上下文。"""
        context_parts = []

        # 如果有慢工具，包含它们的源代码
        for tool in symptoms.get("slow_tools", [])[:3]:
            tool_name = tool.get("name", "")
            for prefix in ["tools/", "evolver/"]:
                path = SANDBOX_DIR / f"{prefix}{tool_name}.py"
                if path.is_file():
                    try:
                        code = path.read_text(encoding="utf-8")
                        if len(code) < 3000:
                            context_parts.append(f"### {prefix}{tool_name}.py\n```python\n{code}\n```")
                        else:
                            context_parts.append(f"### {prefix}{tool_name}.py (前2000字符)\n```python\n{code[:2000]}\n```")
                    except Exception:
                        pass
                    break

        # 如果自检失败，包含自检相关代码
        if symptoms.get("self_check_failed", 0) > 0:
            path = SANDBOX_DIR / "tools/self_check.py"
            if path.is_file():
                try:
                    code = path.read_text(encoding="utf-8")
                    context_parts.append(f"### tools/self_check.py (前2000字符)\n```python\n{code[:2000]}\n```")
                except Exception:
                    pass

        return "\n\n".join(context_parts) if context_parts else "（无相关源代码上下文）"

    def _build_diagnosis_prompt(self, symptoms, context) -> str:
        """构建诊断 prompt。"""
        return (
            f"## 系统症状\n\n"
            f"- 健康评分: {symptoms.get('health_score', '?')}/100\n"
            f"- 症状摘要: {symptoms.get('summary', '无')}\n"
            f"- 健康告警: {str(symptoms.get('health_alert', '无'))[:300]}\n"
            f"- 连续错误: {symptoms.get('consecutive_errors', 0)} 次\n"
            f"- 慢工具: {json.dumps(symptoms.get('slow_tools', []), ensure_ascii=False)}\n"
            f"- 最近事件: {json.dumps(symptoms.get('recent_events', []), ensure_ascii=False)}\n"
            f"\n## 相关源代码\n\n{context}\n\n"
            f"请诊断根因并给出修复方案。回复 JSON 格式:\n"
            f'{{"diagnosis":"...","root_cause":"...","confidence":0.8,"fix_plan":"...","target_file":"tools/xxx.py"}}'
        )

    @staticmethod
    def _parse_diagnosis(raw: str, symptoms: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 返回的诊断 JSON。"""
        import re
        # 尝试提取 JSON
        m = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # 回退：整个响应作为诊断
        return {
            "diagnosis": raw[:500],
            "root_cause": "",
            "confidence": 0.5,
            "fix_plan": raw[:300],
            "target_file": "",
        }

    # ═══════════════════════════════════════════════════════
    # 修复应用
    # ═══════════════════════════════════════════════════════

    def _apply_fix(
        self, target_file: str, fix_plan: str, symptoms: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用 AutomatedPatcher.llm_patch 应用 LLM 生成的修复方案。"""
        if not target_file:
            # 尝试从症状推断目标文件
            if symptoms.get("slow_tools"):
                target_file = f"tools/{symptoms['slow_tools'][0]['name']}.py"
            else:
                return {"success": False, "files": [], "error": "无法确定目标文件"}

        try:
            from evolver.automated_patcher import AutomatedPatcher
            result = AutomatedPatcher.apply(
                target_file,
                "llm_patch",
                params={
                    "idea": fix_plan,
                    "idea_type": "L3",
                    "constraints": "仅修改必要部分。保持现有功能不变。添加错误处理。",
                },
            )
            return {
                "success": result.success,
                "files": [target_file] if result.success else [],
                "description": result.description,
                "rolled_back": False,
            }
        except Exception as exc:
            return {"success": False, "files": [], "error": str(exc), "rolled_back": False}

    # ═══════════════════════════════════════════════════════
    # 验证
    # ═══════════════════════════════════════════════════════

    def _verify_fix(self, session: HealingSession) -> Dict[str, Any]:
        """验证修复是否有效。"""
        result = {"health_score": 0, "self_check_ok": False, "overall_ok": False}

        try:
            from evolver.health_dashboard import _dashboard
            _dashboard.aggregate()
            result["health_score"] = _dashboard.score()
            result["health_improved"] = result["health_score"] >= session.health_score_before
        except Exception:
            pass

        try:
            from tools.self_check import _checker
            _checker.check_all(verbose=False)
            result["self_check_ok"] = not any(r.get("status") == "❌" for r in _checker.results)
        except Exception:
            pass

        result["overall_ok"] = result.get("health_improved", False) and result.get("self_check_ok", False)
        return result

    # ═══════════════════════════════════════════════════════
    # 经验记录
    # ═══════════════════════════════════════════════════════

    def _record_learning(self, session: HealingSession) -> Dict[str, Any]:
        """将愈疗经验记录到 audit_log 和 knowledge。"""
        audit_id = ""
        knowledge_id = ""

        # 审计日志
        try:
            from evolver.audit_log import _audit, DecisionOutcome
            outcome = DecisionOutcome.SUCCESS if session.fix_verified else DecisionOutcome.PARTIAL
            entry = _audit.log(
                decision=f"SelfHealing: {session.diagnosis[:100]}",
                rationale=f"LLM 诊断: {session.root_cause[:200]}",
                strategy_mode="aggressive",
                files_changed=session.files_changed,
                expected_effect=session.fix_description[:200],
                tags=["self-healing", "llm-diagnosis", "innovative"],
                health_before=float(session.health_score_before),
            )
            _audit.update_outcome(
                entry.entry_id,
                outcome=outcome,
                actual_effect=f"Health: {session.health_score_before}→{session.health_score_after}",
                health_after=float(session.health_score_after),
            )
            audit_id = entry.entry_id
        except Exception:
            pass

        # 知识库
        try:
            from tools.knowledge_store import _store
            content = (
                f"# 自主愈疗会话: {session.session_id}\n\n"
                f"## 症状\n{session.symptoms.get('summary', '无')}\n\n"
                f"## 诊断\n{session.diagnosis}\n\n"
                f"## 根因\n{session.root_cause}\n\n"
                f"## 修复\n{session.fix_description}\n\n"
                f"## 结果\n"
                f"- 健康: {session.health_score_before}→{session.health_score_after}\n"
                f"- 修复验证: {'✅' if session.fix_verified else '❌'}\n"
                f"- 置信度: {session.confidence:.0%}\n"
            )
            entry = _store.store(
                title=f"愈疗: {session.diagnosis[:60]}",
                content=content,
                category="healing",
                tags="self-healing,llm-diagnosis",
            )
            knowledge_id = entry
        except Exception:
            pass

        return {
            "summary": f"愈疗{'成功' if session.fix_verified else '部分完成'}，置信度{session.confidence:.0%}",
            "audit_id": audit_id,
            "knowledge_id": knowledge_id,
        }

    # ═══════════════════════════════════════════════════════
    # 历史查询
    # ═══════════════════════════════════════════════════════

    def history(self, limit: int = 10) -> List[HealingSession]:
        """返回最近的愈疗会话。"""
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.started_at,
            reverse=True,
        )
        return sessions[:limit]

    # ═══════════════════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════════════════

    def _save_session(self, session: HealingSession):
        self._sessions[session.session_id] = session
        filepath = HEAL_DIR / "sessions.json"
        data = {sid: s.to_dict() for sid, s in self._sessions.items()}
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── 全局单例 ───────────────────────────────────────────────

_watchdog = SelfHealingWatchdog()


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "self_healing",
        "description": (
            "LLM 驱动的自主愈疗守护者。采集系统症状（健康报告+错误日志+性能数据），"
            "喂给 LLM 推理根因并生成创造性修复方案。不同于 regex 匹配的 auto_repair，"
            "本模块利用 LLM 的语义理解能力处理复杂、新颖的故障模式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["diagnose", "heal", "history", "help"],
                    "description": (
                        "操作类型：diagnose — 仅诊断不修复；"
                        "heal — 完整愈疗流程（诊断→修复→验证）；"
                        "history — 愈疗历史；"
                        "help — 查看帮助"
                    ),
                    "default": "diagnose",
                },
                "auto_apply": {
                    "type": "boolean",
                    "description": "是否自动应用修复（默认 False，需人类确认）",
                    "default": False,
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


def execute_self_healing_tool(arguments: dict) -> str:
    """自主愈疗工具入口。"""
    action = arguments.get("action", "diagnose")

    try:
        if action == "diagnose":
            return _watchdog.diagnose()

        elif action == "heal":
            auto_apply = arguments.get("auto_apply", False)
            session = _watchdog.heal(auto_apply=auto_apply)

            lines = [
                f"## 🩺 自主愈疗完成",
                f"",
                f"**会话**: {session.session_id}",
                f"**耗时**: {session.duration_sec:.1f}s",
                f"",
                f"### 症状",
                f"{session.symptoms.get('summary', '无')}",
                f"",
                f"### LLM 诊断",
                f"{session.diagnosis[:300]}",
                f"",
                f"### 根因",
                f"{session.root_cause or '（未识别）'}",
                f"",
                f"### 修复",
                f"已应用: {'✅' if session.fix_applied else '❌'}",
            ]
            if session.files_changed:
                lines.append(f"变更文件: {', '.join(session.files_changed)}")
            lines.extend([
                f"",
                f"### 验证",
                f"健康: {session.health_score_before} → {session.health_score_after}",
                f"验证: {'✅ 通过' if session.fix_verified else '❌ 未通过'}",
                f"回滚: {'🔄 已回滚' if session.rolled_back else '—'}",
                f"",
                f"### 学习",
                f"{session.lessons_learned}",
            ])
            return "\n".join(lines)

        elif action == "history":
            limit = int(arguments.get("limit", 10))
            sessions = _watchdog.history(limit)
            if not sessions:
                return "暂无愈疗记录。"
            lines = [f"📋 最近 {len(sessions)} 次愈疗:\n"]
            for s in sessions:
                lines.append(
                    f"  [{s.started_at[:19]}] {s.diagnosis[:60]} "
                    f"(健康: {s.health_score_before}→{s.health_score_after})"
                )
            return "\n".join(lines)

        elif action == "help":
            return (
                "🩺 self_healing — LLM 驱动的自主愈疗守护者\n\n"
                "与 auto_repair 的区别:\n"
                "  auto_repair: regex 匹配 → 模板修复 (确定性)\n"
                "  self_healing: LLM 推理 → 创造性修复 (智能)\n\n"
                "操作:\n"
                "  diagnose — 仅诊断（不修改代码）\n"
                "  heal     — 完整愈疗流程\n"
                "  history  — 历史会话\n\n"
                "💡 建议先用 diagnose 了解诊断结果，确认后再 heal"
            )

        else:
            return f"未知操作: {action}。可用: diagnose, heal, history, help"

    except Exception as exc:
        return f"自主愈疗错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    wd = SelfHealingWatchdog()

    print("=== 症状采集 ===")
    symptoms = wd._collect_symptoms()
    print(f"Health: {symptoms['health_score']}")
    print(f"Issues: {symptoms['has_issues']}")
    print(f"Summary: {symptoms['summary']}")

    print("\n=== 诊断 ===")
    diag = wd.diagnose()
    print(diag[:500])
