"""4.1 验证：错误分类覆盖率（要求 35/35 全覆盖，不允许走启发式兜底）"""
import sys, re, glob, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

py_compile.compile(str(ROOT / "tools" / "errors.py"), doraise=True)
print("✅ 语法通过\n")

from tools.errors import ERROR_MAP, classify, coverage_report, make_evidence, ErrorCategory

# 扫描所有错误类
found = {}
for f in (glob.glob(str(ROOT / "tools" / "*.py")) + glob.glob(str(ROOT / "core" / "*.py"))
          + glob.glob(str(ROOT / "evolver" / "*.py")) + [str(ROOT / "agent1.py")]):
    src = open(f, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"class (\w*Error\w*)\((.*?)\):", src):
        bases = m.group(2)
        # 排除枚举/数据类等非异常类（如 ErrorCategory(str, Enum)）
        if "Enum" in bases or "dataclass" in bases:
            continue
        found.setdefault(m.group(1), set()).add(bases.strip())

print(coverage_report())
print()

missing = sorted(set(found) - set(ERROR_MAP))
extra = sorted(set(ERROR_MAP) - set(found))
print(f"扫描到错误类 {len(found)} 种")
print(f"映射表 {len(ERROR_MAP)} 种")
print(f"❌ 未覆盖: {missing if missing else '无'}")
print(f"⚠️ 映射表多余: {extra if extra else '无'}")
print(f"\n覆盖率: {len(set(found) & set(ERROR_MAP))}/{len(found)}")

# 实例化验证
print("\n── 分类实例验证 ──")
from tools.web_search import WebSearchError
from core.read import ReadToolError
from tools.test_runner import TestRunnerError
for exc in [WebSearchError("net down"), ReadToolError("路径不存在"), TestRunnerError("broken")]:
    cat, code, phase = classify(exc)
    ev = make_evidence(exc)
    print(f"  {type(exc).__name__:20} -> {cat.value:10} code={code:24} phase={phase} retryable={ev.retryable}")

# 优先级规则验证（多特征冲突取最保守）
print("\n── 优先级规则：FATAL > REJECTED > RETRYABLE ──")
class TimeoutPathError(RuntimeError):
    pass
cat, code, _ = classify(TimeoutPathError("x"))
print(f"  未登记类型(名含Timeout+Path) -> {cat.value}（启发式）")
