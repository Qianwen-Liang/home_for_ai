"""hot_reload — 模块热重载与单例刷新（自我进化"生产级化"的最后一公里）

问题背景：
  self_improver 修改代码文件后，agent 进程里的旧模块/旧单例仍被引用，
  导致"改了文件但运行时没变"的【伪进化】——进化只写进了磁盘，没有进入运行时。

机制：
  importlib.reload(mod) 会重新执行模块顶层代码，模块级单例（如 `_audit = AuditLog()`）
  会被重新创建并重新 _load() 磁盘数据，从而刷新为最新状态。

  配合两条访问约定，使新代码立即生效、无需重启：
    1. 工具入口用「模块引用」访问单例（agent1.py 中 `tool_xxx.execute_xxx_tool(...)`），
       reload 后模块 __dict__ 被原地更新，旧引用立即看到新代码 + 新单例；
    2. 跨模块取单例用「函数内 from-import」或 get_xxx() 惰性获取，
       避免模块顶层 `from x import _singleton` 持有旧引用。

用法：
    from evolver.hot_reload import hot_reload
    hot_reload(["evolver/audit_log.py"])
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# 变更文件路径（相对 agent-sandbox 根目录，统一正斜杠）→ 模块名
# 仅收录「顶层副作用幂等」的模块，reload 安全（mkdir / sys.path.insert 等重复执行无害）。
HOT_RELOAD_MAP = {
    # ── evolver 模块 ──
    "evolver/audit_log.py": "evolver.audit_log",
    "evolver/effect_evaluator.py": "evolver.effect_evaluator",
    "evolver/self_improver.py": "evolver.self_improver",
    "evolver/cycle_tracker.py": "evolver.cycle_tracker",
    "evolver/health_dashboard.py": "evolver.health_dashboard",
    "evolver/improvement_generator.py": "evolver.improvement_generator",
    "evolver/evolution_strategy.py": "evolver.evolution_strategy",
    "evolver/automated_patcher.py": "evolver.automated_patcher",
    "evolver/self_healing.py": "evolver.self_healing",
    "evolver/safe_deploy.py": "evolver.safe_deploy",
    "evolver/usage_analyzer.py": "evolver.usage_analyzer",
    "evolver/tech_radar.py": "evolver.tech_radar",
    "evolver/env_awareness.py": "evolver.env_awareness",
    # ── tools 模块 ──
    "tools/specialist_base.py": "tools.specialist_base",
    "tools/agent_manager.py": "tools.agent_manager",
    "tools/agent_profile.py": "tools.agent_profile",
    "tools/knowledge_store.py": "tools.knowledge_store",
    "tools/monitor.py": "tools.monitor",
    "tools/self_check.py": "tools.self_check",
    "tools/task_tracker.py": "tools.task_tracker",
    "tools/decision_engine.py": "tools.decision_engine",
    "tools/safety_net.py": "tools.safety_net",
    "tools/test_runner.py": "tools.test_runner",
    "tools/offline_runner.py": "tools.offline_runner",
    "tools/checkpoint_manager.py": "tools.checkpoint_manager",
    "tools/task_dispatcher.py": "tools.task_dispatcher",
    "tools/orchestrator.py": "tools.orchestrator",
    "tools/auto_repair.py": "tools.auto_repair",
    "tools/repair_executors.py": "tools.repair_executors",
    "tools/executor_registry.py": "tools.executor_registry",
    "tools/runner.py": "tools.runner",
    "tools/calculator.py": "tools.calculator",
    "tools/web_search.py": "tools.web_search",
    "tools/file_utils.py": "tools.file_utils",
    "tools/message_bus.py": "tools.message_bus",
    "tools/role_system.py": "tools.role_system",
    "tools/workflow_engine.py": "tools.workflow_engine",
    "tools/code_analyzer.py": "tools.code_analyzer",
}


def resolve_module_name(file_path: str) -> str | None:
    """根据变更文件路径返回模块名（未收录返回 None）。"""
    norm = file_path.replace("\\", "/").lstrip("./")
    return HOT_RELOAD_MAP.get(norm)


def hot_reload(
    files: list[str],
    skip_modules: list[str] | None = None,
) -> list[str]:
    """对变更文件对应的【已加载】模块执行热重载。

    Args:
        files: 变更文件路径列表（相对 agent-sandbox 根目录）
        skip_modules: 需跳过的模块名列表（如调用方自身，避免 reload 自己破坏当前执行上下文）

    Returns:
        人类可读的结果列表。
    """
    skip = set(skip_modules or [])
    results: list[str] = []

    for f in files:
        mod_name = resolve_module_name(f)
        if not mod_name:
            results.append(f"⚠️ {f} (不在可重载映射)")
            continue
        if mod_name in skip:
            results.append(f"⏭️ {mod_name} (主动跳过，需重启生效)")
            continue
        mod = sys.modules.get(mod_name)
        if mod is None:
            results.append(f"ℹ️ {mod_name} (未加载，无需重载)")
            continue
        try:
            importlib.reload(mod)
            results.append(f"✅ {mod_name}")
        except Exception as exc:
            results.append(f"❌ {mod_name} ({type(exc).__name__}: {exc})")

    return results
