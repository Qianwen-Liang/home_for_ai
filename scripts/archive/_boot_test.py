"""启动测试 — 仅当被 Python 直接执行时运行"""
import subprocess, sys
result = subprocess.run(
    [sys.executable, "test_stage_a.py"],
    capture_output=True, text=True, timeout=60, cwd="agent-sandbox"
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print(f"返回码: {result.returncode}")
