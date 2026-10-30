import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
py_compile.compile(str(ROOT / "tools" / "runner.py"), doraise=True)
print("✅ 语法通过\n")

from tools.runner import run_command, _truncate_output

# 小输出
small = run_command('echo hello', timeout=10)
print(f"小输出: {len(small)} 字符 -> {small.strip()}")

# 大输出（生成 60000 字符）
big = run_command('python -c "print(\'X\'*60000)"', timeout=20)
print(f"\n大输出截断后: {len(big)} 字符（原始 60000+）")
print(big[:260])
print("...")
print(f"\n是否包含落盘句柄: {'memory/cmd_output' in big}")
