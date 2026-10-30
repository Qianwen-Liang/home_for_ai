"""
executor_registry — 阶段执行器注册表（v1.0）
============================================
受 LangGraph Activity 模式和 Temporal.io Activity 注册机制启发，
为离线任务提供"可注册阶段执行函数"的能力。

核心设计：
  - 注册表模式：将阶段名称映射到可调用执行函数
  - 装饰器注册：@register("阶段名") 一键注册
  - 延迟绑定：执行时根据阶段名动态查找执行器
  - 默认执行器：未注册的阶段使用默认模拟执行

与 LangGraph Activity 的对应关系：
  LangGraph:  @workflow.activity → workflow.execute_activity(name, args)
  本模块:    @registry.register("phase") → registry.execute(phase, context)

与 offline_runner 的集成：
  runner.execute(task_id, phase_executor=registry.get_executor())

使用方式：
  registry = ExecutorRegistry()

  @registry.register("扫描")
  def scan_phase(task_id: str, phase: str, params: dict) -> dict:
      return {"files": [...], "status": "done"}

  @registry.register("分析")
  def analyze_phase(task_id: str, phase: str, params: dict) -> dict:
      return {"summary": "...", "status": "done"}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .checkpoint_manager import CheckpointManager

SANDBOX_DIR = Path(__file__).resolve().parent.parent
REGISTRY_DIR = SANDBOX_DIR / "memory" / "executors"


# ── 类型定义 ──────────────────────────────────────────────

# 阶段执行器签名: (task_id, phase, params) -> result_dict
PhaseExecutor = Callable[[str, str, dict[str, Any]], dict[str, Any]]


# ── 错误类型 ──────────────────────────────────────────────


class ExecutorRegistryError(RuntimeError):
    """执行器注册表错误。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ExecutorEntry:
    """执行器条目。"""
    name: str
    func: PhaseExecutor
    description: str = ""
    timeout: float = 300.0          # 默认超时 5 分钟
    max_retries: int = 0            # 默认不重试
    registered_at: str = ""
    call_count: int = 0
    error_count: int = 0
    last_duration: float = 0.0


# ── 执行器注册表 ──────────────────────────────────────────


