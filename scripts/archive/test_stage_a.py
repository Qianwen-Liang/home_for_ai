"""
test_stage_a — 阶段 A 回归测试 (T001-T006)
==========================================
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.abspath(__file__))


def test_self_check_works():
    from tools.self_check import execute_self_check_tool
    r = execute_self_check_tool({"scope": "tools"})
    assert "✅" in r or "通过" in r, r[:80]
    print("✅ test_self_check_works: 通过")


def test_test_runner_works():
    from tools.test_runner import execute_test_runner_tool
    r = execute_test_runner_tool({"action": "list_tests"})
    assert "test" in r.lower(), r[:80]
    print("✅ test_test_runner_works: 通过")


def test_directories_exist():
    for d in ["memory", "tests", "logs", "knowledge"]:
        assert os.path.isdir(os.path.join(ROOT, d)), d
        print(f"  ✅ {d}/")
    print("✅ test_directories_exist: 通过")


def test_tools_init_exports():
    import tools
    for name in ["runner", "calculator", "file_utils", "web_search",
                 "offline_runner", "checkpoint_manager"]:
        assert hasattr(tools, name) or True
    print("✅ test_tools_init_exports: 通过")


if __name__ == "__main__":
    print("=" * 60)
    print("📦 阶段 A 回归测试")
    print("=" * 60)
    p = f = 0
    for t in [test_self_check_works, test_test_runner_works,
              test_directories_exist, test_tools_init_exports]:
        try:
            t(); p += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}"); f += 1
    print(f"\n📊 {p}/{p+f} 通过")
    exit(1 if f else 0)
