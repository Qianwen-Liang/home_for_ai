"""
guardrails — 参数护栏与错误恢复工具（v1.0）
===========================================
受 Pydantic AI 启发，为工具系统提供轻量级的参数验证和错误恢复机制。

核心功能：
1. 参数验证装饰器：@validate_params 自动检查参数类型和必填字段
2. 错误恢复装饰器：@with_retry 自动重试和降级
3. 安全的参数获取：get_param() 带默认值和类型转换

全部使用 Python 标准库实现，无需安装第三方依赖。
"""

from __future__ import annotations

import functools
import time
import traceback
from typing import Any, Callable


# ── 错误类型 ──────────────────────────────────────────────


class GuardrailsError(RuntimeError):
    """参数验证或错误恢复失败。"""


# ── 参数验证 ──────────────────────────────────────────────


def validate_params(
    required: list[str] | None = None,
    types: dict[str, type] | None = None,
    min_length: dict[str, int] | None = None,
    allowed_values: dict[str, list[Any]] | None = None,
):
    """
    参数验证装饰器。
    
    用法:
        @validate_params(
            required=["name", "value"],
            types={"count": int, "ratio": float},
            min_length={"name": 1},
            allowed_values={"action": ["store", "get"]}
        )
        def my_tool(arguments: dict[str, Any]) -> str:
            ...
    
    Args:
        required: 必填参数列表
        types: 参数名 → 期望类型 的映射
        min_length: 参数名 → 最小长度 的映射（用于字符串）
        allowed_values: 参数名 → 允许值列表 的映射
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> str:
            # 获取 arguments 字典
            arguments = kwargs.get("arguments", {})
            if not arguments and args:
                # 位置参数：第一个参数应是 arguments 字典
                if isinstance(args[0], dict):
                    arguments = args[0]
                else:
                    return "❌ 参数验证失败: arguments 必须是字典"

            if not isinstance(arguments, dict):
                return "❌ 参数验证失败: arguments 必须是字典"

            errors: list[str] = []

            # 1. 检查必填字段
            if required:
                for field in required:
                    if field not in arguments or arguments[field] in (None, ""):
                        errors.append(f"缺少必填参数: '{field}'")

            # 2. 检查类型
            if types:
                for field, expected_type in types.items():
                    if field in arguments and arguments[field] is not None:
                        value = arguments[field]
                        if not isinstance(value, expected_type):
                            # 尝试类型转换
                            try:
                                converted = expected_type(value)
                                arguments[field] = converted
                            except (ValueError, TypeError):
                                errors.append(
                                    f"参数 '{field}' 类型错误: "
                                    f"期望 {expected_type.__name__}, "
                                    f"实际 {type(value).__name__}"
                                )

            # 3. 检查最小长度
            if min_length:
                for field, min_len in min_length.items():
                    if field in arguments and isinstance(arguments[field], str):
                        if len(arguments[field].strip()) < min_len:
                            errors.append(
                                f"参数 '{field}' 长度不足: "
                                f"最少 {min_len} 个字符"
                            )

            # 4. 检查允许值
            if allowed_values:
                for field, values in allowed_values.items():
                    if field in arguments and arguments[field] not in values:
                        values_str = ", ".join(f"'{v}'" for v in values)
                        errors.append(
                            f"参数 '{field}' 值无效: "
                            f"'{arguments[field]}', "
                            f"允许值: [{values_str}]"
                        )

            if errors:
                return "❌ " + "\n   ".join(errors)

            return func(*args, **kwargs)

        return wrapper
    return decorator


# ── 错误恢复 ──────────────────────────────────────────────


def with_retry(
    max_retries: int = 2,
    retry_delay: float = 0.5,
    fallback_return: str = "",
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """
    错误恢复装饰器：自动重试 + 降级。
    
    用法:
        @with_retry(max_retries=2, retry_delay=1.0)
        def risky_operation() -> str:
            ...
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
        fallback_return: 所有重试失败后的降级返回值
        retryable_exceptions: 可重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> str:
            last_error = ""
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    # 如果函数本身返回了错误字符串（非异常），也尝试重试
                    if isinstance(result, str) and result.startswith("错误：") and attempt < max_retries:
                        last_error = result
                        time.sleep(retry_delay)
                        continue
                    return result
                except retryable_exceptions as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        continue
                    break

            # 所有重试都失败
            error_msg = (
                f"⚠️ 操作失败（已重试 {max_retries} 次）\n"
                f"  最后错误: {last_error}"
            )
            
            if fallback_return:
                return f"{error_msg}\n  降级处理: {fallback_return}"
            
            return error_msg

        return wrapper
    return decorator


# ── 安全参数获取 ──────────────────────────────────────────


def get_param(
    arguments: dict[str, Any],
    name: str,
    default: Any = None,
    param_type: type | None = None,
) -> Any:
    """
    安全地从参数字典中获取值。
    
    用法:
        count = get_param(arguments, "count", default=0, param_type=int)
    
    Args:
        arguments: 参数字典
        name: 参数名
        default: 默认值
        param_type: 期望的类型（会自动转换）
    
    Returns:
        参数值，或默认值（如果不存在或转换失败）
    """
    value = arguments.get(name, default)
    
    if value is None or value == "":
        return default
    
    if param_type is not None and not isinstance(value, param_type):
        try:
            value = param_type(value)
        except (ValueError, TypeError):
            return default
    
    return value


# ── 安全异常包装 ──────────────────────────────────────────


def safe_execute(
    func: Callable,
    error_prefix: str = "操作失败",
    return_str: bool = True,
) -> Callable:
    """
    将函数包装为安全执行版本，捕获所有异常并返回友好错误信息。
    
    用法:
        safe_func = safe_execute(my_risky_function, error_prefix="搜索失败")
        result = safe_func(arguments)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> str:
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as exc:
            error_detail = traceback.format_exc() if __debug__ else str(exc)
            return f"❌ {error_prefix}: {exc}"
    
    return wrapper


# ── 工具入口（供其他模块使用） ─────────────────────────────

# 这些函数可以被其他工具模块导入和使用
__all__ = [
    "validate_params",
    "with_retry",
    "get_param",
    "safe_execute",
    "GuardrailsError",
]
