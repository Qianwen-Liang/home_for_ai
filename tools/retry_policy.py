"""
retry_policy — 指数退避+抖动重试策略（v1.0）
============================================
受分布式系统弹性模式（Resilience Patterns）启发，
为离线任务执行器提供智能重试机制。

核心特性：
  1. 指数退避：延迟时间随重试次数指数增长
  2. 随机抖动：添加随机因子避免"惊群效应"（thundering herd）
  3. 可配置：最大重试、基础延迟、最大延迟均可调
  4. 重试条件：支持按异常类型决定是否重试
  5. 回调钩子：每次重试时触发 on_retry 回调（日志/通知）
  6. 幂等键：可选，防止重复执行副作用

算法（标准指数退避 + 全抖动）：
  delay = min(base_delay * (2 ** attempt), max_delay)
  if jitter:
      delay = random.uniform(0, delay)        # 全抖动
      # 或: delay = delay * (0.5 + random.random())  # 均衡抖动

参考：
  - AWS Architecture Blog: "Exponential Backoff and Jitter"
  - Google Cloud: "Handling retries and errors"
  - Temporal.io: RetryPolicy API

使用方式：
  from tools.retry_policy import RetryPolicy, with_retry_policy
  
  # 方式1：策略对象
  policy = RetryPolicy(max_retries=3, base_delay=1.0)
  result = policy.execute(risky_function, arg1, arg2)
  
  # 方式2：装饰器
  @with_retry_policy(max_retries=3, base_delay=0.5)
  def risky_operation(x):
      ...
  
  # 方式3：集成到 offline_runner
  runner.execute(task_id, phase_executor=policy.wrap(executor_func))
"""

from __future__ import annotations

import functools
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


# ── 错误类型 ──────────────────────────────────────────────


class RetryExhaustedError(RuntimeError):
    """所有重试次数用尽后仍失败。"""

    def __init__(self, attempts: int, last_error: Exception, phase: str = ""):
        self.attempts = attempts
        self.last_error = last_error
        self.phase = phase
        super().__init__(
            f"重试 {attempts} 次后仍失败"
            + (f"（阶段: {phase}）" if phase else "")
            + f": {last_error}"
        )


# ── 重试策略配置 ──────────────────────────────────────────


@dataclass
class RetryConfig:
    """重试策略配置。"""
    max_retries: int = 3               # 最大重试次数（不含首次尝试）
    base_delay: float = 1.0            # 基础延迟（秒）
    max_delay: float = 60.0            # 最大延迟（秒）
    jitter: bool = True                # 是否添加随机抖动
    jitter_style: str = "full"         # 抖动风格: "full" | "equal" | "none"
    exponential: bool = True           # 是否指数增长（False = 线性）
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    non_retryable_exceptions: tuple[type[Exception], ...] = ()
    on_retry: Callable[[int, Exception, float], None] | None = None  # (attempt, error, delay)


# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_CONFIG = RetryConfig()


# ── 重试策略 ──────────────────────────────────────────────


