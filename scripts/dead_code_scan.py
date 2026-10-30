"""全仓模块入向依赖扫描：找出真正的死代码（T2798）。

与 archive_analyze.py 的区别：
  - 覆盖 tools/ evolver/ core/ village/ projects/ 全部模块，不只 legacy 名单
  - 排除 deploy_backups / archive / __pycache__ 等非活代码
  - 给出每个模块的入向依赖数与判据，用于"归档 / 纳管"二态划分

判据：
  ZERO     —— 零入向依赖，且不在 agent1 工具表 → 真正的死代码，可归档
  INTERNAL —— 被 agent1 或其他活代码引用 → 内部子系统，必须保留（不可归档）
  REGISTERED —— 在 ALL_TOOLS 注册表中 → LLM 可见工具

用法：python scripts/dead_code_scan.py [--json] [--zero-only]
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["tools", "evolver", "core", "village"]
EXCLUDE_PARTS = {"__pycache__", "deploy_backups", "archive", ".backups"}
TOP_LEVEL = ["agent1.py", "bootstrap.py"]


def _iter_py(dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if EXCLUDE_PARTS & set(p.parts):
                continue
            out.append(p)
    return out


def _top_files() -> list[Path]:
    return [ROOT / n for n in TOP_LEVEL if (ROOT / n).is_file()]


def _mod(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
                # ★关键：`from tools import village_chat` 的依赖是 tools.village_chat，
                # 只记 node.module 会漏检，导致"零入向依赖"误判（首版 bug）。
                for a in node.names:
                    out.add(f"{node.module}.{a.name}")
    return out


def main() -> None:
    as_json = "--json" in sys.argv
    zero_only = "--zero-only" in sys.argv

    files = _iter_py(SCAN_DIRS)
    tops = _top_files()
    tests = [p for p in (ROOT / "tests").rglob("*.py") if "__pycache__" not in p.parts]

    mod_of = {_mod(p): p for p in files}
    all_src = {_mod(p): p for p in files + tops + tests}

    imports_map = {m: _imports(p) for m, p in all_src.items()}

    inbound: dict[str, set[str]] = {m: set() for m in mod_of}
    for src, imps in imports_map.items():
        for imp in imps:
            for full in mod_of:
                if imp == full or imp.startswith(full + "."):
                    if src != full:
                        inbound[full].add(src)

    # agent1 工具表
    agent1_src = (ROOT / "agent1.py").read_text(encoding="utf-8") if (ROOT / "agent1.py").is_file() else ""
    registered_hint = set()
    for line in agent1_src.splitlines():
        if "TOOL_DEFINITION" in line and "tool_" in line:
            for tok in line.replace("[", " ").replace("]", " ").split():
                if tok.startswith("tool_") and tok.endswith(".TOOL_DEFINITION"):
                    registered_hint.add(tok.split(".")[0].replace("tool_", "", 1))

    rows = []
    for full, path in sorted(mod_of.items()):
        deps = inbound.get(full, set())
        live = [d for d in deps if not d.startswith(("tests.", "scripts."))]
        test_deps = [d for d in deps if d.startswith("tests.")]
        if not deps:
            verdict = "ZERO"
        elif not live:
            verdict = "TEST_ONLY"
        else:
            verdict = "INTERNAL"
        rows.append({
            "module": full,
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "inbound_total": len(deps),
            "inbound_live": sorted(live),
            "inbound_tests": sorted(test_deps),
            "verdict": verdict,
            "lines": path.read_text(encoding="utf-8", errors="replace").count("\n") + 1,
        })

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["verdict"], []).append(r)

    print("=" * 78)
    print("全仓模块入向依赖扫描 · 死代码识别")
    print("=" * 78)
    print(f"扫描模块数 {len(rows)}  文件 {len(files)} 个")
    print("-" * 78)

    for key in ("ZERO", "TEST_ONLY", "INTERNAL"):
        items = groups.get(key, [])
        total_lines = sum(i["lines"] for i in items)
        label = {"ZERO": "零入向依赖（可归档）",
                 "TEST_ONLY": "仅测试引用（需连带归档测试）",
                 "INTERNAL": "被活代码引用（内部子系统，保留）"}[key]
        print(f"\n### {key} — {label}：{len(items)} 个模块 / {total_lines} 行")
        if key == "INTERNAL" and not zero_only:
            print("  （仅列出前 10 个作示例）")
        for r in (items if key != "INTERNAL" or not zero_only else items[:10]):
            print(f"  {r['module']:<38} {r['lines']:>5} 行  入向={r['inbound_total']}")
        if key == "INTERNAL" and len(items) > 10 and not zero_only:
            print(f"  ... 其余 {len(items) - 10} 个省略")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
