"""P1 现状实测：确认哪些瓶颈真实存在"""
import sys, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

print("=" * 66)
print("1) run_command 超时与进程树清理能力")
print("=" * 66)
from tools.runner import _terminate_process_tree, _clamp_timeout
print("  _terminate_process_tree 存在:", callable(_terminate_process_tree))
t0 = time.time()
out = __import__("tools.runner", fromlist=["run_command"]).run_command(
    'python -c "import time; time.sleep(30)"', timeout=2)
print(f"  2s 超时测试耗时: {(time.time()-t0):.1f}s")
print("  输出:", out.strip()[:120])

print()
print("=" * 66)
print("2) knowledge 检索延迟分解")
print("=" * 66)
from tools import knowledge_store as ks
for label in ["冷启动首次", "二次(缓存)"]:
    t0 = time.time()
    try:
        ks._store.search("DeepSeek 架构", max_results=3)
    except Exception as e:
        print("  search 出错:", e); break
    print(f"  {label}: {(time.time()-t0)*1000:.0f}ms")

print()
print("=" * 66)
print("3) safe_deploy 默认是否只跑受影响测试")
print("=" * 66)
from evolver import safe_deploy as sd
import inspect
sig = inspect.signature(sd.execute_safe_deploy_tool) if hasattr(sd, "execute_safe_deploy_tool") else None
src = (ROOT / "evolver" / "safe_deploy.py").read_text(encoding="utf-8")
print("  默认 run_all_tests:", "run_all_tests.*False" in src.replace(" ", "") or "run_all_tests" in src)

print()
print("=" * 66)
print("4) 工具执行是否串行")
print("=" * 66)
a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")
i = a1.find("for tool_call in tool_calls:")
print("  串行循环存在:", i > 0)
print("  片段:", a1[i:i+80].replace("\n", " ") if i > 0 else "N/A")
