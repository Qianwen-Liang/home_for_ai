"""
execute_test — 测试入口脚本
===========================
运行所有测试文件，生成汇总报告。
用法: python execute_test.py [--verbose]
"""

import sys, os, subprocess, time
ROOT = os.path.dirname(os.path.abspath(__file__))

TESTS = [
    ("基础冒烟", "test_simple.py"),
    ("阶段A回归", "test_stage_a.py"),
    ("异常补丁", "test_patched_exceptions.py"),
    ("Debugger捕获", "test_debugger_capture.py"),
    ("Debugger单元", os.path.join("tests", "test_debugger.py")),
    ("内联检查", "_inline_test.py"),
]


def run_test(name, script, verbose):
    path = os.path.join(ROOT, script)
    if not os.path.isfile(path):
        return name, "SKIP", f"文件不存在: {path}", 0
    start = time.time()
    try:
        r = subprocess.run([sys.executable, path], capture_output=True,
                           text=True, timeout=60, cwd=ROOT)
        dur = time.time() - start
        if r.returncode == 0:
            return name, "PASS", "", dur
        return name, "FAIL", r.stderr[-300:] if r.stderr else "", dur
    except subprocess.TimeoutExpired:
        return name, "TIMEOUT", "", 60
    except Exception as e:
        return name, "ERROR", str(e), 0


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    print("=" * 60)
    print("🧪 Agent 1 完整测试套件")
    print("=" * 60)
    results = []
    for name, script in TESTS:
        print(f"▶ {name} ({script})...", end=" ", flush=True)
        n, s, err, dur = run_test(name, script, verbose)
        results.append((n, s, err, dur))
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⬜", "TIMEOUT": "⏰", "ERROR": "⚠️"}
        print(f"{icon[s]} {s}" + (f" ({dur:.1f}s)" if dur else ""))
        if verbose and err:
            print(f"   {err[:200]}")
    print(f"\n{'='*60}")
    passed = sum(1 for _, s, _, _ in results if s == "PASS")
    print(f"📊 汇总: {passed}/{len(results)} 通过")
    for n, s, err, dur in results:
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⬜", "TIMEOUT": "⏰", "ERROR": "⚠️"}
        print(f"  {icon[s]} {n}" + (f" ({dur:.1f}s)" if dur else ""))
    print("=" * 60)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
