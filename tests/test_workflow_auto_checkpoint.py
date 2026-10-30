"""
WorkflowEngine 自动检查点测试（E8）
====================================
测试 v2.0 新增的 auto_checkpoint 模式：
  - 启动/步进/暂停时自动保存检查点
  - restore() 从检查点恢复
  - 关闭 auto_checkpoint 时不保存
  - checkpoint_restore 工具入口
"""
import sys
import os

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.workflow_engine import (
    WorkflowEngine, WorkflowError,
    execute_workflow_tool, WORKFLOW_FILE, _engine as _global_engine,
)
from tools.checkpoint_manager import CheckpointManager


def _extract_instance_id(result: str) -> str:
    """从 start 结果中提取 instance_id。"""
    for line in result.split("\n"):
        if "实例ID:" in line:
            return line.split("实例ID:")[1].strip()
    return ""


def _setup_engine() -> WorkflowEngine:
    """创建启用了 auto_checkpoint 的引擎并注册测试工作流。"""
    engine = WorkflowEngine(auto_checkpoint=True)
    engine.define(
        name="自动检查点测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )
    return engine


# ── E8.1 启动时自动保存检查点 ──────────────────────────────

def test_auto_checkpoint_on_start():
    """启动工作流时应自动保存检查点。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    assert "已启动" in result
    assert "自动检查点已启用" in result

    instance_id = _extract_instance_id(result)
    assert instance_id

    # 验证检查点已创建
    checkpoints = engine._checkpoint_manager.list(f"wf:{instance_id}")
    assert len(checkpoints) >= 1, f"预期至少1个检查点，实际: {len(checkpoints)}"

    # 验证检查点内容
    cp = engine._checkpoint_manager.load(checkpoints[0]["checkpoint_id"])
    state = cp.get("state", {})
    assert state["workflow_name"] == "自动检查点测试"
    assert state["instance_id"] == instance_id
    assert state["current_node"] == "A"

    print("✅ E8.1 启动检查点: 通过")


# ── E8.2 步进时自动保存检查点 ──────────────────────────────

def test_auto_checkpoint_on_step():
    """每步 step 后应自动保存检查点。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)

    # Step 1: A → B
    engine.step(instance_id, node_result="A完成")
    cps_after_step1 = engine._checkpoint_manager.list(f"wf:{instance_id}")
    assert len(cps_after_step1) >= 2, f"预期至少2个检查点，实际: {len(cps_after_step1)}"

    # 最新检查点应反映 B 为当前节点
    latest = engine._checkpoint_manager.load(cps_after_step1[0]["checkpoint_id"])
    assert latest["state"]["current_node"] == "B"

    # Step 2: B → C
    engine.step(instance_id, node_result="B完成")
    cps_after_step2 = engine._checkpoint_manager.list(f"wf:{instance_id}")
    assert len(cps_after_step2) >= 3
    latest2 = engine._checkpoint_manager.load(cps_after_step2[0]["checkpoint_id"])
    assert latest2["state"]["current_node"] == "C"

    print("✅ E8.2 步进检查点: 通过")


# ── E8.3 暂停时自动保存检查点 ──────────────────────────────

