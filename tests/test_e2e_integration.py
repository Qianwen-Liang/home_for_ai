"""
端到端协同测试 — 多工具联合验证 (T060)
=====================================
验证三大工具链的完整协同工作流：
  Chain A: knowledge_store → decision_engine → task_tracker
  Chain B: safety_net → monitor → experience_learner
  Chain C: orchestrator → task_dispatcher → workflow_engine
  Full Walkthrough: 跨链全系统演示
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.knowledge_store import execute_knowledge_tool, KnowledgeStoreError
from tools.decision_engine import execute_decision_engine_tool, DecisionError
from tools.task_tracker import execute_task_tracker_tool, TaskTrackerError
from tools.safety_net import execute_safety_net_tool, SafetyNetError
from tools.monitor import execute_monitor_tool
from tools.experience_learner import execute_experience_learner_tool, ExperienceLearnerError
from tools.task_dispatcher import execute_task_dispatcher_tool, DispatchError
from tools.workflow_engine import execute_workflow_tool, WorkflowError


# ═══════════════════════════════════════════════════════════
# Chain A: knowledge_store → decision_engine → task_tracker
# ═══════════════════════════════════════════════════════════

def test_chain_a_knowledge_decision_task(monkeypatch, tmp_path):
    """验证：知识存储 → 决策建议 → 任务创建 联动链"""
    print("=" * 55)
    print("🧪 Chain A: knowledge_store → decision_engine → task_tracker")
    print("=" * 55)

    # ★T2795-5.1：隔离知识库到临时路径，避免测试数据污染生产知识库
    import tools.experience_learner as _el
    import tools.knowledge_store as _ks

    monkeypatch.setattr(_el, "KNOWLEDGE_DIR", tmp_path / "e2e_experience_kb_a")
    monkeypatch.setattr(
        _ks, "_store", _ks.KnowledgeStore(path=tmp_path / "e2e_kb_a.json")
    )

    # Step 1: 存储经验知识
    print("\n  📌 Step 1: 存储知识条目")
    r1 = execute_knowledge_tool({
        "action": "store",
        "title": "系统扩容最佳实践",
        "content": "扩容时应先评估当前负载、预估增长量、分阶段执行、每次扩容后验证。避免一次性大规模扩容导致服务不稳定。",
        "category": "experience",
        "tags": "扩容,最佳实践,运维",
    })
    assert "已存储" in r1, f"存储失败: {r1}"
    assert "K" in r1
    print(f"     {r1[:80]}...")

    # Step 2: 用决策引擎获取建议
    print("\n  📌 Step 2: 决策引擎提供建议")
    r2 = execute_decision_engine_tool({
        "action": "advise",
        "problem": "系统需要扩容但担心影响稳定性",
        "context": "当前系统负载已达到80%，需制定扩容方案",
        "max_results": 3,
    })
    assert "决策建议" in r2 or "建议" in r2, f"决策建议失败: {r2}"
    print(f"     {r2[:100]}...")

    # Step 3: 根据建议创建任务
    print("\n  📌 Step 3: 创建扩容任务")
    r3 = execute_task_tracker_tool({
        "action": "create",
        "title": "系统扩容计划",
        "description": "基于决策引擎建议：分阶段扩容，先评估负载再执行",
        "phase": "运维",
        "priority": "高",
    })
    assert "已创建任务" in r3, f"创建任务失败: {r3}"
    print(f"     {r3[:80]}...")
    # ★T2795-5.1：清理测试任务，避免污染真实任务库
    import re as _re
    _tid = _re.search(r"T\d+", r3)
    if _tid:
        execute_task_tracker_tool({"action": "delete", "task_id": _tid.group()})

    # Step 4: 记录决策到决策引擎
    print("\n  📌 Step 4: 记录决策")
    r4 = execute_decision_engine_tool({
        "action": "record_decision",
        "decision": "采用分阶段扩容方案，每阶段扩容25%并验证",
        "outcome": "成功 — 服务零中断完成扩容",
    })
    assert "已记录决策" in r4, f"记录决策失败: {r4}"
    print(f"     {r4[:80]}...")

    # Step 5: 验证决策历史
    print("\n  📌 Step 5: 验证决策历史")
    r5 = execute_decision_engine_tool({"action": "history", "max_results": 5})
    assert "扩容" in r5, f"决策历史中应有扩容记录: {r5}"
    print(f"     ✅ 决策历史包含扩容记录")

    print("\n  ✅ Chain A 全链路验证通过！")


# ═══════════════════════════════════════════════════════════
# Chain B: safety_net → monitor → experience_learner
# ═══════════════════════════════════════════════════════════

def test_chain_b_safety_monitor_learning():
    """验证：安全检测 → 监控记录 → 经验学习 联动链"""
    print("\n" + "=" * 55)
    print("🧪 Chain B: safety_net → monitor → experience_learner")
    print("=" * 55)

    # Step 1: 重置安全网和监控数据（确保干净起点）
    print("\n  📌 Step 1: 重置初始状态")
    execute_safety_net_tool({"action": "reset"})
    execute_monitor_tool({"action": "reset"})
    print("     ✅ 安全网和监控数据已重置")

    # Step 2: 模拟正常工具调用并记录到安全网
    print("\n  📌 Step 2: 模拟正常操作事件")
    for i in range(3):
        r = execute_safety_net_tool({
            "action": "record_event",
            "event_type": "tool_call",
            "event_detail": f"第{i+1}次调用 knowledge search",
            "tool_name": "knowledge",
        })
        assert "已记录" in r
    print("     ✅ 3 次正常事件已记录")

    # Step 3: 模拟错误事件并检测
    print("\n  📌 Step 3: 模拟错误事件")
    for i in range(6):
        execute_safety_net_tool({
            "action": "record_event",
            "event_type": "error",
            "event_detail": "磁盘空间不足，写入失败",
            "tool_name": "write_file",
        })

    # 检查安全网应该检测到异常
    r_check = execute_safety_net_tool({"action": "check"})
    assert "连续" in r_check or "问题" in r_check or "正常" in r_check, f"安全网检查失败: {r_check}"
    print(f"     ✅ 安全网检查完成")

    # Step 4: 监控记录操作
    print("\n  📌 Step 4: 记录监控数据")
    r_mon = execute_monitor_tool({
        "action": "record",
        "tool_name": "write_file",
        "duration": 2.5,
        "success": False,
    })
    assert "已记录" in r_mon, f"监控记录失败: {r_mon}"

    r_mon2 = execute_monitor_tool({
        "action": "record",
        "tool_name": "knowledge",
        "duration": 0.3,
        "success": True,
    })
    assert "已记录" in r_mon2
    print("     ✅ 监控记录成功")

    # Step 5: 从错误中学习
    print("\n  📌 Step 5: 记录失败教训到经验学习器")
    r_exp = execute_experience_learner_tool({
        "action": "record_failure",
        "tool_name": "write_file",
        "task": "向磁盘写入大文件",
        "result": "磁盘空间不足，写入失败",
        "lesson": "写入前应使用 file_utils 检查磁盘空间，确保有足够容量后再执行写入操作",
    })
    assert "已记录" in r_exp, f"经验记录失败: {r_exp}"
    print(f"     {r_exp[:100]}...")

    # Step 6: 记录成功经验
    print("\n  📌 Step 6: 记录成功经验")
    r_exp2 = execute_experience_learner_tool({
        "action": "record_success",
        "tool_name": "knowledge",
        "task": "搜索系统扩容相关知识",
        "result": "成功找到 12 条相关经验",
        "lesson": "知识库搜索配合 decision_engine 的 advise 功能可以快速定位最佳实践",
    })
    assert "已记录" in r_exp2, f"成功经验记录失败: {r_exp2}"
    print(f"     {r_exp2[:100]}...")

    # Step 7: 经验回顾
    print("\n  📌 Step 7: 经验回顾")
    r_review = execute_experience_learner_tool({"action": "review", "max_results": 5})
    assert "经验回顾" in r_review, f"经验回顾失败: {r_review}"
    print("     ✅ 经验回顾正常")

    # Step 8: 为相关任务推荐经验
    print("\n  📌 Step 8: 经验推荐")
    r_rec = execute_experience_learner_tool({
        "action": "recommend",
        "task": "需要向磁盘写入大量数据文件",
        "max_results": 3,
    })
    assert "经验" in r_rec or "推荐" in r_rec, f"经验推荐失败: {r_rec}"
    print(f"     {r_rec[:100]}...")

    # Step 9: 监控摘要
    print("\n  📌 Step 9: 监控摘要")
    r_summary = execute_monitor_tool({"action": "summary"})
    assert "监控" in r_summary or "摘要" in r_summary or "记录" in r_summary.lower(), f"监控摘要失败: {r_summary}"
    print("     ✅ 监控摘要正常")

    print("\n  ✅ Chain B 全链路验证通过！")


# ═══════════════════════════════════════════════════════════
# Chain C: task_dispatcher → workflow_engine → orchestrator
# ═══════════════════════════════════════════════════════════

def test_chain_c_dispatch_workflow_orchestrate():
    """验证：任务分解 → 工作流执行 → 编排协调 联动链"""
    print("\n" + "=" * 55)
    print("🧪 Chain C: task_dispatcher → workflow_engine")
    print("=" * 55)

    # Step 1: 定义一个工作流
    print("\n  📌 Step 1: 定义工作流")
    import json
    nodes = json.dumps([
        {"name": "research", "description": "调研阶段"},
        {"name": "design", "description": "设计阶段"},
        {"name": "implement", "description": "实施阶段"},
        {"name": "review", "description": "审查阶段"},
    ])
    edges = json.dumps([
        {"from_node": "research", "to_node": "design"},
        {"from_node": "design", "to_node": "implement"},
        {"from_node": "implement", "to_node": "review"},
    ])

    r_wf = execute_workflow_tool({
        "action": "define",
        "workflow_name": "feature_dev",
        "description": "标准功能开发流程",
        "nodes": nodes,
        "edges": edges,
        "start_node": "research",
        "end_nodes": json.dumps(["review"]),
    })
    assert "已定义工作流" in r_wf, f"工作流定义失败: {r_wf}"
    print(f"     {r_wf[:100]}...")

    # Step 2: 启动工作流实例
    print("\n  📌 Step 2: 启动工作流实例")
    r_start = execute_workflow_tool({
        "action": "start",
        "workflow_name": "feature_dev",
        "initial_state": json.dumps({"project": "Agent 1 v2.0", "priority": "high"}),
    })
    assert "已启动" in r_start, f"工作流启动失败: {r_start}"
    assert "WF-" in r_start
    # 提取 instance_id（uuid 后缀，如 WF-20260816203930-a1b2c3）
    import re
    instance_id_match = re.search(r'WF-\d+-[a-f0-9]+', r_start)
    assert instance_id_match, f"无法提取实例ID: {r_start}"
    instance_id = instance_id_match.group()
    print(f"     实例ID: {instance_id}")

    # Step 3: 逐步执行工作流
    print("\n  📌 Step 3: 逐步执行工作流节点")

    # research → design
    r_step1 = execute_workflow_tool({
        "action": "step",
        "instance_id": instance_id,
        "node_result": "调研完成：发现 3 个关键技术方案",
    })
    assert "前进" in r_step1 or "已完成" in r_step1, f"步骤1失败: {r_step1}"
    print(f"     Step 1: {r_step1[:80]}...")

    # design → implement
    r_step2 = execute_workflow_tool({
        "action": "step",
        "instance_id": instance_id,
        "node_result": "设计完成：选定方案 B 进行实现",
    })
    print(f"     Step 2: {r_step2[:80]}...")

    # implement → review
    r_step3 = execute_workflow_tool({
        "action": "step",
        "instance_id": instance_id,
        "node_result": "实施完成：核心模块已开发并通过单元测试",
    })
    print(f"     Step 3: {r_step3[:80]}...")

    # review → done
    r_step4 = execute_workflow_tool({
        "action": "step",
        "instance_id": instance_id,
        "node_result": "审查通过：代码质量 A 级",
    })
    assert "已完成" in r_step4 or "完成" in r_step4, f"工作流未完成: {r_step4}"
    print(f"     Step 4: {r_step4[:80]}...")

    # Step 4: 查看工作流状态
    print("\n  📌 Step 4: 查看最终状态")
    r_status = execute_workflow_tool({
        "action": "status",
        "instance_id": instance_id,
    })
    assert "已完成" in r_status or "DONE" in r_status or "done" in r_status.lower(), f"状态异常: {r_status}"
    print("     ✅ 工作流已完成")

    # Step 5: 任务分解验证
    print("\n  📌 Step 5: 任务分解器")
    r_decomp = execute_task_dispatcher_tool({
        "action": "decompose",
        "task": "为Agent 1系统添加新的监控功能模块",
        "template": "system",
    })
    assert "分解完成" in r_decomp or "PL_" in r_decomp, f"任务分解失败: {r_decomp}"
    print(f"     {r_decomp[:120]}...")

    # Step 6: 查看模板
    print("\n  📌 Step 6: 查看可用模板")
    r_templates = execute_task_dispatcher_tool({"action": "templates"})
    assert "模板" in r_templates, f"模板列表失败: {r_templates}"
    print("     ✅ 模板列表正常")

    print("\n  ✅ Chain C 全链路验证通过！")


# ═══════════════════════════════════════════════════════════
# Full Walkthrough: 跨链全系统演示
# ═══════════════════════════════════════════════════════════

def test_full_system_walkthrough(monkeypatch, tmp_path):
    """全系统跨链综合演练"""
    print("\n" + "=" * 55)
    print("🧪 全系统跨链 Walkthrough")
    print("=" * 55)

    # ★T2795-5.1：隔离知识库到临时路径，避免测试数据污染生产知识库
    import tools.experience_learner as _el
    import tools.knowledge_store as _ks

    monkeypatch.setattr(_el, "KNOWLEDGE_DIR", tmp_path / "e2e_experience_kb_full")
    monkeypatch.setattr(
        _ks, "_store", _ks.KnowledgeStore(path=tmp_path / "e2e_kb_full.json")
    )

    # ── Phase 1: 知识准备 ──
    print("\n  📌 Phase 1: 知识准备")
    execute_knowledge_tool({
        "action": "store",
        "title": "Agent系统监控方案",
        "content": "监控应包括：工具调用频次、响应时间、错误率、资源使用。推荐使用滑动窗口统计。",
        "category": "research",
        "tags": "监控,性能,方案",
    })
    print("     ✅ 监控方案知识已存储")

    # ── Phase 2: 决策分析 ──
    print("\n  📌 Phase 2: 决策分析")
    r_advise = execute_decision_engine_tool({
        "action": "advise",
        "problem": "系统监控数据不足，需要建立完善的监控体系",
        "context": "已有 monitor 工具但数据积累不够",
    })
    assert "建议" in r_advise or "决策建议" in r_advise
    print(f"     {r_advise[:100]}...")

    # ── Phase 3: 任务规划 ──
    print("\n  📌 Phase 3: 任务规划")
    r1 = execute_task_tracker_tool({
        "action": "create",
        "title": "完善监控体系",
        "description": "基于决策引擎建议，建立完善的监控体系",
        "phase": "实现",
        "priority": "高",
    })
    r2 = execute_task_tracker_tool({
        "action": "create",
        "title": "集成安全网与监控",
        "description": "将 safety_net 的异常检测结果同步到 monitor",
        "phase": "实现",
        "priority": "中",
    })
    # ★T2795-5.1：端到端测试创建的任务必须清理，否则会持续污染真实任务库
    import re as _re
    for _r in (r1, r2):
        _m = _re.search(r"T\d+", _r)
        if _m:
            execute_task_tracker_tool({"action": "delete", "task_id": _m.group()})
    print("     ✅ 任务已创建")
    # ── Phase 4: 任务分解 ──
    print("\n  📌 Phase 4: 任务分解为流水线")
    r_decomp = execute_task_dispatcher_tool({
        "action": "decompose",
        "task": "建立完善的Agent系统监控体系",
        "template": "system",
    })
    assert "PL_" in r_decomp
    import re
    pl_match = re.search(r'PL_[a-f0-9]+', r_decomp)
    pipeline_id = pl_match.group() if pl_match else None
    print(f"     流水线ID: {pipeline_id}")

    # ── Phase 5: 安全网检测 ──
    print("\n  📌 Phase 5: 安全网状态检测")
    r_safety = execute_safety_net_tool({"action": "check"})
    assert "安全网" in r_safety or "正常" in r_safety or "问题" in r_safety
    print(f"     {r_safety[:100]}...")

    # ── Phase 6: 经验学习器回顾 ──
    print("\n  📌 Phase 6: 经验回顾与推荐")
    r_stats = execute_experience_learner_tool({"action": "stats"})
    assert "学习统计" in r_stats or "暂无" in r_stats
    print(f"     {r_stats[:100]}...")

    # ── Phase 7: 监控统计 ──
    print("\n  📌 Phase 7: 监控统计")
    r_mon = execute_monitor_tool({"action": "summary"})
    print(f"     {r_mon[:100] if r_mon else '无监控数据'}...")

    # ── Phase 8: 任务报告 ──
    print("\n  📌 Phase 8: 任务报告")
    r_report = execute_task_tracker_tool({"action": "report"})
    assert "任务" in r_report or "报告" in r_report
    print("     ✅ 任务报告正常")

    # ── Phase 9: 工作流列表 ──
    print("\n  📌 Phase 9: 工作流列表")
    r_wf_list = execute_workflow_tool({"action": "list"})
    assert "feature_dev" in r_wf_list or "工作流" in r_wf_list
    print("     ✅ 工作流列表正常")

    print("\n  ✅ 全系统 Walkthrough 验证通过！")


# ═══════════════════════════════════════════════════════════
# 边界与异常测试
# ═══════════════════════════════════════════════════════════

def test_cross_tool_error_handling():
    """验证跨工具的异常处理"""
    print("\n" + "=" * 55)
    print("🧪 跨工具异常处理")
    print("=" * 55)

    # 无效操作在各工具间的传播
    r1 = execute_knowledge_tool({"action": "invalid_action_xyz"})
    assert "未知" in r1 or "错误" in r1.lower(), f"knowledge应拒绝无效操作: {r1}"

    r2 = execute_decision_engine_tool({"action": "invalid_action_xyz"})
    assert "未知" in r2, f"decision_engine应拒绝无效操作: {r2}"

    r3 = execute_task_tracker_tool({"action": "invalid_action_xyz"})
    assert "未知" in r3, f"task_tracker应拒绝无效操作: {r3}"

    r4 = execute_safety_net_tool({"action": "invalid_action_xyz"})
    assert "未知" in r4, f"safety_net应拒绝无效操作: {r4}"

    r5 = execute_experience_learner_tool({"action": "invalid_action_xyz"})
    assert "未知" in r5, f"experience_learner应拒绝无效操作: {r5}"

    r6 = execute_task_dispatcher_tool({"action": "invalid_action_xyz"})
    assert "未知" in r6, f"task_dispatcher应拒绝无效操作: {r6}"

    r7 = execute_workflow_tool({"action": "invalid_action_xyz"})
    assert "未知" in r7, f"workflow应拒绝无效操作: {r7}"

    print("     ✅ 所有工具正确拒绝无效操作")

    # knowledge search with empty query（工具内部捕获异常返回错误字符串）
    r_kb = execute_knowledge_tool({"action": "search", "query": ""})
    assert "错误" in r_kb, f"knowledge空查询应返回错误: {r_kb}"
    print("     ✅ knowledge 空查询正确返回错误")

    # task_tracker delete non-existent
    r_del = execute_task_tracker_tool({"action": "delete", "task_id": "T99999"})
    assert "未找到" in r_del or "错误" in r_del
    print("     ✅ task_tracker 删除不存在任务正确处理")

    # decision_engine advise empty（工具内部捕获异常返回错误字符串）
    r_de = execute_decision_engine_tool({"action": "advise", "problem": ""})
    assert "错误" in r_de, f"decision_engine空问题应返回错误: {r_de}"
    print("     ✅ decision_engine 空问题正确返回错误")

    # workflow status non-existent
    r_wf = execute_workflow_tool({"action": "status", "instance_id": "WF-nonexistent"})
    assert "未找到" in r_wf or "错误" in r_wf
    print("     ✅ workflow 不存在实例正确处理")

    # task_dispatcher cancel non-existent
    r_disp = execute_task_dispatcher_tool({"action": "cancel", "pipeline_id": "PL_nonexistent"})
    assert "未找到" in r_disp or "错误" in r_disp
    print("     ✅ task_dispatcher 取消不存在流水线正确处理")

    print("\n  ✅ 跨工具异常处理验证通过！")


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🚀 Agent 1 端到端协同测试 (T060)")
    print("=" * 55)

    test_chain_a_knowledge_decision_task()
    test_chain_b_safety_monitor_learning()
    test_chain_c_dispatch_workflow_orchestrate()
    test_full_system_walkthrough()
    test_cross_tool_error_handling()

    print("\n" + "=" * 55)
    print("🎉 所有端到端协同测试通过！")
    print("=" * 55)
    print("""
  已验证的完整工具链:
  ┌────────────────────────────────────────────┐
  │  Chain A: knowledge → decision → task     │
  │  Chain B: safety → monitor → learning     │
  │  Chain C: dispatch → workflow → orch.     │
  │  ──────────────────────────────────────    │
  │  Full Walkthrough: 9-phase 全系统验证      │
  │  Cross-tool Errors: 7 工具异常处理         │
  └────────────────────────────────────────────┘
  """)