class ExecutorRegistry:
    """
    阶段执行器注册表。
    
    管理离线任务各阶段的执行函数注册、查找和调用。
    支持装饰器注册和编程式注册两种方式。
    """

    def __init__(self) -> None:
        self._executors: dict[str, ExecutorEntry] = {}
        self._default_executor: PhaseExecutor | None = None

    # ── 注册 API ──────────────────────────────────────────

    def register(
        self,
        name: str,
        description: str = "",
        timeout: float = 300.0,
        max_retries: int = 0,
    ):
        """
        装饰器方式注册阶段执行器。
        
        用法:
            registry = ExecutorRegistry()
            
            @registry.register("扫描", description="扫描工作区文件")
            def scan_phase(task_id, phase, params):
                return {"files": [...], "status": "done"}
        
        Args:
            name: 阶段名称（与离线任务的 phases 列表中的名称匹配）
            description: 阶段描述
            timeout: 超时秒数（预留，当前未强制执行）
            max_retries: 该阶段的最大重试次数（0 = 不重试）
        """
        def decorator(func: PhaseExecutor) -> PhaseExecutor:
            self._executors[name] = ExecutorEntry(
                name=name,
                func=func,
                description=description,
                timeout=timeout,
                max_retries=max_retries,
                registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return func
        return decorator

    def register_function(
        self,
        name: str,
        func: PhaseExecutor,
        description: str = "",
        timeout: float = 300.0,
        max_retries: int = 0,
    ) -> None:
        """
        编程式注册阶段执行器（非装饰器方式）。
        
        Args:
            name: 阶段名称
            func: 执行函数
            description: 阶段描述
            timeout: 超时秒数
            max_retries: 最大重试次数
        """
        self._executors[name] = ExecutorEntry(
            name=name,
            func=func,
            description=description,
            timeout=timeout,
            max_retries=max_retries,
            registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def set_default(self, func: PhaseExecutor) -> None:
        """
        设置默认执行器（未注册阶段使用）。
        
        Args:
            func: 默认执行函数
        """
        self._default_executor = func

    def unregister(self, name: str) -> bool:
        """
        注销一个阶段执行器。
        
        Returns:
            是否成功注销（False 表示该阶段未注册）
        """
        if name in self._executors:
            del self._executors[name]
            return True
        return False

    # ── 查询 API ──────────────────────────────────────────

    def get(self, name: str) -> PhaseExecutor | None:
        """
        获取阶段执行器函数。
        
        Args:
            name: 阶段名称
        
        Returns:
            执行函数，如果未注册且无默认执行器则返回 None
        """
        entry = self._executors.get(name)
        if entry:
            return entry.func
        return self._default_executor

    def get_entry(self, name: str) -> ExecutorEntry | None:
        """获取执行器条目（含元数据）。"""
        return self._executors.get(name)

    def has(self, name: str) -> bool:
        """检查阶段是否已注册。"""
        return name in self._executors

    def list_executors(self) -> list[dict[str, Any]]:
        """列出所有已注册的执行器。"""
        return [
            {
                "name": entry.name,
                "description": entry.description,
                "timeout": entry.timeout,
                "max_retries": entry.max_retries,
                "registered_at": entry.registered_at,
                "call_count": entry.call_count,
                "error_count": entry.error_count,
                "last_duration": entry.last_duration,
            }
            for entry in sorted(self._executors.values(), key=lambda e: e.name)
        ]

    # ── 执行 API ──────────────────────────────────────────

    def execute(
        self,
        name: str,
        task_id: str,
        phase: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行一个阶段。
        
        查找名为 name 的执行器，调用它并记录指标。
        如果未找到，尝试默认执行器。如果都没有，返回模拟结果。
        
        Args:
            name: 阶段名称
            task_id: 任务 ID
            phase: 阶段名称（可能与 name 相同，传递给执行器）
            params: 任务参数
        
        Returns:
            执行结果字典
        
        Raises:
            ExecutorRegistryError: 执行器抛出异常时
        """
        executor = self.get(name)

        if executor is None:
            # 无注册执行器，返回模拟结果
            return {
                "phase": phase,
                "status": "done",
                "output": f"[模拟] 阶段 '{name}' 完成（无注册执行器）",
                "executor": "builtin.mock",
            }

        entry = self._executors.get(name)
        start_time = time.time()

        try:
            result = executor(task_id, phase, params)
            duration = time.time() - start_time

            if entry:
                entry.call_count += 1
                entry.last_duration = duration

            # 确保结果包含 status 字段
            if isinstance(result, dict) and "status" not in result:
                result["status"] = "done"

            return result

        except Exception as exc:
            duration = time.time() - start_time

            if entry:
                entry.error_count += 1
                entry.last_duration = duration

            raise ExecutorRegistryError(
                f"阶段 '{name}' 执行失败（耗时 {duration:.2f}s）: {exc}"
            ) from exc

    def execute_with_retry(
        self,
        name: str,
        task_id: str,
        phase: str,
        params: dict[str, Any],
        max_retries: int | None = None,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> dict[str, Any]:
        """
        带指数退避重试的阶段执行。
        
        Args:
            name: 阶段名称
            task_id: 任务 ID
            phase: 阶段名称
            params: 任务参数
            max_retries: 最大重试次数（None = 使用注册时的配置，0 = 不重试）
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            jitter: 是否添加随机抖动
        
        Returns:
            执行结果字典
        
        Raises:
            ExecutorRegistryError: 所有重试都失败时
        """
        entry = self._executors.get(name)
        retries = max_retries if max_retries is not None else (entry.max_retries if entry else 0)

        last_error = None
        for attempt in range(retries + 1):
            try:
                return self.execute(name, task_id, phase, params)
            except ExecutorRegistryError as exc:
                last_error = exc
                if attempt < retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        import random
                        delay = delay * (0.5 + random.random())
                    time.sleep(delay)
                    continue
                break

        raise ExecutorRegistryError(
            f"阶段 '{name}' 在 {retries + 1} 次尝试后仍失败: {last_error}"
        )

    # ── 集成方法 ──────────────────────────────────────────

    def get_executor_for_runner(self) -> Callable[[str, str, dict[str, Any]], dict[str, Any]]:
        """
        返回一个符合 offline_runner phase_executor 签名的回调函数。
        
        用法:
            registry = ExecutorRegistry()
            # ... 注册阶段 ...
            runner.execute(task_id, phase_executor=registry.get_executor_for_runner())
        
        Returns:
            (task_id, phase, params) -> result_dict 的回调
        
        注意：回调签名是 (task_id, phase, params)，会自动用 phase 作为
        阶段名称去注册表中查找执行器。
        """
        def _executor(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
            return self.execute(phase, task_id, phase, params)

        return _executor


# ── 全局实例 ──────────────────────────────────────────────

_registry = ExecutorRegistry()


def get_registry() -> ExecutorRegistry:
    """获取全局执行器注册表实例。"""
    return _registry


# ── 快捷注册函数 ──────────────────────────────────────────


def register_executor(
    name: str,
    description: str = "",
    timeout: float = 300.0,
    max_retries: int = 0,
):
    """
    快捷装饰器：向全局注册表注册阶段执行器。
    
    用法:
        from tools.executor_registry import register_executor
        
        @register_executor("扫描", description="扫描工作区")
        def scan_phase(task_id, phase, params):
            return {"files": [...], "status": "done"}
    """
    return _registry.register(
        name=name,
        description=description,
        timeout=timeout,
        max_retries=max_retries,
    )
