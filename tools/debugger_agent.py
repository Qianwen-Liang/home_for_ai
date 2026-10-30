"""
debugger_agent — Debugger 调试守护者智能体
==========================================
独立模块，继承 SpecialistAgent，提供异常诊断、自动修复、快照和离线扫描。
"""

from __future__ import annotations

import json, time
from datetime import datetime
from pathlib import Path
from typing import Any

from .specialist_base import (
    SpecialistAgent, TaskInput, TaskResult, TaskStatus, SpecialistError,
)

SANDBOX_DIR = Path(__file__).resolve().parent.parent


class DebuggerAgent(SpecialistAgent):
    """🐛 Debugger — 调试守护者智能体。"""

    DIAGNOSTIC_RULES: dict[str, dict[str, Any]] = {
        "api_timeout": {"pattern": ["timeout", "timed out", "TimeoutError"], "severity": "high", "category": "network",
            "suggestions": ["检查网络连接", "增大超时时间", "使用备用API端点", "降低并发数"]},
        "api_connection": {"pattern": ["RemoteDisconnected", "ConnectionReset", "URLError", "无法连接", "connection refused"],
            "severity": "high", "category": "network",
            "suggestions": ["检查API服务状态", "等待后重试", "检查API密钥", "切换网络"]},
        "api_auth": {"pattern": ["401", "403", "unauthorized", "forbidden", "API key"],
            "severity": "critical", "category": "auth",
            "suggestions": ["检查API密钥是否过期", "重新配置.env密钥", "检查API配额"]},
        "api_rate_limit": {"pattern": ["429", "rate limit", "too many requests"],
            "severity": "medium", "category": "quota",
            "suggestions": ["等待速率限制重置", "降低请求频率", "启用请求队列"]},
        "api_empty_response": {"pattern": ["空消息", "empty", "null content", "no content"],
            "severity": "high", "category": "api",
            "suggestions": ["重新发送请求", "检查消息格式", "简化输入内容"]},
        "json_parse": {"pattern": ["JSONDecodeError", "json", "parse error", "无效 JSON"],
            "severity": "medium", "category": "data",
            "suggestions": ["检查API返回数据", "确保参数格式正确", "添加数据验证"]},
        "tool_not_found": {"pattern": ["未知工具", "unknown tool", "not found"],
            "severity": "low", "category": "config",
            "suggestions": ["检查工具名称拼写", "确认工具已注册", "检查导入路径"]},
        "tool_validation": {"pattern": ["参数", "validation", "required", "必须"],
            "severity": "low", "category": "config",
            "suggestions": ["检查工具参数格式", "确保必填参数已提供"]},
        "ssl_error": {"pattern": ["SSL", "certificate", "UNEXPECTED_EOF"],
            "severity": "high", "category": "network",
            "suggestions": ["更新SSL证书", "检查系统时间", "添加SSL上下文配置"]},
        "memory_error": {"pattern": ["MemoryError", "memory", "OOM", "out of memory"],
            "severity": "critical", "category": "resource",
            "suggestions": ["减少工具调用轮次", "清理历史消息缓存", "降低并发数据量"]},
    }

    AUTO_FIX_STRATEGIES: dict[str, list[dict[str, Any]]] = {
        "network": [{"name": "重试连接", "action": "retry", "delay": 2.0},
                     {"name": "切换备用端点", "action": "switch_endpoint"},
                     {"name": "降低超时阈值", "action": "increase_timeout"}],
        "auth": [{"name": "重新加载密钥", "action": "reload_key"}],
        "quota": [{"name": "启用请求节流", "action": "throttle", "delay": 5.0}],
        "api": [{"name": "简化请求", "action": "simplify_request"},
                {"name": "重置对话上下文", "action": "reset_context"}],
        "resource": [{"name": "清理缓存", "action": "clear_cache"}],
        "config": [{"name": "检查工具注册", "action": "verify_tools"}],
    }

    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            agent_id=agent_id or "debugger", name="Debugger", specialist_type="debugger",
            description="调试守护者智能体",
            capabilities=["debugging", "monitoring", "analysis", "testing", "recovery"],
            tools=["read_file", "list_directory", "write_file", "replace_text", "make_directory",
                   "run_command", "calculate", "file_utils", "knowledge", "task_tracker",
                   "self_check", "test_runner", "monitor", "decision_engine", "safety_net",
                   "web_search", "offline", "checkpoint", "specialist", "agent_profile",
                   "task_dispatcher", "orchestrator", "auto_repair", "artifact_validator",
                   "villager", "village_chat", "health_dashboard", "usage_analyzer",
                   "safe_deploy", "tech_radar", "env_awareness", "evolution_strategy",
                   "audit_log", "blackboard", "effect_evaluator", "evidence_verifier",
                   "multi_reviewer", "improvement_generator", "self_improver",
                   "cycle_tracker", "self_healing", "offline_research"],
        )
        self._snapshot_dir = SANDBOX_DIR / "memory" / "snapshots"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._diagnosis_history: list[dict[str, Any]] = []
        self._fix_history: list[dict[str, Any]] = []

    def process_task(self, task: TaskInput) -> TaskResult:
        self._current_task = task
        self.status = TaskStatus.PROCESSING
        start_time = time.time()
        try:
            action = task.params.get("action", "diagnose")
            error_text = task.params.get("error", task.description)
            context = task.params.get("context", {})
            if action == "diagnose":
                result = self._execute_diagnose(error_text, context)
            elif action == "auto_fix":
                result = self._execute_auto_fix(error_text, context)
            elif action == "snapshot":
                result = self._execute_snapshot(error_text, context)
            elif action == "health_check":
                result = self._execute_health_check(context)
            elif action == "report":
                result = self._execute_report()
            elif action == "offline_scan":
                target = task.params.get("target", "tools")
                scan_type = task.params.get("scan_type", "quick")
                result = self._execute_offline_scan(target, scan_type, context)
            else:
                raise SpecialistError(f"未知 Debugger 操作: {action}")
        except Exception as exc:
            result = TaskResult(task_id=task.task_id, status=TaskStatus.FAILED.value,
                                error=f"Debugger 任务失败: {exc}", duration=time.time() - start_time)
        self.status = result.status
        self._last_result = result
        self._task_history.append(result)
        self._current_task = None
        return result

    def _execute_diagnose(self, error_text: str, context: dict[str, Any]) -> TaskResult:
        error_lower = error_text.lower()
        matched_rules: list[dict[str, Any]] = []
        all_suggestions: list[str] = []
        for rule_name, rule in self.DIAGNOSTIC_RULES.items():
            for pattern in rule["pattern"]:
                if pattern.lower() in error_lower:
                    matched_rules.append({"rule": rule_name, "severity": rule["severity"], "category": rule["category"]})
                    all_suggestions.extend(rule["suggestions"])
                    break
        if not matched_rules:
            matched_rules.append({"rule": "unknown", "severity": "medium", "category": "unknown"})
            all_suggestions = ["收集详细错误堆栈", "检查最近系统变更", "尝试重启服务", "查看日志获取线索"]
        unique_suggestions = list(dict.fromkeys(all_suggestions))
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_severity = max(matched_rules, key=lambda r: severity_order.get(r["severity"], 1))["severity"]
        primary_category = matched_rules[0]["category"]
        diagnosis = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "error": error_text[:200], "matched_rules": matched_rules,
                     "severity": max_severity, "category": primary_category,
                     "suggestions": unique_suggestions}
        self._diagnosis_history.append(diagnosis)
        if len(self._diagnosis_history) > 50:
            self._diagnosis_history = self._diagnosis_history[-50:]
        sev_icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        icon = sev_icons.get(max_severity, "⚪")
        output = {"diagnosis": {"error_snippet": error_text[:300], "matched_rules": matched_rules,
                                "severity": max_severity, "category": primary_category},
                  "suggestions": unique_suggestions,
                  "has_auto_fix": primary_category in self.AUTO_FIX_STRATEGIES}
        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value, output=output,
                          summary=f"{icon} Debugger 诊断完成 | 类别: {primary_category} | 严重: {max_severity}",
                          duration=0.0, suggestions=unique_suggestions[:5])

    def _execute_auto_fix(self, error_text: str, context: dict[str, Any]) -> TaskResult:
        error_lower = error_text.lower()
        primary_category = "unknown"
        for rule_name, rule in self.DIAGNOSTIC_RULES.items():
            for pattern in rule["pattern"]:
                if pattern.lower() in error_lower:
                    primary_category = rule["category"]; break
            if primary_category != "unknown": break
        strategies = self.AUTO_FIX_STRATEGIES.get(primary_category, [])

        # 记录诊断（保留 Debugger 的诊断价值），但不直接"修复"
        fix_record = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      "category": primary_category, "error": error_text[:200],
                      "actions": [s["name"] for s in strategies], "applied": 0, "failed": 0,
                      "routed_to": "auto_repair/self_healing"}
        self._fix_history.append(fix_record)
        if len(self._fix_history) > 50: self._fix_history = self._fix_history[-50:]

        # 分工：Debugger 只诊断和建议，真正的修复由 evolver 修复引擎执行
        suggestions = [s["name"] for s in strategies][:5] + [
            "使用 auto_repair action=repair 执行确定性修复",
            "使用 self_healing action=heal 执行 LLM 驱动的愈疗",
        ]
        output = {
            "action": "auto_fix",
            "category": primary_category,
            "fixed": False,
            "diagnosis": {"category": primary_category, "error": error_text[:200]},
            "routing": {
                "deterministic_repair": "auto_repair",
                "llm_repair": "self_healing",
            },
            "message": "Debugger 完成诊断，真正的自动修复由修复引擎执行",
            "suggestions": suggestions,
        }
        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value,
                          output=output,
                          summary=f"🐛 Debugger 诊断完成 (类别: {primary_category})，修复已路由到引擎",
                          duration=0.0,
                          suggestions=suggestions)

    def _execute_snapshot(self, reason: str, context: dict[str, Any]) -> TaskResult:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"snap_{timestamp}"
        snapshot = {"snapshot_id": snapshot_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason[:200] if reason else "手动触发", "context": context,
                    "diagnosis_history": self._diagnosis_history[-10:],
                    "fix_history": self._fix_history[-10:],
                    "agent_status": {"agent_id": self.agent_id, "name": self.name, "status": self.status,
                                     "total_tasks": len(self._task_history)}}
        snapshot_file = self._snapshot_dir / f"{snapshot_id}.json"
        try:
            snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                              status=TaskStatus.FAILED.value, error=f"快照保存失败: {exc}", duration=0.0)
        self._cleanup_old_snapshots(keep=20)
        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value,
                          output={"action": "snapshot", "snapshot_id": snapshot_id,
                                  "snapshot_file": str(snapshot_file), "reason": reason[:200] if reason else "手动触发"},
                          summary=f"📸 快照已保存: {snapshot_id}", duration=0.0,
                          suggestions=[f"快照文件: {snapshot_file}", "定期保存快照确保数据安全"])

    def _cleanup_old_snapshots(self, keep: int = 20) -> None:
        try:
            snapshots = sorted(self._snapshot_dir.glob("snap_*.json"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
            for old in snapshots[keep:]: old.unlink(missing_ok=True)
        except (OSError, PermissionError): pass

    def _execute_health_check(self, context: dict[str, Any]) -> TaskResult:
        recent = self._diagnosis_history[-20:]
        total_recent = len(recent)
        if total_recent == 0:
            health_status, health_score = "healthy", 100
        else:
            severity_weights = {"low": 1, "medium": 3, "high": 8, "critical": 15}
            total_weight = sum(severity_weights.get(d.get("severity", "medium"), 3) for d in recent)
            health_score = max(0, 100 - int((total_weight / (total_recent * 15)) * 100))
            health_status = "healthy" if health_score >= 90 else "fair" if health_score >= 70 else "degraded" if health_score >= 40 else "critical"
        cat_counts: dict[str, int] = {}
        sev_counts: dict[str, int] = {}
        for d in self._diagnosis_history:
            cat_counts[d.get("category", "unknown")] = cat_counts.get(d.get("category", "unknown"), 0) + 1
            sev_counts[d.get("severity", "medium")] = sev_counts.get(d.get("severity", "medium"), 0) + 1
        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value,
                          output={"action": "health_check", "health_status": health_status,
                                  "health_score": health_score,
                                  "statistics": {"total_diagnoses": len(self._diagnosis_history),
                                                 "total_fixes": len(self._fix_history),
                                                 "recent_diagnoses": total_recent,
                                                 "category_distribution": cat_counts,
                                                 "severity_distribution": sev_counts}},
                          summary=f"🏥 系统健康: {health_status} (评分: {health_score}/100)",
                          duration=0.0)

    def _execute_report(self) -> TaskResult:
        total_d = len(self._diagnosis_history)
        total_f = len(self._fix_history)
        fix_rate = sum(1 for f in self._fix_history if f.get("applied", 0) > 0 and f.get("failed", 0) == 0) / total_f if total_f > 0 else 1.0
        snap_count = len(list(self._snapshot_dir.glob("snap_*.json")))
        lines = [f"🐛 Debugger Agent 工作报告", f"{'='*50}", "",
                 f"📊 总览", f"  诊断: {total_d}", f"  修复: {total_f}",
                 f"  成功率: {fix_rate:.0%}", f"  快照: {snap_count}", f"  任务: {len(self._task_history)}"]
        output_text = "\n".join(lines)
        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value,
                          output={"action": "report", "total_diagnoses": total_d, "total_fixes": total_f,
                                  "fix_rate": fix_rate, "snapshot_count": snap_count, "report_text": output_text},
                          summary=f"📊 Debugger 报告: {total_d}次诊断, {total_f}次修复, 成功率{fix_rate:.0%}", duration=0.0)

    def _execute_offline_scan(self, target: str, scan_type: str, context: dict[str, Any]) -> TaskResult:
        import ast
        scan_dir = SANDBOX_DIR / target
        if not scan_dir.is_dir():
            return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                              status=TaskStatus.DONE.value,
                              output={"action": "offline_scan", "target": target, "error": f"目录不存在: {target}"},
                              summary=f"❌ 离线扫描失败: 目录 '{target}' 不存在", duration=0.0)
        py_files = list(scan_dir.rglob("*.py"))
        md_files = list(scan_dir.rglob("*.md"))
        json_files = list(scan_dir.rglob("*.json"))
        all_files = py_files + md_files + json_files
        if scan_type == "quick":
            all_files = [f for f in all_files if f.parent == scan_dir][:20]
        files_scanned = len(all_files)
        issues: list[dict[str, Any]] = []

        # 语法检查
        for pf in py_files:
            if scan_type == "quick" and pf.parent != scan_dir: continue
            try:
                ast.parse(pf.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                issues.append({"file": str(pf.relative_to(SANDBOX_DIR)), "severity": "high",
                               "type": "语法错误", "detail": f"第{exc.lineno}行: {exc.msg}"})
            except (OSError, UnicodeError) as exc:
                issues.append({"file": str(pf.relative_to(SANDBOX_DIR)), "severity": "medium",
                               "type": "文件读取错误", "detail": str(exc)})

        # 文件大小检查
        for f in all_files:
            try:
                size = f.stat().st_size
                if size > 100 * 1024:
                    issues.append({"file": str(f.relative_to(SANDBOX_DIR)),
                                   "severity": "low" if size < 500 * 1024 else "medium",
                                   "type": "文件过大", "detail": f"{size/1024:.0f}KB"})
            except OSError: pass

        # 敏感信息检查
        sensitive = ["api_key", "password", "secret", "token", "sk-", "DEEPSEEK"]
        for pf in py_files:
            if scan_type == "quick" and pf.parent != scan_dir: continue
            try:
                content = pf.read_text(encoding="utf-8")
                for pat in sensitive:
                    for lno, line in enumerate(content.split("\n"), 1):
                        if pat.lower() in line.lower():
                            stripped = line.strip()
                            if stripped.startswith("#") or not stripped: continue
                            if any(s in stripped for s in ["os.environ.get", "os.getenv", ".env", "环境变量"]): continue
                            issues.append({"file": str(pf.relative_to(SANDBOX_DIR)), "severity": "medium",
                                           "type": "敏感信息", "detail": f"第{lno}行包含 '{pat}'"})
                            break
            except (OSError, UnicodeError): pass

        # 导入检查
        for pf in py_files:
            if scan_type == "quick" and pf.parent != scan_dir: continue
            try:
                tree = ast.parse(pf.read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names: imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names: imports.append(f"{module}.{alias.name}")
                for imp in imports:
                    if imp.startswith("tools."):
                        parts = imp.split(".")
                        if len(parts) >= 2:
                            mf = SANDBOX_DIR / "tools" / f"{parts[1]}.py"
                            if not mf.is_file():
                                issues.append({"file": str(pf.relative_to(SANDBOX_DIR)), "severity": "high",
                                               "type": "导入目标不存在", "detail": f"导入 '{imp}' 但文件不存在"})
            except (SyntaxError, OSError, UnicodeError): pass

        sev_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        type_count: dict[str, int] = {}
        for iss in issues:
            sev_count[iss.get("severity", "low")] = sev_count.get(iss.get("severity", "low"), 0) + 1
            type_count[iss.get("type", "其他")] = type_count.get(iss.get("type", "其他"), 0) + 1

        # 保存报告
        report_file = SANDBOX_DIR / "memory" / "offline" / f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        lines = [f"🔍 Debugger 离线扫描报告", f"{'='*50}", "",
                 f"📋 目标: {target} | 模式: {scan_type} | 文件: {files_scanned} | 问题: {len(issues)}", ""]
        for sev in ["critical", "high", "medium", "low"]:
            c = sev_count.get(sev, 0)
            if c: lines.append(f"  {'🔴🟠🟡🟢'[['critical','high','medium','low'].index(sev)]} {sev}: {c}")
        lines.append("")
        for iss in issues[:15]:
            lines.append(f"  [{iss.get('type','?')}] {iss.get('file','?')}: {iss.get('detail','')}")
        if len(issues) > 15: lines.append(f"  ... 还有 {len(issues)-15} 个问题")
        report_text = "\n".join(lines)
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(report_text, encoding="utf-8")
        except (OSError, UnicodeError): pass

        return TaskResult(task_id=self._current_task.task_id if self._current_task else "",
                          status=TaskStatus.DONE.value,
                          output={"action": "offline_scan", "target": target, "scan_type": scan_type,
                                  "files_scanned": files_scanned, "total_issues": len(issues),
                                  "severity_distribution": sev_count, "issue_types": type_count,
                                  "issues_sample": issues[:20], "report_file": str(report_file)},
                          summary=f"🔍 离线扫描完成 | 目标: {target} | 文件: {files_scanned} | 问题: {len(issues)}",
                          duration=0.0)
