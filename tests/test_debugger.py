"""
DebuggerAgent 单元测试 — 验证调试守护者智能体的完整功能
===========================================================
测试覆盖：
  - 诊断：匹配各种错误类型，返回正确的严重级别和建议
  - 自动修复：针对不同问题类别执行修复策略
  - 快照保存：保存和清理快照文件
  - 健康检查：综合评估系统健康状态
  - 报告生成：完整的工作报告输出
"""

import sys
import os
import json
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.debugger_agent import DebuggerAgent   # ★T2827：切断循环后改为直接导入
from tools.specialist_base import (
    SpecialistRegistry,
    SpecialistError,
    TaskInput,
    SpecialistAgent,
)


_test_snapshot_dir = None


def setup_module():
    """测试前准备：创建临时快照目录。"""
    global _test_snapshot_dir
    _test_snapshot_dir = tempfile.mkdtemp()


def teardown_module():
    """测试后清理。"""
    global _test_snapshot_dir
    if _test_snapshot_dir is not None:
        shutil.rmtree(_test_snapshot_dir, ignore_errors=True)
        _test_snapshot_dir = None


def create_debugger() -> DebuggerAgent:
    """创建并配置 Debugger 实例（使用独立临时快照目录）。"""
    from pathlib import Path
    debugger = DebuggerAgent()
    # 每个测试使用独立的临时目录（必须为 Path 对象）
    debugger._snapshot_dir = Path(tempfile.mkdtemp())
    return debugger


# ── 测试1：基础创建 ─────────────────────────────────────

def test_debugger_creation():
    """测试 DebuggerAgent 的创建和基本属性。"""
    debugger = DebuggerAgent()

    assert debugger.agent_id == "debugger", f"agent_id 应为 debugger: {debugger.agent_id}"
    assert debugger.name == "Debugger", f"name 应为 Debugger: {debugger.name}"
    assert debugger.specialist_type == "debugger", f"specialist_type 应为 debugger: {debugger.specialist_type}"
    assert "debugging" in debugger.capabilities, f"应有 debugging 能力"
    assert "monitoring" in debugger.capabilities, f"应有 monitoring 能力"
    assert "safety_net" in debugger.tools, f"应包含 safety_net 工具"
    assert "self_check" in debugger.tools, f"应包含 self_check 工具"
    
    # 检查快照目录是否创建
    assert debugger._snapshot_dir.exists(), f"快照目录应存在"
    assert len(debugger.DIAGNOSTIC_RULES) >= 9, f"应有至少9条诊断规则"
    assert len(debugger.AUTO_FIX_STRATEGIES) >= 5, f"应有至少5个修复类别"
    
    print("✅ test_debugger_creation: 通过")


# ── 测试2：通过注册表创建 ───────────────────────────────

def test_create_via_registry():
    """测试通过 SpecialistRegistry 创建 Debugger。"""
    agent = SpecialistRegistry.create("debugger")
    assert isinstance(agent, DebuggerAgent), f"应创建为 DebuggerAgent 实例"
    assert agent.specialist_type == "debugger", f"specialist_type 应一致"
    print("✅ test_create_via_registry: 通过")


# ── 测试3：异常诊断 - API超时 ──────────────────────────

