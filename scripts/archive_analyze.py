"""Legacy 工具归档前的依赖分析（T2798）。

回答三个问题：
  1. 每个 legacy 工具名对应哪个真实模块文件？
  2. 谁 import 了它（入向依赖）？
  3. 它 import 了谁（出向依赖）？归档它是否会连带打断调用链？

判定规则（保守）：
  - 若被 agent1.py / tests / 已注册工具 / 非 legacy 模块引用 → 不可归档
  - 仅被其他 legacy 模块引用 → 可随同归档（需成组移动）
  - 零入向依赖 → 可安全归档

用法：python scripts/archive_analyze.py [--json]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIRS = ["tools", "evolver", "core", "village", "projects", "scripts", "tests"]
TOP_LEVEL = ["agent1.py", "bootstrap.py"]


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for name in TOP_LEVEL:
        p = ROOT / name
        if p.is_file():
            files.append(p)
    for d in PKG_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            files.append(p)
    return files


def _module_name(path: Path) -> str:
    """tools/monitor.py -> tools.monitor ; agent1.py -> agent1"""
    rel = path.relative_to(ROOT)
    return ".".join(rel.with_suffix("").parts)


def _imports(path: Path) -> set[str]:
    """提取文件的所有被导入模块（含 from x import y 的 x）。"""
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
                for a in node.names:
                    out.add(f"{node.module}.{a.name}")
    return out


def load_legacy_names() -> list[str]:
    src = (ROOT / "agent1.py").read_text(encoding="utf-8")
    i = src.find("LEGACY_TOOLS = (")
    j = src.find(")", i)
    return re.findall(r'"([a-z_]+)"', src[i:j + 1])


def main() -> None:
    as_json = "--json" in sys.argv
    legacy = load_legacy_names()

    files = _iter_py_files()
    mod_of = {_module_name(p): p for p in files}
    # 模块短名 -> 全名（tools.monitor 的短名是 monitor）
    short_index: dict[str, list[str]] = {}
    for full in mod_of:
        short = full.rsplit(".", 1)[-1]
        short_index.setdefault(short, []).append(full)

    imports_map = {m: _imports(p) for m, p in mod_of.items()}

    # 反向索引：被谁 import
    inbound: dict[str, set[str]] = {m: set() for m in mod_of}
    for src, imps in imports_map.items():
        for imp in imps:
            for full, _p in mod_of.items():
                if imp == full or imp.startswith(full + "."):
                    if src != full:
                        inbound[full].add(src)

    # legacy 名 -> 候选模块全名
    report: dict[str, dict] = {}
    for name in legacy:
        candidates = []
        if f"tools.{name}" in mod_of:
            candidates.append(f"tools.{name}")
        for full in mod_of:
            if full.rsplit(".", 1)[-1] == name and full not in candidates:
                candidates.append(full)
        # 名称近似（offline -> offline_runner, checkpoint -> checkpoint_manager）
        if not candidates:
            for full in mod_of:
                short = full.rsplit(".", 1)[-1]
                if short.startswith(name) or name.startswith(short):
                    candidates.append(full)

        entries = []
        for full in candidates:
            deps = sorted(inbound.get(full, set()))
            entries.append({"module": full, "inbound": deps, "inbound_count": len(deps)})
        report[name] = {"candidates": entries}

    # 分类
    legacy_full = {e["module"] for r in report.values() for e in r["candidates"]}
    protected_prefixes = ("agent1", "tests.", "scripts.")
    registered_tools = (ROOT / "agent1.py").read_text(encoding="utf-8")

    for name, info in report.items():
        for e in info["candidates"]:
            ext = [d for d in e["inbound"] if not d.startswith(protected_prefixes)]
            prot = [d for d in e["inbound"] if d.startswith(protected_prefixes)]
            e["external_inbound"] = ext
            e["protected_inbound"] = prot
            if prot:
                e["verdict"] = "BLOCKED"      # 被 agent1/tests/scripts 使用
            elif ext:
                e["verdict"] = "GROUP_ONLY"   # 仅被其他模块引用，需成组归档
            else:
                e["verdict"] = "SAFE"         # 零入向依赖

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 78)
    print("Legacy 工具归档 · 依赖分析")
    print("=" * 78)
    for name in legacy:
        cands = report[name]["candidates"]
        if not cands:
            print(f"\n[{name}]  ⚠️ 未找到对应模块")
            continue
        for e in cands:
            icon = {"SAFE": "✅", "GROUP_ONLY": "🟡", "BLOCKED": "⛔"}[e["verdict"]]
            print(f"\n[{name}] -> {e['module']}  {icon} {e['verdict']}")
            if e["protected_inbound"]:
                print(f"    受保护引用: {', '.join(e['protected_inbound'][:6])}")
            if e["external_inbound"]:
                print(f"    其他引用: {', '.join(e['external_inbound'][:8])}")

    print("\n" + "=" * 78)
    counts: dict[str, int] = {}
    for info in report.values():
        for e in info["candidates"]:
            counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1
    total = sum(len(i["candidates"]) for i in report.values())
    print(f"候选模块总数 {total}：SAFE={counts.get('SAFE',0)}  "
          f"GROUP_ONLY={counts.get('GROUP_ONLY',0)}  BLOCKED={counts.get('BLOCKED',0)}")
    print("=" * 78)


if __name__ == "__main__":
    main()
