"""
test_debugger_capture — Debugger 异常捕获链路测试
================================================
验证 Debugger 在真实异常场景下的捕获、诊断和修复能力。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.specialist_base import DebuggerAgent, TaskInput


def test_capture_runtime_error():
    debugger = DebuggerAgent()
    task = TaskInput(task_id="T1", description="RuntimeError",
                     params={"action": "diagnose", "error": "RuntimeError: 模拟异常"})
    result = debugger.process_task(task)
    assert result.status == "done"
    print("✅ test_capture_runtime_error: 通过")


def test_capture_custom_error():
    debugger = DebuggerAgent()
    task = TaskInput(task_id="T2", description="BrokenToolError",
                     params={"action": "diagnose", "error": "BrokenToolError: 自定义异常"})
    result = debugger.process_task(task)
    assert result.status == "done"
    print("✅ test_capture_custom_error: 通过")


def test_capture_chain():
    debugger = DebuggerAgent()
    # 诊断
    r = debugger.process_task(TaskInput(task_id="T3", description="timeout",
        params={"action": "diagnose", "error": "Read timed out"}))
    assert r.status == "done"
    assert r.output.get("diagnosis", {}).get("category") == "network"
    # 修复
    r = debugger.process_task(TaskInput(task_id="T4", description="fix",
        params={"action": "auto_fix", "error": "Read timed out"}))
    assert r.status == "done"
    # 快照
    r = debugger.process_task(TaskInput(task_id="T5", description="snap",
        params={"action": "snapshot", "error": "链路测试"}))
    assert r.status == "done"
    # 健康检查
    r = debugger.process_task(TaskInput(task_id="T6", description="health",
        params={"action": "health_check"}))
    assert r.status == "done"
    print("✅ test_capture_chain: 通过")


if __name__ == "__main__":
    print("=" * 60)
    print("🐛 Debugger 异常捕获链路测试")
    print("=" * 60)
    passed = failed = 0
    for test in [test_capture_runtime_error, test_capture_custom_error, test_capture_chain]:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"❌ {test.__name__}: {exc}")
            failed += 1
    print(f"\n📊 {passed}/{passed+failed} 通过")
    exit(1 if failed else 0)