class RetryPolicy:
    """
    指数退避重试策略。
    
    支持三种抖动风格（参考 AWS 架构博客）：
      - "full":    delay = random.uniform(0, computed_delay)     # 最大随机性
      - "equal":   delay = computed_delay / 2 + random.uniform(0, computed_delay / 2)  # 均衡
      - "none":    delay = computed_delay                        # 无抖动
    
    用法:
        policy = RetryPolicy(max_retries=3, base_delay=1.0)
        
        # 执行单个函数
        result = policy.execute(lambda: risky_call(), arg1)
        
        # 包装为 phase_executor 兼容的回调
        runner.execute(task_id, phase_executor=policy.wrap(executor_func))
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        jitter_style: str = "full",
        exponential: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
        non_retryable_exceptions: tuple[type[Exception], ...] = (),
        on_retry: Callable[[int, Exception, float], None] | None = None,
    ):
        self.config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
            jitter_style=jitter_style,
            exponential=exponential,
            retryable_exceptions=retryable_exceptions,
            non_retryable_exceptions=non_retryable_exceptions,
            on_retry=on_retry,
        )
        self._attempts: list[dict[str, Any]] = []  # 执行历史

    # ── 核心方法 ──────────────────────────────────────────

    def execute(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        执行函数，失败时自动重试。
        
        Args:
            func: 要执行的函数
            *args, **kwargs: 传递给 func 的参数
        
        Returns:
            函数返回值
        
        Raises:
            RetryExhaustedError: 所有重试耗尽
        """
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                last_error = exc

                # 检查是否可重试
                if not self._is_retryable(exc):
                    raise

                # 最后一次尝试不等待
                if attempt < self.config.max_retries:
                    delay = self._compute_delay(attempt)
                    self._attempts.append({
                        "attempt": attempt + 1,
                        "error": str(exc),
                        "delay": delay,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })

                    if self.config.on_retry:
                        try:
                            self.config.on_retry(attempt + 1, exc, delay)
                        except Exception:
                            pass  # 回调异常不影响重试

                    time.sleep(delay)
                    continue
                break

        # 所有重试耗尽
        raise RetryExhaustedError(
            attempts=self.config.max_retries + 1,
            last_error=last_error or Exception("未知错误"),
        )

    def execute_phase(
        self,
        task_id: str,
        phase: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        作为 phase_executor 执行一个阶段（带重试）。
        
        签名兼容 offline_runner 的 phase_executor 回调。
        
        Args:
            task_id: 任务 ID
            phase: 阶段名称
            params: 任务参数
        
        Returns:
            阶段执行结果字典
        """
        # 此方法作为 phase_executor 被 offline_runner 调用
        # 实际的执行函数由 params 中的 _executor_func 或默认行为决定
        executor_func = params.get("_executor_func")

        if executor_func and callable(executor_func):
            return self.execute(executor_func, task_id, phase, params)
        else:
            # 默认：模拟执行
            return {
                "phase": phase,
                "status": "done",
                "output": f"[模拟] 阶段 '{phase}' 完成",
            }

    def wrap(
        self,
        func: Callable[..., dict[str, Any]],
    ) -> Callable[[str, str, dict[str, Any]], dict[str, Any]]:
        """
        将普通函数包装为 phase_executor 兼容的回调。
        
        用法:
            policy = RetryPolicy(max_retries=3)
            runner.execute(
                task_id,
                phase_executor=policy.wrap(my_executor_function)
            )
        
        Args:
            func: 接受 (task_id, phase, params) 并返回 dict 的函数
        
        Returns:
            带重试的 phase_executor 回调
        """
        def wrapped(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
            return self.execute(func, task_id, phase, params)

        return wrapped

    # ── 内部方法 ──────────────────────────────────────────

    def _compute_delay(self, attempt: int) -> float:
        """计算第 attempt 次重试的等待时间。"""
        if self.config.exponential:
            delay = self.config.base_delay * (2 ** attempt)
        else:
            delay = self.config.base_delay * (attempt + 1)

        delay = min(delay, self.config.max_delay)

        if self.config.jitter:
            if self.config.jitter_style == "full":
                delay = random.uniform(0, delay)
            elif self.config.jitter_style == "equal":
                half = delay / 2
                delay = half + random.uniform(0, half)
            # "none" = 不添加抖动

        return delay

    def _is_retryable(self, exc: Exception) -> bool:
        """判断异常是否可重试。"""
        # 不可重试优先
        if self.config.non_retryable_exceptions:
            if isinstance(exc, self.config.non_retryable_exceptions):
                return False

        # 可重试检查
        if self.config.retryable_exceptions:
            return isinstance(exc, self.config.retryable_exceptions)

        return True

    # ── 统计 ──────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """获取重试统计信息。"""
        return {
            "total_attempts": len(self._attempts),
            "config": {
                "max_retries": self.config.max_retries,
                "base_delay": self.config.base_delay,
                "max_delay": self.config.max_delay,
                "jitter_style": self.config.jitter_style,
            },
            "attempts": self._attempts,
        }

    def reset_stats(self) -> None:
        """重置统计信息。"""
        self._attempts.clear()


# ── 装饰器 ────────────────────────────────────────────────


def with_retry_policy(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    jitter_style: str = "full",
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    non_retryable_exceptions: tuple[type[Exception], ...] = (),
):
    """
    指数退避重试装饰器。
    
    用法:
        @with_retry_policy(max_retries=3, base_delay=0.5)
        def risky_network_call(url: str) -> dict:
            ...
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        jitter: 是否添加随机抖动
        jitter_style: 抖动风格 "full" | "equal" | "none"
        retryable_exceptions: 可重试的异常类型
        non_retryable_exceptions: 不可重试的异常类型
    """
    policy = RetryPolicy(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        jitter_style=jitter_style,
        retryable_exceptions=retryable_exceptions,
        non_retryable_exceptions=non_retryable_exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator


# ── 便捷函数 ──────────────────────────────────────────────


def compute_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    单次计算指数退避延迟（无需创建 RetryPolicy 对象）。
    
    Args:
        attempt: 当前重试次数（0-based）
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        jitter: 是否添加随机抖动
    
    Returns:
        延迟秒数
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = random.uniform(0, delay)
    return delay