def test_auto_checkpoint_on_pause():
    """暂停时应自动保存检查点。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)

    # 先走一步
    engine.step(instance_id, node_result="A完成")

    # 暂停
    cps_before = engine._checkpoint_manager.list(f"wf:{instance_id}")
    engine.pause(instance_id)
    cps_after = engine._checkpoint_manager.list(f"wf:{instance_id}")

    assert len(cps_after) > len(cps_before), "暂停应创建新检查点"

    # 最新检查点状态应为已暂停
    latest = engine._checkpoint_manager.load(cps_after[0]["checkpoint_id"])
    assert latest["state"]["status"] == "已暂停"

    print("✅ E8.3 暂停检查点: 通过")


# ── E8.4 从检查点恢复 ─────────────────────────────────────

def test_restore_from_checkpoint():
    """从检查点恢复工作流实例。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)

    # 走一步
    engine.step(instance_id, node_result="A完成")

    # 暂停
    engine.pause(instance_id)

    # 创建新引擎模拟进程重启
    engine2 = WorkflowEngine(auto_checkpoint=True)
    engine2.define(
        name="自动检查点测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )

    # 恢复
    result = engine2.restore(instance_id)
    assert "已从检查点恢复" in result
    assert instance_id in result
    assert "B" in result or "1/3" in result or "进度" in result

    # 继续执行
    result = engine2.step(instance_id, node_result="B恢复执行")
    assert "C" in result

    result = engine2.step(instance_id, node_result="C完成")
    assert "已完成" in result

    print("✅ E8.4 恢复并继续: 通过")


# ── E8.5 恢复不存在的检查点 ───────────────────────────────

def test_restore_no_checkpoint():
    """恢复不存在检查点时抛出 WorkflowError。"""
    engine = WorkflowEngine(auto_checkpoint=True)
    try:
        engine.restore("WF-nonexistent-999")
        assert False, "应抛出 WorkflowError"
    except WorkflowError as e:
        assert "未找到" in str(e) or "检查点" in str(e)

    print("✅ E8.5 恢复不存在: 通过")


# ── E8.6 恢复时定义已丢失 ─────────────────────────────────

def test_restore_missing_definition():
    """恢复时工作流定义已删除，抛出 WorkflowError。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)

    # 关键：必须在 engine2 创建之前清空 workflows.json
    # 因为 WorkflowEngine.__init__ → _load() 会从磁盘读取定义到内存
    # 如果在创建后清空，定义已加载到 _definitions 中，清空文件无效
    if WORKFLOW_FILE.is_file():
        WORKFLOW_FILE.write_text('{"definitions":{},"instances":{}}', encoding="utf-8")

    # 创建另一个引擎（不定义工作流，且磁盘上无定义可加载）
    engine2 = WorkflowEngine(auto_checkpoint=True)
    # 刻意不调用 define

    try:
        engine2.restore(instance_id)
        assert False, "应抛出 WorkflowError"
    except WorkflowError as e:
        assert "已丢失" in str(e) or "定义" in str(e)

    print("✅ E8.6 恢复定义丢失: 通过")


# ── E8.7 auto_checkpoint=False 不保存 ─────────────────────

def test_no_auto_checkpoint():
    """关闭 auto_checkpoint 时不应创建检查点。"""
    engine = WorkflowEngine(auto_checkpoint=False)
    engine.define(
        name="无检查点测试",
        nodes='[{"name":"X"},{"name":"Y"}]',
        edges='[{"from_node":"X","to_node":"Y"}]',
        start_node="X",
        end_nodes='["Y"]',
    )
    result = engine.start("无检查点测试")
    assert "自动检查点已启用" not in result

    instance_id = _extract_instance_id(result)
    engine.step(instance_id, node_result="X完成")
    engine.pause(instance_id)

    # 检查点列表应为空（或不存在该任务条目）
    checkpoints = engine._checkpoint_manager.list(f"wf:{instance_id}")
    assert len(checkpoints) == 0, f"关闭自动检查点不应创建检查点，实际: {len(checkpoints)}"

    print("✅ E8.7 关闭自动检查点: 通过")


# ── E8.8 checkpoint_restore 工具入口 ──────────────────────

def test_checkpoint_restore_tool():
    """通过工具入口执行 checkpoint_restore。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)
    engine.step(instance_id, node_result="A完成")
    engine.pause(instance_id)

    # 通过工具入口恢复
    result = execute_workflow_tool({
        "action": "checkpoint_restore",
        "instance_id": instance_id,
    })
    assert "已从检查点恢复" in result

    # 继续步进
    result = execute_workflow_tool({
        "action": "step",
        "instance_id": instance_id,
        "node_result": "B完成",
    })
    assert "C" in result

    print("✅ E8.8 checkpoint_restore 工具: 通过")


# ── E8.9 完整周期：start → step → pause → restore → step → done ──

