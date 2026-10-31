"""4.3 验证：阈值统一 + 预算感知动态裁剪"""
import sys, py_compile, importlib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

for f in ["tools/budget.py", "core/read.py", "tools/runner.py",
          "tools/middleware.py", "tools/registry.py"]:
    py_compile.compile(str(ROOT / f), doraise=True)
print("✅ 全部文件语法通过\n")

from tools.budget import (BUDGET, ContextBudget, fit_text, snapshot,
                          FULL_TEXT_LIMIT, RESULT_LIMIT, HARD_FILE_LIMIT, MIN_ALLOWANCE)

print("── 统一阈值（唯一来源 tools/budget.py）──")
print(f"  FULL_TEXT_LIMIT = {FULL_TEXT_LIMIT}")
print(f"  RESULT_LIMIT    = {RESULT_LIMIT}")
print(f"  HARD_FILE_LIMIT = {HARD_FILE_LIMIT}")
print(f"  MIN_ALLOWANCE   = {MIN_ALLOWANCE}")

# 确认各模块已引用而非重复定义
import re
print("\n── 各模块是否仍重复定义 ──")
for f in ["core/read.py", "tools/runner.py", "tools/middleware.py", "tools/registry.py"]:
    s = (ROOT / f).read_text(encoding="utf-8")
    dup = re.findall(r"(MAX_FILE_BYTES|FULL_TEXT_LIMIT|MAX_OUTPUT_CHARS|LARGE_CHARS|budget_chars)\s*[:=]\s*[\d_]+", s)
    print(f"  {f:24} 硬编码数字定义: {dup if dup else '无 ✅'}")

print("\n── 预算感知动态裁剪 ──")
b = ContextBudget(pool=50_000)
print(f"  初始: {b.usage()}")
for label, n in [("小文本", 5_000), ("中文本", 15_000), ("大文本", 40_000)]:
    txt = "x" * n
    out, trunc = fit_text(txt, handle="memory/cmd_output/demo.txt", budget=b)
    print(f"  {label}({n}) -> 输出 {len(out)} 字符, truncated={trunc}, 剩余={b.remaining()}")

print("\n── 二元效应防护：池耗尽后额度收缩 ──")
b2 = ContextBudget(pool=25_000)
print(f"  池=25000, 额度={b2.allowance()} (期望 min(20000,25000)=20000)")
b2.consume(20_000)
print(f"  消耗 20000 后剩余={b2.remaining()}, 额度={b2.allowance()} (期望收缩)")
b2.consume(10_000)
print(f"  耗尽后剩余={b2.remaining()}, 额度={b2.allowance()} (期望 MIN_ALLOWANCE={MIN_ALLOWANCE})")
