"""1.3 契约基线生成：跑测试矩阵并记录通过状态 + 已知问题清单"""
import sys, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TESTS = ROOT / "tests" / "contract"

# 跑测试矩阵（静默模式，取汇总行）
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "test_tool_contracts.py", "-q", "--no-header",
     "-p", "no:cacheprovider", "--tb=no"],
    cwd=str(TESTS), capture_output=True, text=True, timeout=300,
)
tail = [l for l in proc.stdout.strip().splitlines() if l.strip()][-1]
print("测试汇总:", tail)

m = re.search(r"(\d+) passed", tail)
passed = int(m.group(1)) if m else 0
m2 = re.search(r"(\d+) failed", tail)
failed = int(m2.group(1)) if m2 else 0
m3 = re.search(r"(\d+) skipped", tail)
skipped = int(m3.group(1)) if m3 else 0

sys.path.insert(0, str(ROOT))
import agent1

baseline = {
    "_doc": "契约测试基线（步骤1.3产出）。known_issues 为契约测试暴露的真实缺口，供步骤5修复。",
    "generated": "2026-10-30",
    "spec": "tests/contract/SPEC.md",
    "tool_count": len(agent1.ALL_TOOLS),
    "tools": [t["function"]["name"] for t in agent1.ALL_TOOLS],
    "assertions": {
        "C1_schema_compliance": "工具定义符合MCP必填字段与命名规则",
        "C2_param_validation": "6类边界输入满足P1/P2/P3",
        "C3_error_contract": "错误必为已知类型或可识别错误串",
        "C4_no_exception_leak": "任意输入绝不泄漏未包装异常",
        "C5_result_type": "返回值必为 str",
        "C6_large_result": "超阈值必须走摘要路径",
    },
    "latest_run": {"passed": passed, "failed": failed, "skipped": skipped,
                   "summary": tail},
    "known_issues": [
        {"id": "K1", "assertion": "C3", "severity": "中",
         "issue": "7个工具的错误消息前缀不统一（返回'未知操作:/不可用:'而非 ❌ 前缀）",
         "tools": ["run_command", "web_search", "task_tracker", "knowledge",
                   "calculate", "test_runner", "safe_deploy"],
         "fix_in": "步骤5.2"},
        {"id": "K2", "assertion": "C3", "severity": "中",
         "issue": "run_command 失败时返回中性串 '返回码: N'，缺少明确失败标记，模型可能误判为成功",
         "tools": ["run_command"], "fix_in": "步骤5.2"},
        {"id": "K3", "assertion": "C1", "severity": "低",
         "issue": "0/16 工具提供 outputSchema（MCP 规范推荐，提供则结果必须符合）",
         "tools": "all", "fix_in": "步骤2（注册表承载）"},
        {"id": "K4", "assertion": "C1", "severity": "低",
         "issue": "0/16 工具提供 annotations（idempotent/readOnly/destructive 等行为声明）",
         "tools": "all", "fix_in": "步骤2（注册表承载）"},
    ],
    "exemptions": [
        {"tool": "evidence_verifier", "assertion": "C3",
         "reason": "仅接受 report 参数，空串会走正常校验路径而非错误路径"},
    ],
    "next_step": "进入步骤 2（声明式工具注册表），本基线作为改造后的回归对照",
}

out = ROOT / "eval" / "governance" / "contract_baseline.json"
out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n✅ 基线已写入 {out}")
print(f"   工具数: {baseline['tool_count']}")
print(f"   通过/失败/跳过: {passed}/{failed}/{skipped}")
print(f"   已知问题: {len(baseline['known_issues'])} 项")
for k in baseline["known_issues"]:
    print(f"     [{k['id']}] ({k['assertion']}) {k['issue'][:60]}... -> {k['fix_in']}")