def test_diagnose_api_timeout():
    """测试诊断 API 超时错误。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_diag_01",
        description="连接超时: timed out after 30 seconds",
        params={"action": "diagnose", "error": "timed out after 30 seconds"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"诊断应成功: {result.status}"
    output = result.output
    assert isinstance(output, dict), f"输出应为字典"
    
    diagnosis = output.get("diagnosis", {})
    assert diagnosis.get("severity") == "high", f"超时严重级别应为 high: {diagnosis.get('severity')}"
    assert diagnosis.get("category") == "network", f"超时类别应为 network: {diagnosis.get('category')}"
    
    suggestions = output.get("suggestions", [])
    assert len(suggestions) > 0, f"应有修复建议"
    assert any("超时" in s or "timeout" in s.lower() for s in suggestions), f"建议应与超时相关: {suggestions}"
    
    print("✅ test_diagnose_api_timeout: 通过")


# ── 测试4：异常诊断 - 认证错误 ─────────────────────────

def test_diagnose_auth_error():
    """测试诊断 API 认证错误。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_diag_02",
        description="401 Unauthorized: API key is invalid",
        params={"action": "diagnose", "error": "401 Unauthorized: API key is invalid"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"诊断应成功"
    diagnosis = result.output.get("diagnosis", {})
    assert diagnosis.get("severity") == "critical", f"认证错误严重级别应为 critical: {diagnosis.get('severity')}"
    assert diagnosis.get("category") == "auth", f"认证错误类别应为 auth: {diagnosis.get('category')}"
    
    print("✅ test_diagnose_auth_error: 通过")


# ── 测试5：异常诊断 - 速率限制 ────────────────────────

def test_diagnose_rate_limit():
    """测试诊断 API 速率限制错误。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_diag_03",
        description="429 Too Many Requests: rate limit exceeded",
        params={"action": "diagnose", "error": "429 rate limit exceeded"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"诊断应成功"
    diagnosis = result.output.get("diagnosis", {})
    assert diagnosis.get("severity") == "medium", f"速率限制严重级别应为 medium: {diagnosis.get('severity')}"
    assert diagnosis.get("category") == "quota", f"速率限制类别应为 quota: {diagnosis.get('category')}"
    
    print("✅ test_diagnose_rate_limit: 通过")


# ── 测试6：异常诊断 - SSL错误 ──────────────────────────

def test_diagnose_ssl_error():
    """测试诊断 SSL 错误。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_diag_04",
        description="SSL: UNEXPECTED_EOF_WHILE_READING certificate verify failed",
        params={"action": "diagnose", "error": "SSL: UNEXPECTED_EOF_WHILE_READING"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"诊断应成功"
    diagnosis = result.output.get("diagnosis", {})
    assert diagnosis.get("severity") == "high", f"SSL错误严重级别应为 high: {diagnosis.get('severity')}"
    assert diagnosis.get("category") == "network", f"SSL错误类别应为 network: {diagnosis.get('category')}"
    
    suggestions = result.suggestions
    assert any("SSL" in s or "ssl" in s.lower() for s in suggestions), f"建议应与SSL相关: {suggestions}"
    
    print("✅ test_diagnose_ssl_error: 通过")


# ── 测试7：异常诊断 - 未知错误 ────────────────────────

def test_diagnose_unknown_error():
    """测试诊断未知错误（无匹配规则）。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_diag_05",
        description="An completely unknown error that doesn't match any pattern: XYZ123",
        params={"action": "diagnose", "error": "XYZ123 very strange error"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"诊断应成功"
    diagnosis = result.output.get("diagnosis", {})
    assert diagnosis.get("category") == "unknown", f"未知错误类别应为 unknown: {diagnosis.get('category')}"
    assert len(result.suggestions) > 0, f"未知错误也应有建议"
    
    print("✅ test_diagnose_unknown_error: 通过")


# ── 测试8：自动修复 - 网络问题 ────────────────────────

def test_auto_fix_network():
    """测试自动修复网络类问题。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_fix_01",
        description="Connection refused: Unable to connect to API server",
        params={"action": "auto_fix", "error": "Connection refused"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"自动修复应成功"
    output = result.output
    assert output.get("category") == "network", f"修复类别应为 network: {output.get('category')}"
    assert "fixed" in output or "fix_summary" in output, f"应有修复结果"
    
    # 检查修复动作列表
    fix_actions = output.get("fix_actions", [])
    assert len(fix_actions) > 0, f"应有修复动作"
    action_names = [a.get("action", "") for a in fix_actions]
    assert any("重试" in a for a in action_names), f"网络修复应有重试策略: {action_names}"
    
    print("✅ test_auto_fix_network: 通过")


# ── 测试9：自动修复 - 认证问题 ────────────────────────

def test_auto_fix_auth():
    """测试自动修复认证类问题。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_fix_02",
        description="403 Forbidden: Invalid API key",
        params={"action": "auto_fix", "error": "403 Forbidden"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"自动修复应成功"
    output = result.output
    assert output.get("category") == "auth", f"修复类别应为 auth: {output.get('category')}"
    
    fix_actions = output.get("fix_actions", [])
    assert len(fix_actions) > 0, f"认证修复应有动作"
    
    print("✅ test_auto_fix_auth: 通过")


# ── 测试10：自动修复 - 无匹配策略 ─────────────────────

def test_auto_fix_no_strategy():
    """测试无匹配修复策略时的处理。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_fix_03",
        description="Some random error with no matching category",
        params={"action": "auto_fix", "error": "SomeRandomErrorCode"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"应返回结果"
    output = result.output
    # unknown 类别没有修复策略
    if output.get("category") == "unknown":
        assert not output.get("fixed", True), f"未知类别应标记为未修复"
    
    print("✅ test_auto_fix_no_strategy: 通过")


# ── 测试11：快照保存 ──────────────────────────────────

def test_save_snapshot():
    """测试保存系统快照。"""
    debugger = create_debugger()
    
    # 先做一些诊断，让快照有历史数据
    diag_task = TaskInput(
        task_id="T_snap_prep",
        description="API timeout error",
        params={"action": "diagnose", "error": "timed out"},
    )
    debugger.process_task(diag_task)
    
    # 保存快照
    task = TaskInput(
        task_id="T_snap_01",
        description="系统异常 - 测试快照",
        params={
            "action": "snapshot",
            "error": "测试异常场景",
            "context": {"source": "test", "severity": "high"},
        },
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"快照保存应成功"
    output = result.output
    assert output.get("action") == "snapshot", f"动作应为 snapshot"
    assert output.get("snapshot_id", "").startswith("snap_"), f"快照ID格式不对: {output.get('snapshot_id')}"
    
    # 检查文件是否存在
    snapshot_file = output.get("snapshot_file", "")
    assert snapshot_file, f"应有快照文件路径"
    assert os.path.exists(snapshot_file), f"快照文件应存在: {snapshot_file}"
    
    # 验证快照文件内容
    with open(snapshot_file, "r", encoding="utf-8") as f:
        snapshot_data = json.load(f)
    assert "snapshot_id" in snapshot_data, f"快照应有 ID"
    assert "diagnosis_history" in snapshot_data, f"快照应有诊断历史"
    assert "agent_status" in snapshot_data, f"快照应有 Agent 状态"
    assert snapshot_data["reason"] == "测试异常场景", f"快照原因应一致: {snapshot_data['reason']}"
    
    print("✅ test_save_snapshot: 通过")


# ── 测试12：快照清理 ──────────────────────────────────

def test_snapshot_cleanup():
    """测试快照清理机制（只保留最近N个）。"""
    debugger = create_debugger()
    
    # 创建多个快照
    for i in range(5):
        task = TaskInput(
            task_id=f"T_snap_clean_{i}",
            description=f"测试快照 {i}",
            params={
                "action": "snapshot",
                "error": f"测试快照 {i}",
            },
        )
        debugger.process_task(task)
    
    # 获取当前快照文件列表
    snapshots = list(debugger._snapshot_dir.glob("snap_*.json"))
    
    # 手动调用清理（保留3个）
    debugger._cleanup_old_snapshots(keep=3)
    
    remaining = list(debugger._snapshot_dir.glob("snap_*.json"))
    assert len(remaining) <= 3, f"清理后最多应保留3个快照: {len(remaining)}"
    
    print("✅ test_snapshot_cleanup: 通过")


# ── 测试13：健康检查 ──────────────────────────────────

def test_health_check():
    """测试系统健康检查功能。"""
    debugger = create_debugger()
    
    # 初始状态（无诊断记录）
    task = TaskInput(
        task_id="T_health_01",
        description="健康检查",
        params={"action": "health_check"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"健康检查应成功"
    output = result.output
    assert output.get("action") == "health_check", f"动作应为 health_check"
    assert output.get("health_status") in ("healthy", "fair", "degraded", "critical"), f"应有健康状态"
    assert isinstance(output.get("health_score"), (int, float)), f"健康评分应为数值"
    assert 0 <= output.get("health_score", -1) <= 100, f"健康评分应在0-100之间"
    
    # 添加一些诊断记录后再检查
    for err in ["API timeout", "connection refused", "SSL error"]:
        diag_task = TaskInput(
            task_id=f"T_health_prep_{err[:5]}",
            description=err,
            params={"action": "diagnose", "error": err},
        )
        debugger.process_task(diag_task)
    
    task2 = TaskInput(
        task_id="T_health_02",
        description="有诊断记录后的健康检查",
        params={"action": "health_check"},
    )
    result2 = debugger.process_task(task2)
    
    assert result2.status == "done", f"第二次健康检查应成功"
    output2 = result2.output
    
    # 统计信息应包含诊断和修复次数
    stats = output2.get("statistics", {})
    assert stats.get("total_diagnoses", 0) >= 3, f"应有至少3次诊断: {stats.get('total_diagnoses')}"
    
    print("✅ test_health_check: 通过")


# ── 测试14：报告生成 ──────────────────────────────────

def test_generate_report():
    """测试 Debugger 完整工作报告生成。"""
    debugger = create_debugger()
    
    # 生成初始报告（无数据）
    task = TaskInput(
        task_id="T_rpt_01",
        description="生成报告",
        params={"action": "report"},
    )
    result = debugger.process_task(task)
    
    assert result.status == "done", f"报告生成应成功"
    output = result.output
    report_text = output.get("report_text", "")
    assert "Debugger Agent 工作报告" in report_text, f"报告应有标题: {report_text[:50]}"
    
    print("✅ test_generate_report: 通过")


# ── 测试15：完整工作流 ────────────────────────────────

def test_complete_workflow():
    """
    测试 Debugger 完整工作流。
    
    场景模拟：API 调用超时 → 诊断 → 自动修复 → 快照 → 健康检查 → 报告
    """
    debugger = create_debugger()
    
    # 步骤1: 模拟 API 超时错误
    error_text = "HTTPSConnectionPool: Read timed out. (read timeout=120)"
    diag_task = TaskInput(
        task_id="T_flow_01",
        description=error_text,
        params={"action": "diagnose", "error": error_text},
    )
    diag_result = debugger.process_task(diag_task)
    assert diag_result.status == "done", "步骤1: 诊断应成功"
    assert diag_result.output.get("diagnosis", {}).get("category") in ("network", "api"), \
        f"步骤1: 应为 network/api 类别: {diag_result.output.get('diagnosis', {}).get('category')}"
    
    # 步骤2: 自动修复
    fix_task = TaskInput(
        task_id="T_flow_02",
        description=error_text,
        params={"action": "auto_fix", "error": error_text},
    )
    fix_result = debugger.process_task(fix_task)
    assert fix_result.status == "done", "步骤2: 自动修复应成功"
    
    # 步骤3: 保存快照
    snap_task = TaskInput(
        task_id="T_flow_03",
        description="API超时 - 工作流测试快照",
        params={
            "action": "snapshot",
            "error": "API超时 - 工作流测试",
            "context": {"workflow_step": 3},
        },
    )
    snap_result = debugger.process_task(snap_task)
    assert snap_result.status == "done", "步骤3: 快照应成功"
    assert os.path.exists(snap_result.output.get("snapshot_file", "")), "步骤3: 快照文件应存在"
    
    # 步骤4: 健康检查
    health_task = TaskInput(
        task_id="T_flow_04",
        description="工作流测试健康检查",
        params={"action": "health_check"},
    )
    health_result = debugger.process_task(health_task)
    assert health_result.status == "done", "步骤4: 健康检查应成功"
    assert health_result.output.get("statistics", {}).get("total_diagnoses", 0) >= 1, \
        "步骤4: 应有诊断记录"
    
    # 步骤5: 生成报告
    rpt_task = TaskInput(
        task_id="T_flow_05",
        description="工作流测试报告",
        params={"action": "report"},
    )
    rpt_result = debugger.process_task(rpt_task)
    assert rpt_result.status == "done", "步骤5: 报告应成功"
    assert rpt_result.output.get("total_diagnoses", 0) >= 1, "步骤5: 报告应有诊断统计"
    assert rpt_result.output.get("total_fixes", 0) >= 1, "步骤5: 报告应有修复统计"
    assert rpt_result.output.get("snapshot_count", 0) >= 1, "步骤5: 报告应有快照统计"
    
    print("✅ test_complete_workflow: 通过")


# ── 测试16：无效操作 ──────────────────────────────────

def test_invalid_action():
    """测试无效操作的处理。"""
    debugger = create_debugger()
    
    task = TaskInput(
        task_id="T_invalid",
        description="无效操作",
        params={"action": "nonexistent_action"},
    )
    result = debugger.process_task(task)
    # 无效操作应该返回 failed 状态
    assert result.status == "failed", f"无效操作应返回 failed: {result.status}"
    assert "未知" in result.error, f"错误信息应提示未知操作: {result.error}"
    
    print("✅ test_invalid_action: 通过")


# ── 测试17：大规模诊断 ────────────────────────────────

def test_bulk_diagnostics():
    """测试大量诊断时的稳定性和历史记录管理。"""
    debugger = create_debugger()
    
    errors = [
        ("API timeout", "timed out"),
        ("Connection refused", "connection refused"),
        ("401 Unauthorized", "401"),
        ("429 rate limit", "429"),
        ("JSON decode error", "JSONDecodeError"),
        ("SSL error", "SSL: certificate verify failed"),
        ("Memory error", "MemoryError"),
        ("Tool not found", "unknown tool"),
        ("Parameter error", "参数错误"),
        ("Empty response", "empty content"),
    ]
    
    for i, (desc, err_text) in enumerate(errors * 5):  # 50次诊断
        task = TaskInput(
            task_id=f"T_bulk_{i:03d}",
            description=desc,
            params={"action": "diagnose", "error": err_text},
        )
        result = debugger.process_task(task)
        assert result.status == "done", f"批量诊断 #{i} 应成功: {result.status}"
    
    # 确保诊断历史不超过限制
    assert len(debugger._diagnosis_history) <= 50, f"诊断历史不应超过50条: {len(debugger._diagnosis_history)}"
    
    # 健康检查应能正常处理大量数据
    health_task = TaskInput(
        task_id="T_bulk_health",
        description="大量诊断后健康检查",
        params={"action": "health_check"},
    )
    health_result = debugger.process_task(health_task)
    assert health_result.status == "done", "批量后健康检查应成功"
    assert health_result.output.get("statistics", {}).get("total_diagnoses", 0) >= 50, \
        f"应有50次诊断: {health_result.output.get('statistics', {}).get('total_diagnoses', 0)}"
    
    print("✅ test_bulk_diagnostics: 通过")


# ── 运行所有测试 ──────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🐛 DebuggerAgent 单元测试")
    print("=" * 60)
    
    tests = [
        test_debugger_creation,
        test_create_via_registry,
        test_diagnose_api_timeout,
        test_diagnose_auth_error,
        test_diagnose_rate_limit,
        test_diagnose_ssl_error,
        test_diagnose_unknown_error,
        test_auto_fix_network,
        test_auto_fix_auth,
        test_auto_fix_no_strategy,
        test_save_snapshot,
        test_snapshot_cleanup,
        test_health_check,
        test_generate_report,
        test_complete_workflow,
        test_invalid_action,
        test_bulk_diagnostics,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"❌ {test.__name__}: 失败 — {exc}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"📊 结果: {passed}/{len(tests)} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed > 0:
        exit(1)
    else:
        print("🎉 所有测试通过！")
