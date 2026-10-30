"""
test_patched_exceptions — 异常补丁验证测试
=========================================
验证所有自定义异常类可正确导入，broken_tool 各模式行为正确。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXPECTED_ERRORS = [
    ("tools.runner", "RunnerError"),
    ("tools.calculator", "CalculationError"),
    ("tools.file_utils", "FileUtilsError"),
    ("tools.knowledge_store", "KnowledgeStoreError"),
    ("tools.task_tracker", "TaskTrackerError"),
    ("tools.test_runner", "TestRunnerError"),
    ("tools.monitor", "MonitorError"),
    ("tools.decision_engine", "DecisionError"),
    ("tools.safety_net", "SafetyNetError"),
    ("tools.web_search", "WebSearchError"),
    ("tools.offline_runner", "OfflineError"),
    ("tools.checkpoint_manager", "CheckpointError"),
]


def test_all_errors_importable():
    for mod, err in EXPECTED_ERRORS:
        m = __import__(mod, fromlist=[err])
        assert issubclass(getattr(m, err), Exception), f"{mod}.{err}"
        print(f"  ✅ {mod}.{err}")
    print("✅ test_all_errors_importable: 通过")


def test_broken_tool_error():
    from broken_tool import BrokenToolError
    assert issubclass(BrokenToolError, RuntimeError)
    try:
        raise BrokenToolError("test")
    except BrokenToolError:
        pass
    print("✅ test_broken_tool_error: 通过")


def test_broken_tool_modes():
    from broken_tool import execute_broken_tool, BrokenToolError
    try:
        execute_broken_tool("raise_error")
        assert False
    except RuntimeError:
        pass
    assert "静默失败" in execute_broken_tool("silent_fail")
    try:
        execute_broken_tool("custom_error_type")
        assert False
    except BrokenToolError:
        pass
    assert "未知模式" in execute_broken_tool("unknown")
    print("✅ test_broken_tool_modes: 通过")


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 异常补丁验证测试")
    print("=" * 60)
    passed = failed = 0
    for t in [test_all_errors_importable, test_broken_tool_error, test_broken_tool_modes]:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n📊 {passed}/{passed+failed} 通过")
    exit(1 if failed else 0)
