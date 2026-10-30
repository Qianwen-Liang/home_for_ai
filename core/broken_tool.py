"""
broken_tool — 异常模拟工具（v2.0 补丁验证用）
==============================================
为 /test-error 命令提供可控的异常触发能力。
用于验证 Debugger 的异常捕获、诊断和自动修复链路。

模式说明：
  raise_error      — 抛出标准 RuntimeError，测试 Debugger 诊断链路
  silent_fail      — 返回错误字符串而非抛异常，测试静默失败检测
  custom_error_type — 抛出自定义 BrokenToolError，测试异常类型路由
  naked            — 不经过任何包装直接触发，测试最外层防护
"""

from __future__ import annotations


class BrokenToolError(RuntimeError):
    """broken_tool 专用异常类型，用于测试异常类型路由。"""


def execute_broken_tool(mode: str = "raise_error") -> str:
    if mode == "raise_error":
        raise RuntimeError(
            "BrokenTool: 模拟的工具运行时异常 "
            "(mode=raise_error, 应被 execute_model_tool_call 捕获)"
        )
    elif mode == "silent_fail":
        return (
            "⚠️ BrokenTool: 模拟的静默失败\n"
            "此模式下工具'成功'执行但返回了错误结果，"
            "不应触发异常捕获链路。"
        )
    elif mode == "custom_error_type":
        raise BrokenToolError(
            "BrokenTool: 模拟的自定义异常 "
            "(mode=custom_error_type, 测试 BrokenToolError 路由)"
        )
    elif mode == "naked":
        raise Exception("naked exception from broken_tool")
    else:
        return (
            f"BrokenTool: 未知模式 '{mode}'。"
            f"可用模式: raise_error, silent_fail, custom_error_type, naked"
        )
