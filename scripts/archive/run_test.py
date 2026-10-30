"""快速运行阶段A测试的启动脚本"""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "agent-sandbox/test_stage_a.py"],
    capture_output=True,
    text=True,
    timeout=60,
    cwd="agent-sandbox",
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print(f"返回码: {result.returncode}")
