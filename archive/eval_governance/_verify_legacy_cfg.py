import sys, json, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过\n")

import agent1
from tools.registry import REGISTRY

print(f"默认工具数: {len(agent1.ALL_TOOLS)}（基础 {agent1.BASE_TOOL_COUNT}）")
print(f"已启用 legacy: {agent1.ENABLED_LEGACY or '无（默认，字节稳定）'}")
print(f"注册表: {len(REGISTRY)}")

# 更新 legacy_tools.json，加入 enabled_legacy 字段
cfg_path = ROOT / "eval" / "governance" / "legacy_tools.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
cfg["enabled_legacy"] = []
cfg["_enabled_legacy_doc"] = ("在此数组中填入 legacy 工具名即可启用（无需改代码）。"
                              "注意：启用会改变工具列表前缀，prompt cache 将重建一次。")
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n✅ 已写入 enabled_legacy 字段: {cfg_path.name}")
print(f"   可选 legacy 工具 {len(agent1._LEGACY_TOOL_DEFS)} 个")
