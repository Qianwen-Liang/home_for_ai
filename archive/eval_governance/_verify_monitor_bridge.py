"""验证 monitor 桥接 + 全链路一致性"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import agent1
from tools.middleware import MIDDLEWARE
from tools import monitor as mon

MIDDLEWARE.reset()
before = len(getattr(mon._monitor, "_data", {}).get("tools", {}) or {})

def call(name, args):
    tc = {"id": f"b_{name}", "type": "function",
          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    return agent1.execute_model_tool_call(tc)

for n, a in [("calculate", {"expression": "3*7"}),
             ("list_directory", {"path": "."})]:
    call(n, a)

snap = MIDDLEWARE.snapshot()
print("中间件采集:", snap["total"], "条")
print("中间件 by_tool:", list(snap.get("by_tool", {}).keys()))

# monitor 是否也被写入
data = getattr(mon._monitor, "_data", {})
tools_data = data.get("tools", {}) if isinstance(data, dict) else {}
print("monitor 中已有工具条目:", list(tools_data.keys())[:8])
hit = all(k in tools_data for k in ("calculate", "list_directory"))
print("✅ monitor 桥接生效" if hit else "⚠️ monitor 未记录到这两个工具")

# usage_analyzer 能否读到
try:
    from evolver import usage_analyzer as ua
    print("\nusage_analyzer 可用:", hasattr(ua, "execute_usage_analyzer_tool"))
except Exception as e:
    print("\nusage_analyzer 导入异常:", e)
