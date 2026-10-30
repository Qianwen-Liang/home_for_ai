"""
Retry Policy 单元测试
"""
import sys
import os

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.retry_policy import (
    RetryPolicy, RetryConfig, RetryExhaustedError,
    with_retry_policy, compute_backoff,
)


# ── 测试：RetryConfig ─────────────────────────────────────


def test_default_config():
    """默认配置"""
    cfg = RetryConfig()
    assert cfg.max_retries == 3
    assert cfg.base_delay == 1.0
    assert cfg.max_delay == 60.0
    assert cfg.jitter is True
    assert cfg.jitter_style == "full"
    assert cfg.exponential is True
    print("✅ 测试1 默认配置: 通过")


def test_custom_config():
    """自定义配置"""
    cfg = RetryConfig(
        max_retries=5,
        base_delay=2.0,
        jitter_style="equal",
        exponential=False,
    )
    assert cfg.max_retries == 5
    assert cfg.base_delay == 2.0
    assert cfg.jitter_style == "equal"
    assert cfg.exponential is False
    print("✅ 测试2 自定义配置: 通过")


# ── 测试：RetryPolicy 构造 ────────────────────────────────


def test_retry_policy_init():
    """策略对象构造"""
    policy = RetryPolicy(max_retries=5, base_delay=2.0)
    assert policy.config.max_retries == 5
    assert policy.config.base_delay == 2.0
    print("✅ 测试3 策略构造: 通过")


# ── 测试：成功执行 ────────────────────────────────────────


def test_execute_success():
    """执行成功，不触发重试"""
    policy = RetryPolicy(max_retries=3)

    def good_func(x):
        return x * 2

    result = policy.execute(good_func, 21)
    assert result == 42
    stats = policy.stats()
    assert stats["total_attempts"] == 0  # 无重试
    print("✅ 测试4 执行成功: 通过")


# ── 测试：重试逻辑 ────────────────────────────────────────


def test_execute_retry_then_success():
    """前两次失败，第三次成功"""
    call_count = [0]

    def flaky_func():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError(f"尝试 {call_count[0]} 失败")
        return "ok"

    policy = RetryPolicy(
        max_retries=3,
        base_delay=0.01,
        max_delay=0.1,
        jitter=False,  # 测试中关闭随机
    )
    result = policy.execute(flaky_func)
    assert result == "ok"
    assert call_count[0] == 3
    stats = policy.stats()
    assert stats["total_attempts"] == 2  # 两次重试
    print("✅ 测试5 重试成功: 通过")


def test_execute_retry_exhausted():
    """所有重试耗尽"""
    policy = RetryPolicy(
        max_retries=2,
        base_delay=0.01,
        max_delay=0.1,
        jitter=False,
    )

    def always_fail():
        raise RuntimeError("永久失败")

    try:
        policy.execute(always_fail)
        assert False, "应抛出 RetryExhaustedError"
    except RetryExhaustedError as e:
        assert e.attempts == 3  # 1 次原始 + 2 次重试
        assert "永久失败" in str(e.last_error)

    stats = policy.stats()
    assert stats["total_attempts"] == 2
    print("✅ 测试6 重试耗尽: 通过")


def test_execute_zero_retries():
    """max_retries=0，不重试"""
    policy = RetryPolicy(max_retries=0, base_delay=0.01, jitter=False)

    call_count = [0]

    def fail_once():
        call_count[0] += 1
        raise ValueError("失败")

    try:
        policy.execute(fail_once)
        assert False
    except RetryExhaustedError:
        pass

    assert call_count[0] == 1  # 只调用一次
    print("✅ 测试7 零重试: 通过")


# ── 测试：异常过滤 ────────────────────────────────────────


def test_non_retryable_exception():
    """不可重试异常 → 立即抛出"""
    policy = RetryPolicy(
        max_retries=3,
        base_delay=0.01,
        jitter=False,
        non_retryable_exceptions=(ValueError,),
    )

    call_count = [0]

    def raise_value_error():
        call_count[0] += 1
        raise ValueError("不可重试")

    try:
        policy.execute(raise_value_error)
        assert False
    except ValueError:
        pass

    assert call_count[0] == 1  # 不重试
    print("✅ 测试8 不可重试异常: 通过")


