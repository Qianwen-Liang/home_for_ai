"""执行 legacy 工具归档与三态分类（T2798）。

背景（实证）：26 个 legacy 工具名对应的模块，**全部被 agent1.py 直接 import**，
属于"LLM 不可见但系统内部在用"的内部子系统，不是死代码。
机械物理归档会直接 ImportError 打断系统。

因此本脚本执行的是"消除中间态"的正确形态：

  1. 物理归档：仅移动**确证零代码引用**且非既有交付物的模块 → archive/
  2. 三态分类：把 26 个 legacy 从"待定"明确归入
       internal_subsystem —— 被 agent1 等活代码 import（保留，语义澄清）
       test_only          —— 仅被测试引用
       archived           —— 已物理移出
  3. 落 manifest：记录证据、时间、可回滚路径

用法：
    python scripts/archive_execute.py --dry-run
    python scripts/archive_execute.py --apply
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = ROOT / "archive"
MANIFEST = ARCHIVE_ROOT / "ARCHIVE_MANIFEST.json"
LEGACY_JSON = ROOT / "eval" / "governance" / "legacy_tools.json"

# 物理归档候选（须经 ref_check 证零 import 引用，且非既有能力交付物）
PHYSICAL_ARCHIVE = [
    {"module": "tools.log_rotation", "path": "tools/log_rotation.py",
     "reason": "零 import 引用、无 hot_reload 映射、非已知交付物", "lines": 145},
]

# 明确不归档的原因（留档，避免下次重复调研）
KEPT_WITH_REASON = {
    "tools.capsule": "T2795 P3 能力交付物，agent1 系统提示词约定调用（文档级引用，非 import）",
    "village.acp_server": "T2443 ACP 协议对齐交付物",
    "tools.code_analyzer": "evolver/hot_reload.py 热重载映射表登记",
}

EXCLUDE_PARTS = {"__pycache__", "deploy_backups", ".git", ".pytest_cache"}


def _importers_of(target_module: str) -> list[str]:
    """返回实际 import 该模块的文件（AST 级，含 from pkg import sub 形式）。"""
    hits = []
    for p in ROOT.rglob("*.py"):
        if EXCLUDE_PARTS & set(p.parts):
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel == f"{target_module.replace('.', '/')}.py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == target_module or a.name.startswith(target_module + "."):
                        hits.append(rel)
            elif isinstance(node, ast.ImportFrom):
                if node.module == target_module:
                    hits.append(rel)
                elif node.module:
                    for a in node.names:
                        if f"{node.module}.{a.name}" == target_module:
                            hits.append(rel)
    return sorted(set(hits))


def load_legacy() -> dict:
    return json.loads(LEGACY_JSON.read_text(encoding="utf-8"))


def main() -> int:
    apply_changes = "--apply" in sys.argv
    dry = not apply_changes

    legacy_names = load_legacy()["legacy"]

    # ── 1. 物理归档前再验一次零引用 ──
    plan = []
    for item in PHYSICAL_ARCHIVE:
        importers = _importers_of(item["module"])
        ok = not importers
        plan.append({**item, "importers": importers, "safe": ok})

    # ── 2. 26 个 legacy 的分类 ──
    classification: dict[str, dict] = {}
    for name in legacy_names:
        # 尝试定位模块
        candidates = [m for m in _all_modules() if m.rsplit(".", 1)[-1] == name]
        if not candidates:
            for m in _all_modules():
                short = m.rsplit(".", 1)[-1]
                if short.startswith(name) or name.startswith(short):
                    candidates.append(m)
        if not candidates:
            classification[name] = {"class": "unresolved", "evidence": [], "note": "未定位到同名模块"}
            continue

        best = None
        for mod in candidates:
            importers = _importers_of(mod)
            live = [i for i in importers if not i.startswith(("tests/", "scripts/"))]
            tests = [i for i in importers if i.startswith("tests/")]
            if live:
                best = (mod, "internal_subsystem", live, tests)
                break
            if best is None:
                best = (mod, "test_only", [], tests)
        mod, cls, live, tests = best
        classification[name] = {
            "class": cls,
            "module": mod,
            "live_importers": live,
            "test_importers": tests,
            "note": KEPT_WITH_REASON.get(mod, ""),
        }

    for item in plan:
        classification[item["module"]] = {
            "class": "archived" if item["safe"] else "archive_blocked",
            "module": item["module"],
            "live_importers": item["importers"],
            "note": item["reason"],
        }

    # ── 3. 输出计划 ──
    print("=" * 78)
    print(f"归档执行计划（{'DRY-RUN' if dry else 'APPLY'}）")
    print("=" * 78)

    print("\n[物理归档]")
    for p in plan:
        icon = "✅" if p["safe"] else "⛔"
        print(f"  {icon} {p['module']} ({p['lines']} 行) — {p['reason']}")
        if p["importers"]:
            print(f"     阻断：被 import: {p['importers'][:5]}")

    print("\n[26 个 legacy 三态分类]")
    groups: dict[str, list[str]] = {}
    for name, info in classification.items():
        groups.setdefault(info["class"], []).append(name)
    for cls, names in sorted(groups.items()):
        print(f"  {cls:<20} {len(names):>2} 个: {', '.join(sorted(names))}")

    print("\n[明确保留并记录理由]")
    for mod, reason in KEPT_WITH_REASON.items():
        print(f"  • {mod}: {reason}")

    if dry:
        print("\n--dry-run：未做任何修改。加 --apply 执行。")
        return 0

    # ── 4. 执行 ──
    ARCHIVE_ROOT.mkdir(exist_ok=True)
    moved = []
    for p in plan:
        if not p["safe"]:
            continue
        src = ROOT / p["path"]
        if not src.is_file():
            continue
        dst_dir = ARCHIVE_ROOT / "tools"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        shutil.move(str(src), str(dst))
        moved.append({"from": p["path"], "to": str(dst.relative_to(ROOT)).replace("\\", "/"),
                      "module": p["module"], "lines": p["lines"], "reason": p["reason"]})

    manifest = {
        "_doc": "legacy 工具归档记录。可回滚：将 files[].to 移回 from 并重启。",
        "executed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evidence": "scripts/archive_analyze.py + scripts/dead_code_scan.py + scripts/ref_check.py",
        "key_finding": (
            "26 个 legacy 工具名对应模块全部被 agent1.py import，属内部子系统而非死代码；"
            "物理归档仅对确证零代码引用者执行。"
        ),
        "files": moved,
        "kept_with_reason": KEPT_WITH_REASON,
        "classification": classification,
        "restore_hint": "python scripts/archive_execute.py --restore（见下）",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同步 legacy_tools.json 的分类
    data = load_legacy()
    data["classification"] = {k: v["class"] for k, v in classification.items()}
    data["classification_evidence"] = "scripts/archive_execute.py 生成，见 archive/ARCHIVE_MANIFEST.json"
    LEGACY_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 已移动 {len(moved)} 个模块 → archive/")
    print(f"✅ manifest: {MANIFEST.relative_to(ROOT)}")
    print(f"✅ classification 已写回 {LEGACY_JSON.relative_to(ROOT)}")
    return 0


_MODULE_CACHE: list[str] | None = None


def _all_modules() -> list[str]:
    global _MODULE_CACHE
    if _MODULE_CACHE is not None:
        return _MODULE_CACHE
    mods = []
    for d in ("tools", "evolver", "core", "village"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if EXCLUDE_PARTS & set(p.parts):
                continue
            mods.append(".".join(p.relative_to(ROOT).with_suffix("").parts))
    _MODULE_CACHE = mods
    return mods


if __name__ == "__main__":
    raise SystemExit(main())
