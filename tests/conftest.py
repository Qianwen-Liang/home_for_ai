"""
pytest 全局配置 — 测试隔离基建。

解决"多智能体协同"相关测试的隔离问题：
这些组件通过持久化文件（agents.json / messages.json / checkpoints 等）共享状态，
测试之间未清理会导致顺序依赖、结果波动。

通过 autouse fixture 在每个测试前后：
  1. 重置持久化文件为默认空状态
  2. 清空目录（checkpoints / offline）
  3. 清空模块级单例的内存状态（避免 reload 带来的跨模块引用问题）
"""

import json
import sys
from pathlib import Path

import pytest

# 将 agent-sandbox 根目录（tests/ 的父目录）加入 sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ── 持久化文件 → 默认空内容 ──────────────────────────────
_PERSISTENT_FILES = {
    "memory/agents.json": {"agents": [], "task_records": []},
    "memory/messages.json": {"queues": {}, "history": [], "subscriptions": {}},
    "memory/dispatch.json": {"pipelines": []},
    "memory/workflows.json": {"definitions": {}, "instances": {}},
}

# ── 持久化目录（清空其中的 *.json）───────────────────────
_PERSISTENT_DIRS = [
    "memory/checkpoints",
    "memory/offline",
]


def _reset_persistent_files() -> None:
    """重置持久化文件为默认空状态。"""
    for rel, default in _PERSISTENT_FILES.items():
        p = _root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(default, ensure_ascii=False), encoding="utf-8")

    for rel in _PERSISTENT_DIRS:
        d = _root / rel
        if d.is_dir():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except OSError:
                    pass


def _clear_singleton_memory() -> None:
    """清空模块级单例的内存状态。

    只清内存、不 reload 模块，避免 reload 导致其他模块持有的旧引用
    （如 orchestrator 顶层 `from tools.agent_manager import _manager`）失效。
    """
    # agent_manager
    mod = sys.modules.get("tools.agent_manager")
    if mod is not None and hasattr(mod, "_manager"):
        mod._manager._agents.clear()
        mod._manager._task_records.clear()

    # message_bus
    mod = sys.modules.get("tools.message_bus")
    if mod is not None and hasattr(mod, "_bus"):
        mod._bus._queues.clear()
        mod._bus._history.clear()
        mod._bus._subscriptions.clear()

    # task_dispatcher
    mod = sys.modules.get("tools.task_dispatcher")
    if mod is not None and hasattr(mod, "_dispatcher"):
        mod._dispatcher._pipelines.clear()

    # workflow_engine
    mod = sys.modules.get("tools.workflow_engine")
    if mod is not None and hasattr(mod, "_engine"):
        mod._engine._definitions.clear()
        mod._engine._instances.clear()

    # offline_runner
    mod = sys.modules.get("tools.offline_runner")
    if mod is not None and hasattr(mod, "_manager"):
        mod._manager._tasks.clear()
        mod._manager._idempotency_map.clear()


@pytest.fixture(autouse=True)
def _isolated_state():
    """每个测试前后清理多智能体持久化状态，确保隔离。"""
    _reset_persistent_files()
    _clear_singleton_memory()
    yield
    _reset_persistent_files()
    _clear_singleton_memory()


@pytest.fixture(autouse=True)
def _isolated_knowledge_writes(monkeypatch, tmp_path):
    """测试期间把知识库写入重定向到临时路径（★T2795-5.1）。

    背景：多个测试（压测 / e2e / experience_learner）在验证工具时会真实写入
    生产知识库 `knowledge/knowledge_store.json`，每跑一次全量测试就留下
    数十条"[经验] xxx 成功"、"压力测试条目"、"并发模拟"之类脏数据。
    历史上已由 T2654 人工清理过一次，属复发缺陷。此处在全局层面根治：

      1. KnowledgeStore 模块级单例 `_store` → 临时库
      2. experience_learner 按文件路径直写，其 `KNOWLEDGE_DIR` → 临时目录

    只影响测试进程，不影响生产行为。
    """
    import tools.knowledge_store as _ks

    isolated = _ks.KnowledgeStore(path=tmp_path / "conftest_kb.json")
    monkeypatch.setattr(_ks, "_store", isolated, raising=False)

    try:
        import tools.experience_learner as _el
    except ImportError:
        _el = None
    if _el is not None and hasattr(_el, "KNOWLEDGE_DIR"):
        monkeypatch.setattr(_el, "KNOWLEDGE_DIR", tmp_path / "conftest_experience_kb")

    # monitor 单例同样直写生产文件，需一并隔离。
    # （由 gate.py G1 于 2026-10-30 捕获：3 个测试会把 memory/monitor_data.json 改写）
    try:
        import tools.monitor as _mon
    except ImportError:
        _mon = None
    if _mon is not None and hasattr(_mon, "_monitor"):
        monkeypatch.setattr(
            _mon, "_monitor", _mon.Monitor(path=tmp_path / "conftest_monitor.json")
        )

    return isolated
