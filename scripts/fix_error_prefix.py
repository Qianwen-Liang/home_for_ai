"""K1 修复：统一工具错误返回前缀为 ❌（T2798）。

基线 K1 记录：7 个工具的错误消息前缀不统一（返回"未知操作:/不可用:"等
而非 ❌ 前缀），导致模型需要为每个工具学习不同的失败识别规则。

本脚本只做**最小侵入**替换：把明确表示失败、但缺少统一标记的返回语句
加上 ❌ 前缀。幂等（已带 ❌ 的跳过）。

用法：
    python scripts/fix_error_prefix.py --dry-run
    python scripts/fix_error_prefix.py --apply
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    "tools/calculator.py",
    "tools/task_tracker.py",
    "tools/knowledge_store.py",
    "tools/test_runner.py",
    "tools/web_search.py",
    "evolver/safe_deploy.py",
    "tools/self_check.py",
]

# 失败语义关键词：出现在 return 字符串开头附近即视为错误返回。
# ★注意：不含"未找到"——空结果（"未找到与 X 相关的条目"）是**合法结果**，
# 不是执行失败。给它加 ❌ 会让模型误判为需要重试/修复。
FAIL_WORDS = ("错误", "失败", "未知操作", "不可用", "拒绝", "无法", "不支持", "缺少")

# 已带标记的前缀（无需处理）
OK_PREFIX = ("❌", "⚠️", "ℹ️", "✅", "🔍", "🔬", "📋", "🧪", "📊", "🗑️", "🏥", "📦", "🚀", "🧹", "🎉")

RETURN_RE = re.compile(r'(return\s+f?["\'])(?!❌|⚠️|ℹ️|✅)')


def patch_line(line: str) -> str | None:
    """若该行是缺少 ❌ 的错误返回，返回替换后的行，否则 None。"""
    stripped = line.lstrip()
    if not stripped.startswith("return"):
        return None
    m = RETURN_RE.search(line)
    if not m:
        return None
    # 提取 return 之后的字面量起始片段
    tail = line[m.end():m.end() + 40]
    if any(w in tail for w in FAIL_WORDS):
        return line[:m.end()] + "❌ " + line[m.end():]
    return None


def main() -> int:
    apply_changes = "--apply" in sys.argv

    total_patched = 0
    for rel in TARGETS:
        path = ROOT / rel
        if not path.is_file():
            print(f"  ⚠️ 跳过（不存在）: {rel}")
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        patched: list[tuple[int, str, str]] = []
        for i, line in enumerate(lines):
            new = patch_line(line)
            if new is not None:
                patched.append((i + 1, line.rstrip(), new.rstrip()))
        if not patched:
            print(f"  ✅ {rel}: 无需修改")
            continue
        print(f"\n  📝 {rel}: {len(patched)} 处")
        for ln, old, new in patched[:8]:
            print(f"     L{ln}: {old.strip()[:70]}")
            print(f"       →  {new.strip()[:70]}")
        if len(patched) > 8:
            print(f"     ... 另 {len(patched) - 8} 处")
        if apply_changes:
            for ln, _old, new in patched:
                original = lines[ln - 1]
                indent = original[:len(original) - len(original.lstrip())]
                lines[ln - 1] = indent + new.strip() + ("\n" if original.endswith("\n") else "")
            path.write_text("".join(lines), encoding="utf-8")
            total_patched += len(patched)

    if apply_changes:
        print(f"\n✅ 已修改 {total_patched} 处错误前缀")
    else:
        print("\n--dry-run：未修改。加 --apply 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
