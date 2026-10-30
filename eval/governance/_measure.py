import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import agent1

tools = agent1.ALL_TOOLS
full = len(json.dumps(tools, ensure_ascii=False))
print(f"全量 {len(tools)} 工具 schema: {full} 字符 ≈ {full//3} tokens\n")

# 按实测高频顺序定义核心工具
CORE_SETS = {
    "核心5(实测高频)": ["run_command", "write_file", "replace_text", "read_file", "web_search"],
    "核心8": ["run_command", "write_file", "replace_text", "read_file", "web_search",
              "list_directory", "knowledge", "task_tracker"],
    "核心10": ["run_command", "write_file", "replace_text", "read_file", "web_search",
               "list_directory", "knowledge", "task_tracker", "make_directory", "calculate"],
}
for label, names in CORE_SETS.items():
    sel = [t for t in tools if t.get("function", {}).get("name", "") in names]
    sz = len(json.dumps(sel, ensure_ascii=False))
    print(f"{label:18} 命中{len(sel):2}个 | {sz:6} 字符 ≈ {sz//3:5} tokens | "
          f"较全量节省 {(full-sz)/full*100:5.1f}%")

# 加上 search_tools 元工具的估算开销
search_tool_overhead = 700   # 一个 search_tools 定义约 700 字符
print(f"\n+ search_tools 元工具 ≈ {search_tool_overhead} 字符")

print("\n── context window 占比（V4.1 Flash = 1M tokens）──")
for label, names in CORE_SETS.items():
    sel = [t for t in tools if t.get("function", {}).get("name", "") in names]
    sz = len(json.dumps(sel, ensure_ascii=False)) + search_tool_overhead
    print(f"{label:18} {sz//3:5} tokens = {(sz//3)/1_000_000*100:.3f}% of 1M")
print(f"{'全量42':18} {full//3:5} tokens = {(full//3)/1_000_000*100:.3f}% of 1M")

print("\n── MCP 官方阈值建议：context window 的 1%~5% 应切换渐进式发现 ──")
ratio = (full//3) / 1_000_000 * 100
print(f"   我们当前: {ratio:.3f}% → {'接近/超过阈值，建议实施' if ratio >= 1 else '低于阈值，但仍值得做(准确率收益)'}")