def test_retryable_exception_only():
    """仅对指定异常重试"""
    policy = RetryPolicy(
        max_retries=2,
        base_delay=0.01,
        jitter=False,
        retryable_exceptions=(ValueError,),
    )

    call_count = [0]

    def raise_type_error():
        call_count[0] += 1
        raise TypeError("不可重试的类型错误")

    try:
        policy.execute(raise_type_error)
        assert False
    except TypeError:
        pass

    assert call_count[0] == 1  # TypeError 不在 retryable 中
    print("✅ 测试9 仅指定异常重试: 通过")


# ── 测试：回调钩子 ────────────────────────────────────────


def test_on_retry_callback():
    """重试时触发回调"""
    retry_info = []

    def on_retry(attempt, error, delay):
        retry_info.append((attempt, str(error), delay))

    policy = RetryPolicy(
        max_retries=2,
        base_delay=0.01,
        max_delay=0.1,
        jitter=False,
        on_retry=on_retry,
    )

    call_count = [0]

    def fail_then_succeed():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError("失败")
        return "ok"

    result = policy.execute(fail_then_succeed)
    assert result == "ok"
    assert len(retry_info) == 2  # 两次重试都触发回调
    print("✅ 测试10 回调钩子: 通过")


def test_on_retry_callback_exception():
    """回调异常不影响重试"""
    def bad_callback(attempt, error, delay):
        raise RuntimeError("回调出错")

    policy = RetryPolicy(
        max_retries=1,
        base_delay=0.01,
        jitter=False,
        on_retry=bad_callback,
    )

    call_count = [0]

    def fail_then_succeed():
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("第一次失败")
        return "ok"

    result = policy.execute(fail_then_succeed)
    assert result == "ok"
    print("✅ 测试11 回调异常容错: 通过")


# ── 测试：延迟计算 ────────────────────────────────────────


def test_compute_delay_exponential():
    """指数退避计算"""
    policy = RetryPolicy(base_delay=1.0, max_delay=60.0, jitter=False)

    d0 = policy._compute_delay(0)  # base * 2^0 = 1.0
    d1 = policy._compute_delay(1)  # base * 2^1 = 2.0
    d2 = policy._compute_delay(2)  # base * 2^2 = 4.0

    assert d0 == 1.0
    assert d1 == 2.0
    assert d2 == 4.0
    print("✅ 测试12 指数退避: 通过")


def test_compute_delay_linear():
    """线性退避"""
    policy = RetryPolicy(
        base_delay=1.0,
        max_delay=60.0,
        jitter=False,
        exponential=False,
    )

    d0 = policy._compute_delay(0)  # base * 1 = 1.0
    d1 = policy._compute_delay(1)  # base * 2 = 2.0
    d2 = policy._compute_delay(2)  # base * 3 = 3.0

    assert d0 == 1.0
    assert d1 == 2.0
    assert d2 == 3.0
    print("✅ 测试13 线性退避: 通过")


def test_compute_delay_capped():
    """延迟被 max_delay 截断"""
    policy = RetryPolicy(
        base_delay=10.0,
        max_delay=25.0,
        jitter=False,
    )

    d5 = policy._compute_delay(5)  # 10 * 2^5 = 320 → capped at 25
    assert d5 == 25.0
    print("✅ 测试14 延迟截断: 通过")


def test_compute_delay_jitter():
    """带抖动的延迟"""
    policy = RetryPolicy(base_delay=1.0, max_delay=60.0, jitter=True)

    for _ in range(20):
        d = policy._compute_delay(0)
        # full jitter: 0 <= d <= 1.0
        assert 0.0 <= d <= 1.0
    print("✅ 测试15 抖动范围: 通过")


def test_jitter_styles():
    """三种抖动风格"""
    # full
    p_full = RetryPolicy(base_delay=1.0, jitter=True, jitter_style="full")
    for _ in range(20):
        d = p_full._compute_delay(0)
        assert 0.0 <= d <= 1.0

    # equal
    p_equal = RetryPolicy(base_delay=1.0, jitter=True, jitter_style="equal")
    for _ in range(20):
        d = p_equal._compute_delay(0)
        assert 0.5 <= d <= 1.0  # half + random(0, half)

    # none
    p_none = RetryPolicy(base_delay=1.0, jitter=False, jitter_style="none")
    d = p_none._compute_delay(0)
    assert d == 1.0

    print("✅ 测试16 抖动风格: 通过")


# ── 测试：wrap ────────────────────────────────────────────


