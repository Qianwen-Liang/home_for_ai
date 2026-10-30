"""步骤 2.3 分派层重构：elif 链 → 注册表查表（保留 legacy 兼容路径）

策略：
  1) 把原 37 个 elif 分支原样搬进 _legacy_dispatch()
  2) 主路径改为 REGISTRY.get(name).handler(arguments)
  3) 开关 _USE_REGISTRY_DISPATCH 可一键回退
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
p = ROOT / "agent1.py"
src = p.read_text(encoding="utf-8")
lines = src.splitlines()

# 1) 定位分派块
start = next(i for i, l in enumerate(lines)
             if 'if name in {"read_file", "list_directory"}' in l)
# 分派块从 start-1（try:）开始
block_start = start - 1
assert lines[block_start].strip() == "try:", lines[block_start]

# 2) 找到块结束（未知工具提示的 _tool_success = False）
end = None
for i in range(start, len(lines)):
    if lines[i].strip() == "_tool_success = False":
        end = i
        break
assert end is not None

# 3) 提取 elif 链主体（从 if 行到 最后一个 elif 的 result 赋值）
body_lines = []
for i in range(start, end):
    l = lines[i]
    if l.strip().startswith("else:"):
        break
    body_lines.append(l)

# 4) 生成 _legacy_dispatch：把 result = X 改成 return X
legacy_body = []
for l in body_lines:
    s = l.strip()
    if s.startswith("result = "):
        indent = l[: len(l) - len(l.lstrip())]
        legacy_body.append(f"{indent}return {s[len('result = '):]}")
    else:
        legacy_body.append(l)
legacy_fn = [
    "",
    "# ── 步骤 2.3：分派层 —— 注册表查表（主）/ elif 链（兼容回退）──",
    "_USE_REGISTRY_DISPATCH = True   # 置 False 即可回退到 legacy elif 链",
    "",
    "",
    "def _unknown_tool_hint(name: str) -> str:",
    '    """未知工具友好提示（不抛异常，让模型自行纠正）。"""',
    '    known_tools = [t.get("function", {}).get("name", "") for t in ALL_TOOLS]',
    "    known_tools = [n for n in known_tools if n]",
    "    hint = \", \".join(known_tools[:8])",
    "    return (",
    '        f"❌ 未知工具: {name}。该工具不存在于当前可用工具列表中。\\n"',
    '        f"请从以下工具中选择一个重新尝试（前8个）: {hint}\\n"',
    '        f"💡 提示: 如果你需要查找文件，请使用 file_utils（action=\'find\'）；"',
    '        f"联网搜索请用 web_search。"',
    "    )",
    "",
    "",
    "def _legacy_dispatch(name: str, arguments: dict) -> str | None:",
    '    """旧 elif 分派链（兼容回退路径，保留全部历史分支）。"""',
] + legacy_body + [
    "    return None",
    "",
    "",
]

# 5) 新分派块
new_block = [
    "    try:",
    "        if _USE_REGISTRY_DISPATCH:",
    "            _spec = REGISTRY.get(name)",
    "            if _spec is not None:",
    "                result = _spec.handler(arguments)",
    "            else:",
    "                result = _unknown_tool_hint(name)",
    "                _tool_success = False",
    "        else:",
    "            _legacy_result = _legacy_dispatch(name, arguments)",
    "            if _legacy_result is None:",
    "                result = _unknown_tool_hint(name)",
    "                _tool_success = False",
    "            else:",
    "                result = _legacy_result",
]

# 6) 组装
new_lines = (lines[:block_start] + new_block + lines[end + 1:])

# 7) 在 execute_model_tool_call 定义前插入 legacy 函数
insert_at = None
for i, l in enumerate(new_lines):
    if l.startswith("def execute_model_tool_call("):
        insert_at = i
        break
assert insert_at is not None, "未找到 execute_model_tool_call"

new_lines = new_lines[:insert_at] + legacy_fn + new_lines[insert_at:]

p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("✅ 重构完成")
print(f"   legacy 分支数: {sum(1 for l in legacy_body if l.strip().startswith('elif ') or l.strip().startswith('if name'))}")
print(f"   文件行数: {len(lines)} -> {len(new_lines)}")
