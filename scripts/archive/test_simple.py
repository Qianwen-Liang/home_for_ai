"""
test_simple — 基础冒烟测试
=========================
快速验证核心模块导入和 agent1.py 语法。
"""

import sys, os, py_compile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_tools_import():
    for mod in ["tools.runner", "tools.calculator", "tools.file_utils",
                 "tools.knowledge_store", "tools.task_tracker", "tools.self_check",
                 "tools.test_runner", "tools.monitor", "tools.decision_engine",
                 "tools.safety_net", "tools.web_search", "tools.offline_runner",
                 "tools.checkpoint_manager", "tools.specialist_base"]:
        __import__(mod)
        print(f"  ✅ {mod}")
    print("✅ test_tools_import: 通过")


def test_core_imports():
    for mod in ["read", "write", "conversation", "restart", "broken_tool"]:
        __import__(mod)
        print(f"  ✅ {mod}")
    print("✅ test_core_imports: 通过")


def test_agent1_syntax():
    py_compile.compile("agent1.py", doraise=True)
    print("✅ test_agent1_syntax: 通过")


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 基础冒烟测试")
    print("=" * 60)
    p = f = 0
    for t in [test_tools_import, test_core_imports, test_agent1_syntax]:
        try:
            t(); p += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}"); f += 1
    print(f"\n📊 {p}/{p+f} 通过")
    exit(1 if f else 0)