def test_wrap_phase_executor():
    """包装为 phase_executor"""
    policy = RetryPolicy(max_retries=2, base_delay=0.01, jitter=False)

    def my_executor(task_id, phase, params):
        return {"status": "done", "task_id": task_id, "phase": phase}

    wrapped = policy.wrap(my_executor)
    result = wrapped("T001", "分析", {"x": 1})
    assert result["status"] == "done"
    assert result["task_id"] == "T001"
    print("✅ 测试17 wrap: 通过")


def test_wrap_with_retry():
    """wrap 带重试"""
    call_count = [0]

    def flaky_executor(task_id, phase, params):
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("临时错误")
        return {"status": "done", "calls": call_count[0]}

    policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter=False)
    wrapped = policy.wrap(flaky_executor)
    result = wrapped("T001", "分析", {})
    assert result["status"] == "done"
    assert call_count[0] == 3
    print("✅ 测试18 wrap 重试: 通过")


# ── 测试：execute_phase ───────────────────────────────────


def test_execute_phase_with_func():
    """execute_phase 从 params 获取执行函数"""
    policy = RetryPolicy(max_retries=1, base_delay=0.01, jitter=False)

    def my_func(task_id, phase, params):
        return {"status": "done", "executed": True}

    result = policy.execute_phase("T001", "测试", {"_executor_func": my_func})
    assert result["status"] == "done"
    assert result["executed"] is True
    print("✅ 测试19 execute_phase: 通过")


def test_execute_phase_default():
    """execute_phase 无函数 → 模拟"""
    policy = RetryPolicy()
    result = policy.execute_phase("T001", "测试", {})
    assert result["status"] == "done"
    assert "模拟" in result.get("output", "")
    print("✅ 测试20 execute_phase 默认: 通过")


# ── 测试：装饰器 ──────────────────────────────────────────


def test_with_retry_decorator():
    """@with_retry_policy 装饰器"""
    call_count = [0]

    @with_retry_policy(max_retries=2, base_delay=0.01, jitter=False)
    def unreliable():
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("临时错误")
        return "success"

    result = unreliable()
    assert result == "success"
    assert call_count[0] == 3
    print("✅ 测试21 装饰器: 通过")


# ── 测试：compute_backoff 便捷函数 ────────────────────────


def test_compute_backoff_basic():
    """便捷退避计算"""
    d0 = compute_backoff(0, base_delay=1.0, jitter=False)
    d1 = compute_backoff(1, base_delay=1.0, jitter=False)
    d2 = compute_backoff(2, base_delay=1.0, jitter=False)

    assert d0 == 1.0
    assert d1 == 2.0
    assert d2 == 4.0
    print("✅ 测试22 compute_backoff: 通过")


# ── 测试：stats / reset ───────────────────────────────────


def test_stats_and_reset():
    """统计与重置"""
    policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter=False)

    call_count = [0]

    def fail_then_succeed():
        call_count[0] += 1
        if call_count[0] < 2:
            raise ValueError("失败")
        return "ok"

    policy.execute(fail_then_succeed)

    stats = policy.stats()
    assert stats["total_attempts"] == 1  # 一次重试
    assert stats["config"]["max_retries"] == 3

    policy.reset_stats()
    assert policy.stats()["total_attempts"] == 0
    print("✅ 测试23 统计重置: 通过")


# ── 测试：RetryExhaustedError ───────────────────────────


def test_retry_exhausted_error_attrs():
    """RetryExhaustedError 属性"""
    last = RuntimeError("原始错误")
    err = RetryExhaustedError(attempts=5, last_error=last, phase="分析")
    assert err.attempts == 5
    assert err.last_error is last
    assert err.phase == "分析"
    assert "5" in str(err)
    assert "分析" in str(err)
    print("✅ 测试24 RetryExhaustedError: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Retry Policy 单元测试")
    print("=" * 50)
    test_default_config()
    test_custom_config()
    test_retry_policy_init()
    test_execute_success()
    test_execute_retry_then_success()
    test_execute_retry_exhausted()
    test_execute_zero_retries()
    test_non_retryable_exception()
    test_retryable_exception_only()
    test_on_retry_callback()
    test_on_retry_callback_exception()
    test_compute_delay_exponential()
    test_compute_delay_linear()
    test_compute_delay_capped()
    test_compute_delay_jitter()
    test_jitter_styles()
    test_wrap_phase_executor()
    test_wrap_with_retry()
    test_execute_phase_with_func()
    test_execute_phase_default()
    test_with_retry_decorator()
    test_compute_backoff_basic()
    test_stats_and_reset()
    test_retry_exhausted_error_attrs()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
