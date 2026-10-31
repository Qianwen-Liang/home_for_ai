import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
py_compile.compile(str(ROOT / "tools" / "capsule.py"), doraise=True)
print("✅ 语法通过\n")

from tools import capsule as cap

print(cap.save_capsule("arch-governance-p0p3", {
    "goal": "执行架构治理 P0-P3",
    "done": ["P0 工具集收敛 42→16（schema -74.6%）",
             "P1 knowledge 冷启动 43.5s→160ms",
             "P2 read_file 大文件采样 -93.4%"],
    "doing": ["P3 capsule 机制落地"],
    "todo": ["回归测试", "部署验证"],
    "decisions": ["工具集保持字节稳定，不做运行期动态增删"],
    "files": {"agent1.py": "ALL_TOOLS 已收敛至 16 个",
              "tools/knowledge_store.py": "后台预热+首次降级"},
}, note="P3 实施中"))

print()
print("列表:", cap.list_capsules())
print()
c = cap.load_capsule("arch-governance-p0p3")
print(cap.render_capsule(c))
print()
print("should_checkpoint(120):", cap.should_checkpoint(120))
print("should_checkpoint(50):", cap.should_checkpoint(50))
