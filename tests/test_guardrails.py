"""
Guardrails 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.guardrails import (
    validate_params, with_retry, get_param, safe_execute, GuardrailsError
)


def test_get_param():
    """测试安全参数获取"""
    # 基本获取
    assert get_param({"a": 1}, "a") == 1
    assert get_param({"a": 1}, "b") is None
    assert get_param({"a": 1}, "b", default=42) == 42
    print("✅ 测试1 get_param 基本: 通过")

    # 空值处理
    assert get_param({"a": ""}, "a", default="default") == "default"
    assert get_param({"a": None}, "a", default=99) == 99
    print("✅ 测试2 get_param 空值: 通过")

    # 类型转换
    assert get_param({"count": "5"}, "count", param_type=int) == 5
    assert get_param({"count": "abc"}, "count", default=0, param_type=int) == 0
    assert get_param({"flag": "True"}, "flag", param_type=str) == "True"
    print("✅ 测试3 get_param 类型转换: 通过")

    # 浮点数
    assert get_param({"ratio": "0.75"}, "ratio", param_type=float) == 0.75
    assert get_param({"ratio": "bad"}, "ratio", default=0.0, param_type=float) == 0.0
    print("✅ 测试4 get_param 浮点数: 通过")


def test_validate_params_required():
    """测试必填参数验证"""

    @validate_params(required=["name"])
    def my_tool(arguments):
        return f"OK: {arguments['name']}"

    # 正常
    result = my_tool(arguments={"name": "test"})
    assert "OK" in result, f"应返回OK: {result}"
    print("✅ 测试5 必填参数 正常: 通过")

    # 缺少
    result = my_tool(arguments={})
    assert "缺少必填参数" in result, f"应提示缺少: {result}"
    print("✅ 测试6 必填参数 缺少: 通过")

    # 空字符串
    result = my_tool(arguments={"name": ""})
    assert "缺少必填参数" in result, f"空字符串也应提示缺少: {result}"
    print("✅ 测试7 必填参数 空字符串: 通过")


def test_validate_params_types():
    """测试类型验证"""

    @validate_params(types={"count": int, "ratio": float})
    def my_tool(arguments):
        return f"count={arguments['count']}, ratio={arguments['ratio']}"

    # 正常
    result = my_tool(arguments={"count": 5, "ratio": 0.5})
    assert "count=5" in result, f"应正常: {result}"
    print("✅ 测试8 类型验证 正常: 通过")

    # 自动转换
    result = my_tool(arguments={"count": "3", "ratio": "0.8"})
    assert "count=3" in result, f"应自动转换: {result}"
    print("✅ 测试9 类型验证 自动转换: 通过")

    # 转换失败
    result = my_tool(arguments={"count": "abc", "ratio": 0.5})
    assert "类型错误" in result, f"应提示类型错误: {result}"
    print("✅ 测试10 类型验证 转换失败: 通过")


def test_validate_params_combined():
    """测试组合验证"""

    @validate_params(
        required=["action"],
        types={"max": int},
        allowed_values={"action": ["store", "get"]},
    )
    def my_tool(arguments):
        return f"OK: {arguments['action']}"

    # 全部正常
    result = my_tool(arguments={"action": "store", "max": 5})
    assert "OK" in result, f"应正常: {result}"
    print("✅ 测试11 组合验证 正常: 通过")

    # 值不在允许范围
    result = my_tool(arguments={"action": "delete"})
    assert "值无效" in result, f"应提示值无效: {result}"
    print("✅ 测试12 组合验证 无效值: 通过")

    # 缺必填 + 类型错误
    result = my_tool(arguments={"max": "abc"})
    assert "缺少必填参数" in result, f"应提示缺少必填: {result}"
    print("✅ 测试13 组合验证 缺字段: 通过")


def test_validate_params_min_length():
    """测试最小长度验证"""

    @validate_params(min_length={"name": 3})
    def my_tool(arguments):
        return f"OK: {arguments['name']}"

    result = my_tool(arguments={"name": "ab"})
    assert "长度不足" in result, f"应提示长度不足: {result}"
    print("✅ 测试14 最小长度: 通过")

    result = my_tool(arguments={"name": "abc"})
    assert "OK" in result, f"应正常: {result}"
    print("✅ 测试15 最小长度 正常: 通过")


def test_validate_params_non_dict():
    """测试非字典参数"""

    @validate_params(required=["name"])
    def my_tool(arguments):
        return "OK"

    result = my_tool("not_a_dict")
    assert "必须是字典" in result, f"应提示必须是字典: {result}"
    print("✅ 测试16 非字典参数: 通过")


def test_with_retry_success():
    """测试重试装饰器 - 成功情况"""
    call_count = [0]

    @with_retry(max_retries=2, retry_delay=0.01)
    def my_func():
        call_count[0] += 1
        return "success"

    result = my_func()
    assert result == "success"
    assert call_count[0] == 1, f"应只调用1次: {call_count[0]}"
    print("✅ 测试17 重试成功: 通过")


def test_with_retry_failure():
    """测试重试装饰器 - 失败后降级"""
    call_count = [0]

    @with_retry(max_retries=2, retry_delay=0.01, fallback_return="降级值")
    def my_func():
        call_count[0] += 1
        raise ValueError("always fail")

    result = my_func()
    assert "降级值" in result, f"应有降级: {result}"
    assert call_count[0] == 3, f"应调用3次(1+2重试): {call_count[0]}"
    print("✅ 测试18 重试失败降级: 通过")


def test_with_retry_error_string():
    """测试重试装饰器 - 函数返回错误字符串"""
    call_count = [0]

    @with_retry(max_retries=2, retry_delay=0.01)
    def my_func():
        call_count[0] += 1
        if call_count[0] < 3:
            return "错误：网络超时"
        return "success"

    result = my_func()
    assert "success" in result, f"重试后应成功: {result}"
    assert call_count[0] == 3
    print("✅ 测试19 错误字符串重试: 通过")


def test_with_retry_no_fallback():
    """测试重试装饰器 - 无降级"""
    call_count = [0]

    @with_retry(max_retries=1, retry_delay=0.01)
    def my_func():
        call_count[0] += 1
        raise RuntimeError("fail")

    result = my_func()
    assert "操作失败" in result, f"应有失败提示: {result}"
    assert "已重试" in result, f"应有重试次数: {result}"
    print("✅ 测试20 无降级重试: 通过")


def test_safe_execute():
    """测试安全执行包装器"""
    def risky_func(x):
        if x < 0:
            raise ValueError("负数不允许")
        return f"结果: {x}"

    safe = safe_execute(risky_func, error_prefix="计算失败")

    # 正常
    result = safe(5)
    assert "结果: 5" in result, f"应正常: {result}"
    print("✅ 测试21 safe_execute 正常: 通过")

    # 异常
    result = safe(-1)
    assert "计算失败" in result, f"应有错误前缀: {result}"
    assert "负数不允许" in result, f"应有异常信息: {result}"
    print("✅ 测试22 safe_execute 异常: 通过")


def test_guardrails_error():
    """测试自定义异常"""
    try:
        raise GuardrailsError("测试错误")
    except GuardrailsError as e:
        assert "测试错误" in str(e)
    print("✅ 测试23 自定义异常: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Guardrails 单元测试")
    print("=" * 50)
    test_get_param()
    print()
    test_validate_params_required()
    print()
    test_validate_params_types()
    print()
    test_validate_params_combined()
    print()
    test_validate_params_min_length()
    print()
    test_validate_params_non_dict()
    print()
    test_with_retry_success()
    print()
    test_with_retry_failure()
    print()
    test_with_retry_error_string()
    print()
    test_with_retry_no_fallback()
    print()
    test_safe_execute()
    print()
    test_guardrails_error()
    print()
    print("=" * 50)
    print("🎉 所有 Guardrails 测试通过！")
    print("=" * 50)
