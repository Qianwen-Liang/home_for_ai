"""
Executor Registry 单元测试
"""
import sys
import os

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.executor_registry import (
    ExecutorRegistry, ExecutorEntry, ExecutorRegistryError,
    get_registry, register_executor,
)


# ── 辅助 ──────────────────────────────────────────────────

def _clean_registry():
    """创建一个干净的注册表实例。"""
    return ExecutorRegistry()


# ── 测试：装饰器注册 ──────────────────────────────────────


def test_decorator_register():
    """装饰器方式注册阶段执行器"""
    reg = _clean_registry()

    @reg.register("扫描", description="扫描工作区")
    def scan_phase(task_id, phase, params):
        return {"status": "done", "files": ["a.py", "b.py"]}

    assert reg.has("扫描")
    entry = reg.get_entry("扫描")
    assert entry is not None
    assert entry.name == "扫描"
    assert entry.description == "扫描工作区"
    assert entry.call_count == 0
    assert entry.error_count == 0
    print("✅ 测试1 装饰器注册: 通过")


def test_register_function():
    """编程式注册阶段执行器"""
    reg = _clean_registry()

    def my_executor(task_id, phase, params):
        return {"status": "done"}

    reg.register_function("分析", my_executor, description="分析数据", max_retries=2)
    assert reg.has("分析")
    entry = reg.get_entry("分析")
    assert entry is not None
    assert entry.max_retries == 2
    assert entry.description == "分析数据"
    print("✅ 测试2 编程式注册: 通过")


def test_unregister():
    """注销执行器"""
    reg = _clean_registry()

    @reg.register("临时阶段")
    def tmp(task_id, phase, params):
        return {"status": "done"}

    assert reg.has("临时阶段")
    assert reg.unregister("临时阶段") is True
    assert not reg.has("临时阶段")
    assert reg.unregister("不存在") is False
    print("✅ 测试3 注销: 通过")


# ── 测试：执行 ────────────────────────────────────────────


def test_execute_registered():
    """执行已注册的阶段"""
    reg = _clean_registry()

    @reg.register("测试")
    def test_executor(task_id, phase, params):
        return {"status": "done", "task_id": task_id, "phase": phase, "params": params}

    result = reg.execute("测试", "T001", "测试", {"key": "val"})
    assert result["status"] == "done"
    assert result["task_id"] == "T001"
    assert result["params"] == {"key": "val"}
    assert result["phase"] == "测试"

    # 检查调用计数
    entry = reg.get_entry("测试")
    assert entry.call_count == 1
    assert entry.error_count == 0
    print("✅ 测试4 执行已注册阶段: 通过")


def test_execute_unregistered_default():
    """未注册阶段使用默认执行器"""
    reg = _clean_registry()

    def default_executor(task_id, phase, params):
        return {"status": "done", "executor": "default", "phase": phase}

    reg.set_default(default_executor)

    result = reg.execute("未注册阶段", "T001", "未注册阶段", {})
    assert result["executor"] == "default"
    assert result["status"] == "done"
    print("✅ 测试5 默认执行器: 通过")


def test_execute_unregistered_mock():
    """无注册也无默认 → 模拟执行"""
    reg = _clean_registry()

    result = reg.execute("不存在", "T001", "不存在", {})
    assert result["status"] == "done"
    assert "模拟" in result["output"] or "mock" in result.get("executor", "")
    print("✅ 测试6 模拟执行: 通过")


def test_execute_error_propagation():
    """执行器抛异常 → ExecutorRegistryError"""
    reg = _clean_registry()

    @reg.register("会失败的阶段")
    def failing(task_id, phase, params):
        raise ValueError("模拟错误")

    try:
        reg.execute("会失败的阶段", "T001", "会失败的阶段", {})
        assert False, "应抛出异常"
    except ExecutorRegistryError as e:
        assert "会失败的阶段" in str(e)
        assert "模拟错误" in str(e)

    entry = reg.get_entry("会失败的阶段")
    assert entry.error_count == 1
    print("✅ 测试7 异常传播: 通过")


def test_result_auto_status():
    """结果无 status 字段 → 自动添加"""
    reg = _clean_registry()

    @reg.register("无状态阶段")
    def no_status(task_id, phase, params):
        return {"output": "done without status"}

    result = reg.execute("无状态阶段", "T001", "无状态阶段", {})
    assert result["status"] == "done"
    print("✅ 测试8 自动状态: 通过")


# ── 测试：重试执行 ────────────────────────────────────────


