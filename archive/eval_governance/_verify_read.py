import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
py_compile.compile(str(ROOT / "core" / "read.py"), doraise=True)
print("✅ 语法通过\n")

from core.read import read_file, READ_TOOLS

# 小文件全文
out = read_file("README.md")
print(f"小文件 README.md: {len(out)} 字符（全文）")

# 大文件采样
big = "agent1.py"
out2 = read_file(big)
print(f"\n大文件 {big}: {len(out2)} 字符")
print(out2[:300])
print("...")

# 分段读取
seg = read_file(big, offset=0, limit=5)
print(f"\n分段读取 offset=0 limit=5:")
print(seg[:260])

# 检查 TOOL_DEFINITION
rf = [t for t in READ_TOOLS if t["function"]["name"] == "read_file"][0]
print(f"\nread_file 参数: {list(rf['function']['parameters']['properties'].keys())}")
