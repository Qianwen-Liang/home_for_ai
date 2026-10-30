"""code_analyzer — 代码库结构分析工具

基于 Python AST 的静态分析，提取代码库的：
  - import 依赖关系（跨文件引用）
  - 函数/类定义清单
  - 代码规模统计

帮助 Agent 快速理解代码库结构，对齐 Codex 的"代码库理解"能力。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "code_analyzer",
        "description": (
            "代码库结构分析工具。扫描指定目录的 Python 文件，"
            "提取 import 依赖关系、函数/类定义、代码规模统计。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "要分析的目录（相对路径），如 'tools' 或 '.'",
                    "default": "tools",
                },
                "detail": {
                    "type": "boolean",
                    "description": "是否输出函数/类定义明细，默认 False",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
    },
}


def _parse_file(path: Path) -> dict[str, Any]:
    """解析单个 Python 文件，提取结构信息。"""
    info: dict[str, Any] = {
        "path": str(path),
        "imports": [],
        "functions": [],
        "classes": [],
        "lines": 0,
    }
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return info

    info["lines"] = len(source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError:
        info["parse_error"] = True
        return info

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info["imports"].append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                info["imports"].append(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            info["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "args": [a.arg for a in node.args.args],
            })
        elif isinstance(node, ast.ClassDef):
            info["classes"].append({
                "name": node.name,
                "line": node.lineno,
            })

    # 去重 imports
    info["imports"] = sorted(set(info["imports"]))
    return info


def analyze(target: str = "tools", detail: bool = False) -> str:
    """分析代码库结构。"""
    base = SANDBOX_DIR / target
    if not base.is_dir():
        return f"⚠️ 目录不存在: {target}"

    py_files = sorted(base.rglob("*.py"))
    if not py_files:
        return f"⚠️ 目录 {target} 下无 .py 文件。"

    results = [_parse_file(f) for f in py_files]
    results = [r for r in results if r["lines"] > 0]

    total_lines = sum(r["lines"] for r in results)
    total_funcs = sum(len(r["functions"]) for r in results)
    total_classes = sum(len(r["classes"]) for r in results)

    # 内部 import 关系（引用 sandbox 内的模块）
    all_imports: dict[str, int] = {}
    for r in results:
        for imp in r["imports"]:
            all_imports[imp] = all_imports.get(imp, 0) + 1

    internal_imports = {k: v for k, v in all_imports.items() if k in ("tools", "evolver") or k.startswith("tools")}

    lines = [
        f"📊 代码库分析报告: {target}",
        f"{'─'*50}",
        f"文件数: {len(results)} | 总行数: {total_lines:,} | "
        f"函数: {total_funcs} | 类: {total_classes}",
        "",
        f"📦 内部依赖 (import 计数):",
    ]
    for mod, count in sorted(internal_imports.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {mod}: {count} 次")
    if not internal_imports:
        lines.append("  (无内部 tools 依赖)")

    lines.append("")
    lines.append(f"📁 文件规模 TOP 10:")
    for r in sorted(results, key=lambda x: -x["lines"])[:10]:
        lines.append(f"  {r['path'].replace(str(SANDBOX_DIR)+chr(92), '')}: {r['lines']} 行")

    if detail:
        lines.append("")
        lines.append(f"🔍 函数/类定义明细:")
        for r in results:
            for f in r["functions"]:
                lines.append(f"  {r['path'].split(chr(92))[-1]}:L{f['line']} def {f['name']}({', '.join(f['args'])})")

    return "\n".join(lines)


def execute_code_analyzer_tool(arguments: dict[str, Any]) -> str:
    target = arguments.get("target", "tools")
    detail = bool(arguments.get("detail", False))
    return analyze(target, detail)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(analyze("tools", detail=False))