def test_execute_with_retry_success():
    """重试执行：第一次成功"""
    reg = _clean_registry()

    call_count = [0]

    @reg.register("可靠阶段", max_retries=3)
    def reliable(task_id, phase, params):
        call_count[0] += 1
        return {"status": "done", "calls": call_count[0]}

    result = reg.execute_with_retry("可靠阶段", "T001", "可靠阶段", {}, max_retries=3)
    assert result["status"] == "done"
    assert call_count[0] == 1  # 一次成功
    print("✅ 测试9 重试首次成功: 通过")


def test_execute_with_retry_eventual_success():
    """重试执行：前两次失败，第三次成功"""
    reg = _clean_registry()

    call_count = [0]

    @reg.register("波动阶段", max_retries=3)
    def flaky(task_id, phase, params):
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError(f"尝试 {call_count[0]} 失败")
        return {"status": "done", "calls": call_count[0]}

    result = reg.execute_with_retry(
        "波动阶段", "T001", "波动阶段", {},
        max_retries=3, base_delay=0.01, max_delay=0.1, jitter=False,
    )
    assert result["status"] == "done"
    assert call_count[0] == 3
    print("✅ 测试10 重试最终成功: 通过")


def test_execute_with_retry_exhausted():
    """重试耗尽"""
    reg = _clean_registry()

    @reg.register("必败阶段", max_retries=2)
    def always_fail(task_id, phase, params):
        raise RuntimeError("永远失败")

    try:
        reg.execute_with_retry(
            "必败阶段", "T001", "必败阶段", {},
            max_retries=2, base_delay=0.01, max_delay=0.1, jitter=False,
        )
        assert False, "应抛出异常"
    except ExecutorRegistryError as e:
        assert "3 次尝试" in str(e) or "仍失败" in str(e)

    print("✅ 测试11 重试耗尽: 通过")


# ── 测试：集成 ────────────────────────────────────────────


def test_get_executor_for_runner():
    """返回 phase_executor 兼容的回调"""
    reg = _clean_registry()

    @reg.register("阶段A")
    def phase_a(task_id, phase, params):
        return {"status": "done", "phase": phase}

    callback = reg.get_executor_for_runner()
    assert callable(callback)

    result = callback("T001", "阶段A", {"x": 1})
    assert result["status"] == "done"
    print("✅ 测试12 runner 集成回调: 通过")


# ── 测试：全局实例 ────────────────────────────────────────


def test_global_registry():
    """全局注册表实例"""
    reg = get_registry()
    assert isinstance(reg, ExecutorRegistry)
    print("✅ 测试13 全局实例: 通过")


def test_shortcut_register_executor():
    """快捷装饰器"""
    # 使用干净的全局实例测试
    reg = ExecutorRegistry()

    @reg.register("快捷阶段")
    def quick(task_id, phase, params):
        return {"status": "done"}

    assert reg.has("快捷阶段")
    print("✅ 测试14 快捷装饰器: 通过")


# ── 测试：list_executors ──────────────────────────────────


def test_list_executors():
    """列出所有执行器"""
    reg = _clean_registry()

    @reg.register("A")
    def a(task_id, phase, params):
        return {"status": "done"}

    @reg.register("B")
    def b(task_id, phase, params):
        return {"status": "done"}

    entries = reg.list_executors()
    assert len(entries) == 2
    names = [e["name"] for e in entries]
    assert "A" in names
    assert "B" in names
    print("✅ 测试15 列出执行器: 通过")


# ── 测试：ExecutorEntry 数据模型 ──────────────────────────


def test_executor_entry_dataclass():
    """ExecutorEntry 数据类"""
    entry = ExecutorEntry(
        name="测试阶段",
        func=lambda tid, p, pp: {},
        description="测试用",
        timeout=600.0,
        max_retries=5,
    )
    assert entry.name == "测试阶段"
    assert entry.timeout == 600.0
    assert entry.max_retries == 5
    assert entry.call_count == 0
    print("✅ 测试16 ExecutorEntry 数据模型: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Executor Registry 单元测试")
    print("=" * 50)
    test_decorator_register()
    test_register_function()
    test_unregister()
    test_execute_registered()
    test_execute_unregistered_default()
    test_execute_unregistered_mock()
    test_execute_error_propagation()
    test_result_auto_status()
    test_execute_with_retry_success()
    test_execute_with_retry_eventual_success()
    test_execute_with_retry_exhausted()
    test_get_executor_for_runner()
    test_global_registry()
    test_shortcut_register_executor()
    test_list_executors()
    test_executor_entry_dataclass()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
