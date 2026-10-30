"""候选归档模块的引用核查（T2798）。

对每个候选模块，在全仓（含 scripts/、docs/*.md、agent1.py 系统提示词）
搜索其名字出现位置，区分：
  - import 引用（代码依赖）
  - 字符串/文档引用（可能被约定直接调用）
  - 自身定义

避免"AST 看不到 = 没人用"的误判。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CANDIDATES = [
    "capsule", "code_analyzer", "log_rotation", "test_tools",
    "checkpoint_backend", "executor_registry", "experience_learner",
    "guardrails", "retry_policy", "role_system", "acp_server", "amone",
]

EXCLUDE_PARTS = {"__pycache__", "deploy_backups", ".git", ".pytest_cache"}


def _all_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if EXCLUDE_PARTS & set(p.parts):
            continue
        if p.suffix in (".py", ".md", ".json", ".toml", ".txt"):
            out.append(p)
    return out


def main() -> None:
    files = _all_files()
    report = {}
    for name in CANDIDATES:
        hits = []
        for p in files:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            # 排除模块自身文件
            if Path(rel).stem == name and rel.startswith(("tools/", "evolver/", "core/", "village/")):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if name not in text:
                continue
            for ln, line in enumerate(text.splitlines(), 1):
                if name in line:
                    kind = "import" if ("import" in line or "from " in line) else "mention"
                    hits.append({"file": rel, "line": ln, "kind": kind, "text": line.strip()[:110]})
                    break
        code_hits = [h for h in hits if h["kind"] == "import"]
        report[name] = {
            "total_files": len(hits),
            "import_refs": code_hits,
            "mention_refs": [h for h in hits if h["kind"] == "mention"],
        }

    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 78)
    print("候选归档模块 · 全仓引用核查")
    print("=" * 78)
    for name, info in report.items():
        flag = "✅ 可归档" if not info["import_refs"] and not info["mention_refs"] else "⚠️ 有引用"
        print(f"\n[{name}]  {flag}  引用文件数={info['total_files']}")
        for h in info["import_refs"][:4]:
            print(f"    import  {h['file']}:{h['line']}  {h['text'][:80]}")
        for h in info["mention_refs"][:4]:
            print(f"    mention {h['file']}:{h['line']}  {h['text'][:80]}")
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