def test_full_checkpoint_cycle():
    """模拟进程重启的完整恢复周期。"""
    # 第一次会话
    engine1 = _setup_engine()
    result = engine1.start("自动检查点测试")
    instance_id = _extract_instance_id(result)
    engine1.step(instance_id, node_result="A完成")

    # 模拟崩溃/重启：创建新引擎并恢复
    engine2 = WorkflowEngine(auto_checkpoint=True)
    engine2.define(
        name="自动检查点测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )
    restore_result = engine2.restore(instance_id)
    assert "已从检查点恢复" in restore_result

    # 继续
    step_result = engine2.step(instance_id, node_result="B完成(恢复后)")
    assert "C" in step_result

    final = engine2.step(instance_id, node_result="C完成")
    assert "已完成" in final

    # 验证最终状态
    status = engine2.get_status(instance_id)
    assert "已完成" in status
    assert "✅" in status

    print("✅ E8.9 完整恢复周期: 通过")


# ── E8.10 恢复后 checkpoint 内容完整性 ────────────────────

def test_restore_state_integrity():
    """恢复后的实例状态应与保存前一致。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试", initial_state='{"counter": 42, "mode": "test"}')
    instance_id = _extract_instance_id(result)
    engine.step(instance_id, node_result="A结果")

    # 记录状态
    orig = engine._instances[instance_id]
    orig_node_results = dict(orig.node_results)
    orig_state = dict(orig.state)

    # 恢复
    engine2 = WorkflowEngine(auto_checkpoint=True)
    engine2.define(
        name="自动检查点测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )
    engine2.restore(instance_id)
    restored = engine2._instances[instance_id]

    assert restored.current_node == orig.current_node
    assert restored.node_results == orig_node_results
    assert restored.state == orig_state
    assert restored.state["counter"] == 42
    assert restored.state["mode"] == "test"

    print("✅ E8.10 状态完整性: 通过")


# ── E8.11 恢复已完成的工作流 ──────────────────────────────

def test_restore_completed_workflow():
    """恢复一个已完成的工作流实例。"""
    engine = _setup_engine()
    result = engine.start("自动检查点测试")
    instance_id = _extract_instance_id(result)
    engine.step(instance_id, node_result="A完成")
    engine.step(instance_id, node_result="B完成")
    engine.step(instance_id, node_result="C完成")

    # 恢复已完成实例
    engine2 = WorkflowEngine(auto_checkpoint=True)
    engine2.define(
        name="自动检查点测试",
        nodes='[{"name":"A"},{"name":"B"},{"name":"C"}]',
        edges='[{"from_node":"A","to_node":"B"},{"from_node":"B","to_node":"C"}]',
        start_node="A",
        end_nodes='["C"]',
    )
    result = engine2.restore(instance_id)
    assert "已从检查点恢复" in result
    assert engine2._instances[instance_id].status == "已完成"

    print("✅ E8.11 恢复已完成工作流: 通过")


# ── E8.12 auto_checkpoint 开关不影响引擎基本功能 ──────────

def test_auto_checkpoint_backward_compat():
    """auto_checkpoint 开关不影响 define/start/step/pause/resume/status/list/delete。"""
    # 关闭
    engine_off = WorkflowEngine(auto_checkpoint=False)
    engine_off.define(name="兼容测试", nodes='[{"name":"n1"},{"name":"n2"}]',
                      start_node="n1", end_nodes='["n2"]')
    r = engine_off.start("兼容测试")
    iid = _extract_instance_id(r)
    assert iid
    r = engine_off.step(iid, "ok")
    assert "已完成" in r
    r = engine_off.get_status(iid)
    assert "已完成" in r
    r = engine_off.list_workflows()
    assert "兼容测试" in r
    engine_off.delete("兼容测试")

    # 开启
    engine_on = WorkflowEngine(auto_checkpoint=True)
    engine_on.define(name="兼容测试2", nodes='[{"name":"n1"},{"name":"n2"}]',
                     start_node="n1", end_nodes='["n2"]')
    r = engine_on.start("兼容测试2")
    iid2 = _extract_instance_id(r)
    engine_on.pause(iid2)
    engine_on.resume(iid2)
    r = engine_on.step(iid2, "ok")
    assert "已完成" in r
    engine_on.delete("兼容测试2")

    print("✅ E8.12 向后兼容: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 WorkflowEngine 自动检查点测试 (E8)")
    print("=" * 50)
    print()

    test_auto_checkpoint_on_start()
    test_auto_checkpoint_on_step()
    test_auto_checkpoint_on_pause()
    test_restore_from_checkpoint()
    test_restore_no_checkpoint()
    test_restore_missing_definition()
    test_no_auto_checkpoint()
    test_checkpoint_restore_tool()
    test_full_checkpoint_cycle()
    test_restore_state_integrity()
    test_restore_completed_workflow()
    test_auto_checkpoint_backward_compat()

    print()
    print("=" * 50)
    print("🎉 所有 E8 自动检查点测试通过！")
    print("=" * 50)
