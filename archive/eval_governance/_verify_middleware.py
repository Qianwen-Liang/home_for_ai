import sys, json, py_compile, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "tools" / "middleware.py"), doraise=True)
py_compile.compile(str(ROOT / "agent1.py"), doraise=True)
print("✅ 语法通过")

# 手工埋点是否归零
a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")
manual = len(re.findall(r"tool_monitor\._monitor\.record", a1))
print(f"手工埋点剩余: {manual} 处（应为 0）")

import agent1
from tools.middleware import MIDDLEWARE, OTEL_TOOL_NAME, METRIC_TOOL_DURATION

MIDDLEWARE.reset()

def call(name, args):
    tc = {"id": f"mw_{name}", "type": "function",
          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    return agent1.execute_model_tool_call(tc)

print("\n── 采集验证 ──")
for n, a in [("calculate", {"expression": "1+1"}),
             ("read_file", {"path": "README.md"}),
             ("read_file", {"path": "__nope__.txt"}),
             ("run_command", {"command": "exit 1", "timeout": 5})]:
    try:
        call(n, a)
    except Exception as e:
        print(f"  {n}: EXC {type(e).__name__}")

snap = MIDDLEWARE.snapshot()
print(f"\n采集条数: {snap['total']}")
print(f"错误率: {snap['error_rate']}, 静默失败率: {snap['silent_rate']}, 平均耗时: {snap['avg_ms']}ms")
print("\n按工具:")
for t, d in snap.get("by_tool", {}).items():
    print(f"  {t:14} calls={d['calls']} avg={d['avg_ms']}ms errors={d['errors']} silent={d['silent']} maxchars={d['max_chars']}")

print("\n── OTel 兼容导出 ──")
ev = MIDDLEWARE.export_otel(3)
print(f"事件数: {len(ev)}")
if ev:
    print(f"属性键: {list(ev[0]['attributes'].keys())}")
    print(f"指标键: {list(ev[0]['metric'].keys())}")

print("\n── 静默失败识别（K2 场景）──")
for r in ["返回码: 1", "正常输出内容", "⚠️ 命令执行超时", "❌ 未知工具: xx"]:
    print(f"  {r!r:28} -> silent={MIDDLEWARE.detect_silent_failure('run_command', r)}")
