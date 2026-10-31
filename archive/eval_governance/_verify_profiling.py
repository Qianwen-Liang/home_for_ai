"""3.3 验证：慢工具/大结果/静默失败画像 + 确定性验证 + 闭环钩子"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.middleware import MIDDLEWARE, TraceMiddleware

MIDDLEWARE.reset()

# 1) 确定性验证一：结果重算
print("── 确定性验证一：结果重算 ──")
for claimed, parts in [(10, [3, 3, 4]), (10, [3, 3, 3]), (0, [])]:
    ok, msg = TraceMiddleware.verify_recomputation(claimed, parts)
    print(f"  声称 {claimed} vs {parts} -> {'✅' if ok else '❌'} {msg}")

# 2) 确定性验证二：覆盖检查
print("\n── 确定性验证二：必需调用覆盖 ──")
for req, act in [(["a", "b"], ["a", "b", "c"]), (["a", "b"], ["a"])]:
    ok, msg = TraceMiddleware.verify_coverage(req, act)
    print(f"  必需 {req} vs 实际 {act} -> {'✅' if ok else '❌'} {msg}")

# 3) 静默失败识别（对照 K2）
print("\n── 确定性验证三：静默失败 ──")
cases = ["返回码: 1", "", "   ", "正常输出", "❌ 失败", "⚠️ 超时", "未找到文件 foo"]
for c in cases:
    print(f"  {c!r:22} -> silent={TraceMiddleware.detect_silent_failure('x', c)}")

# 4) 画像：构造记录
print("\n── 3.3 画像（构造数据）──")
for i, (tool, res, ms) in enumerate([
    ("run_command", "x" * 30000, 5000),      # 大结果 + 慢
    ("read_file", "正常内容", 10),
    ("run_command", "返回码: 1", 20),         # 静默失败
    ("web_search", "结果", 7000),             # 慢
]):
    MIDDLEWARE.record_call(tool=tool, call_id=f"c{i}", arguments={"a": 1},
                           result=res, duration_ms=ms)

print("  慢工具 TOP:")
for r in MIDDLEWARE.slow_tools(3):
    print(f"    {r['tool']:14} avg={r['avg_ms']}ms max={r['max_ms']}ms")
print("  大结果 TOP:")
for r in MIDDLEWARE.large_result_tools(3):
    print(f"    {r['tool']:14} max={r['max_chars']} 字符")
print("  静默失败 TOP:")
for r in MIDDLEWARE.silent_failure_tools(3):
    print(f"    {r['tool']:14} silent={r['silent']}")

# 5) 闭环钩子
print("\n── 观测闭环：on_threshold ──")
acts = MIDDLEWARE.on_threshold()
print(f"  取出 {len(acts)} 个待处理动作:")
for a in acts:
    print(f"    [{a['severity']:5}] {a['kind']:14} {a['message'][:60]}")
print(f"  再次取出（应为 0）: {len(MIDDLEWARE.on_threshold())}")
