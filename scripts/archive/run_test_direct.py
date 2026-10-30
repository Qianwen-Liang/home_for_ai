"""
run_test_direct — 直接测试运行器
===============================
在当前进程中直接运行测试函数，避免 subprocess 开销。
用法: python run_test_direct.py
"""

import sys, os, time
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def run_all():
    print("=" * 60)
    print("🔧 Agent 1 直接测试运行器")
    print("=" * 60)

    suites = []

    try:
        import test_simple
        suites.append(("基础冒烟", [
            test_simple.test_tools_import,
            test_simple.test_core_imports,
            test_simple.test_agent1_syntax,
        ]))
        print("  ✅ 加载 test_simple")
    except Exception as e:
        print(f"  ❌ test_simple: {e}")

    try:
        import test_stage_a
        suites.append(("阶段A回归", [
            test_stage_a.test_self_check_works,
            test_stage_a.test_test_runner_works,
            test_stage_a.test_directories_exist,
            test_stage_a.test_tools_init_exports,
        ]))
        print("  ✅ 加载 test_stage_a")
    except Exception as e:
        print(f"  ❌ test_stage_a: {e}")

    try:
        import test_patched_exceptions
        suites.append(("异常补丁", [
            test_patched_exceptions.test_all_errors_importable,
            test_patched_exceptions.test_broken_tool_error,
            test_patched_exceptions.test_broken_tool_modes,
        ]))
        print("  ✅ 加载 test_patched_exceptions")
    except Exception as e:
        print(f"  ❌ test_patched_exceptions: {e}")

    try:
        import test_debugger_capture
        suites.append(("Debugger捕获", [
            test_debugger_capture.test_capture_runtime_error,
            test_debugger_capture.test_capture_custom_error,
            test_debugger_capture.test_capture_chain,
        ]))
        print("  ✅ 加载 test_debugger_capture")
    except Exception as e:
        print(f"  ❌ test_debugger_capture: {e}")

    print()
    tp = tf = 0
    for name, tests in suites:
        print(f"▶ {name}")
        for fn in tests:
            try:
                fn()
                tp += 1
            except Exception as exc:
                print(f"  ❌ {fn.__name__}: {exc}")
                tf += 1
    print(f"\n{'='*60}")
    print(f"📊 {tp}/{tp+tf} 通过" + (" ✅" if tf == 0 else " ❌"))
    print("=" * 60)


if __name__ == "__main__":
    run_all()
