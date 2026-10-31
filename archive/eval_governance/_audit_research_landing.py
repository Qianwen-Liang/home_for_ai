"""验证：历史调研结论是否真的落进了代码（反向追溯）"""
import sys, re, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

print("=" * 74)
print("步骤1 调研 → 代码 落地验证")
print("=" * 74)

# 1) MCP 契约标准（inputSchema / isError / annotations）
spec = (ROOT / "tests" / "contract" / "SPEC.md").read_text(encoding="utf-8")
tests = (ROOT / "tests" / "contract" / "test_tool_contracts.py").read_text(encoding="utf-8")
checks1 = {
    "MCP inputSchema 字段规范": "inputSchema" in spec,
    "MCP annotations 不可信约定": "annotations" in spec and "不可信" in spec,
    "MCP 双错误机制(Protocol/Execution)": "Protocol Error" in spec and "Tool Execution Error" in spec,
    "Hypothesis 属性测试实装": "from hypothesis import" in tests,
    "jsonschema 依赖使用": "jsonschema" in tests,
}
for k, v in checks1.items():
    print(f"  {'✅' if v else '❌'} {k}")

print()
print("=" * 74)
print("步骤2 调研 → 代码 落地验证")
print("=" * 74)
reg = (ROOT / "tools" / "registry.py").read_text(encoding="utf-8")
a1 = (ROOT / "agent1.py").read_text(encoding="utf-8")

checks2 = {
    "实测结论: dict查表替代elif → _legacy_dispatch 存在": "_legacy_dispatch" in a1,
    "实测结论: 字节稳定 → 哈希断言": "_BASELINE_SHA256" in a1,
    "实测结论: 装饰器注册 → register_tool": "def register_tool" in reg,
    "pluggy借鉴: 规格/实现/管理器分离": "class ToolSpec" in reg and "class ToolRegistry" in reg,
    "学术2608.25512: 时间可组合性 → unregister": "def unregister" in reg,
    "学术2608.25512: 空间可组合性 → dependencies": "dependencies" in reg,
    "学术2608.25512: 响应式→ activate_when": "activate_when" in reg,
    "学术2608.06370: PTC → stub 字段": "stub:" in reg,
}
for k, v in checks2.items():
    print(f"  {'✅' if v else '❌'} {k}")

print()
print("=" * 74)
print("步骤3 调研 → 代码 落地验证（落地契约 10 项）")
print("=" * 74)
mw = (ROOT / "tools" / "middleware.py").read_text(encoding="utf-8")
a1_now = (ROOT / "agent1.py").read_text(encoding="utf-8")

checks3 = {
    "1. OTel属性 gen_ai.tool.name": "gen_ai.tool.name" in mw,
    "2. OTel指标 gen_ai.execute_tool.duration": "gen_ai.execute_tool.duration" in mw,
    "3. OTel异常 gen_ai.client.operation.exception": "gen_ai.client.operation.exception" in mw,
    "4. 确定性验证-结果重算": "def verify_recomputation" in mw,
    "5. 确定性验证-覆盖检查": "def verify_coverage" in mw,
    "6. 静默失败识别": "def detect_silent_failure" in mw,
    "7. 观测闭环 on_threshold": "def on_threshold" in mw,
    "8. 与注册表联动(读spec)": "spec" in mw and "read_only" in mw,
    "9. 手工埋点归零": len(re.findall(r"tool_monitor\._monitor\.record", a1_now)) == 0,
    "10. 零第三方依赖": not any(k in mw for k in
                          ("import opentelemetry", "import structlog", "import prometheus")),
    "中间件已在执行链接入": bool(re.search(r"\b_MW\.record_call|MIDDLEWARE\.record_call", a1_now)),
}
for k, v in checks3.items():
    print(f"  {'✅' if v else '❌'} {k}")

failed = [k for k, v in checks3.items() if not v]
print(f"\n落地率: {len(checks3) - len(failed)}/{len(checks3)}")
if failed:
    print("  ❌ 未落地:", failed)

print()
print("=" * 74)
print("步骤4 调研 → 代码 落地验证")
print("=" * 74)
errmod = (ROOT / "tools" / "errors.py").read_text(encoding="utf-8")
budgetmod = (ROOT / "tools" / "budget.py").read_text(encoding="utf-8")
a1_now = (ROOT / "agent1.py").read_text(encoding="utf-8")

checks4 = {
    "1. 三层错误模型(ErrorCategory)": "class ErrorCategory" in errmod,
    "2. gRPC语义对齐(RETRYABLE/REJECTED/FATAL)": all(
        k in errmod for k in ("RETRYABLE", "REJECTED", "FATAL")),
    "3. 错误映射表(ERROR_MAP)": "ERROR_MAP" in errmod,
    "4. 可审计证据(ErrorEvidence)": "class ErrorEvidence" in errmod,
    "5. 失败阶段记录(phase)": "phase" in errmod,
    "6. OTel异常事件名": "gen_ai.client.operation.exception" in errmod,
    "7. 手工except元组已消除": not bool(re.search(r"except \(\s*\n\s*ReadToolError", a1_now)),
    "8. 错误契约声明化(ToolSpec.errors)": "_TOOL_ERROR_TYPES" in a1_now,
    "9. 统一阈值唯一来源(budget.py)": "FULL_TEXT_LIMIT" in budgetmod and "RESULT_LIMIT" in budgetmod,
    "10. 预算感知动态裁剪(allowance)": "def allowance" in budgetmod,
    "11. 各模块无硬编码阈值": not any(
        re.search(r"(MAX_FILE_BYTES|MAX_OUTPUT_CHARS|LARGE_CHARS)\s*=\s*[\d_]+", (ROOT / f).read_text(encoding="utf-8"))
        for f in ["core/read.py", "tools/runner.py", "tools/middleware.py"]),
}
for k, v in checks4.items():
    print(f"  {'✅' if v else '❌'} {k}")
failed4 = [k for k, v in checks4.items() if not v]
print(f"\n落地率: {len(checks4) - len(failed4)}/{len(checks4)}")
if failed4:
    print("  ❌ 未落地:", failed4)

