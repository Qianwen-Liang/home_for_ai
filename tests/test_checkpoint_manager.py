"""
Checkpoint Manager 单元测试（v2.0 — 对齐源码 API）
================================================
测试 CheckpointManager 的所有公共方法及工具入口。
"""
import sys
import os

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    # __file__ 在 exec() 沙箱中未定义
    sys.path.insert(0, os.getcwd())

from tools.checkpoint_manager import (
    CheckpointManager, CheckpointError,
    TOOL_DEFINITION, execute_checkpoint_tool,
)

# 使用独立实例，避免与持久化数据污染
_mgr = CheckpointManager()


def test_save_and_load():
    """保存并加载检查点 — 核心路径"""
    cp_id = _mgr.save(task_id="ut_save_load", phase="init", state={"key": "value"})
    assert cp_id.startswith("cp_ut_save_load_"), f"意外 ID: {cp_id}"

    data = _mgr.load(cp_id)
    assert data["checkpoint_id"] == cp_id
    assert data["task_id"] == "ut_save_load"
    assert data["phase"] == "init"
    assert data["state"]["key"] == "value"
    print("✅ save + load: 通过")


def test_save_with_metadata():
    """保存时附带元数据"""
    cp_id = _mgr.save(
        task_id="ut_meta", phase="start",
        state={"x": 1}, metadata={"author": "test"},
    )
    data = _mgr.load(cp_id)
    assert data["metadata"]["author"] == "test"
    print("✅ save + metadata: 通过")


def test_list_all():
    """列出所有检查点 — 返回 list[dict]"""
    _mgr.save(task_id="ut_list_all", phase="a", state={})
    cps = _mgr.list()
    assert isinstance(cps, list)
    assert len(cps) >= 1
    # 检查返回结构
    assert "checkpoint_id" in cps[0]
    assert "task_id" in cps[0]
    assert "phase" in cps[0]
    print("✅ list() 全部: 通过")


def test_list_by_task():
    """按任务筛选检查点"""
    _mgr.save(task_id="ut_filter", phase="phase1", state={})
    _mgr.save(task_id="ut_filter", phase="phase2", state={})
    _mgr.save(task_id="ut_other", phase="x", state={})

    cps = _mgr.list(task_id="ut_filter")
    assert all(cp["task_id"] == "ut_filter" for cp in cps), "筛选结果包含其他任务"
    assert len(cps) >= 2
    print("✅ list(task_id=...) 筛选: 通过")


def test_rollback():
    """回滚到指定阶段 — 返回 state dict"""
    _mgr.save(task_id="ut_rollback", phase="before", state={"v": 1})
    _mgr.save(task_id="ut_rollback", phase="after", state={"v": 2})

    state = _mgr.rollback(task_id="ut_rollback", target_phase="before")
    assert isinstance(state, dict)
    assert state["v"] == 1
    print("✅ rollback: 通过")


def test_rollback_nonexistent_phase():
    """回滚到不存在的阶段 — 应抛出 CheckpointError"""
    _mgr.save(task_id="ut_rollback_ne", phase="only", state={})
    try:
        _mgr.rollback(task_id="ut_rollback_ne", target_phase="nowhere")
        assert False, "应该抛出异常"
    except CheckpointError as e:
        assert "未找到阶段" in str(e)
    print("✅ rollback 不存在阶段: 通过")


def test_rollback_no_task():
    """回滚不存在的任务 — 应抛出 CheckpointError"""
    try:
        _mgr.rollback(task_id="ut_never_existed", target_phase="x")
        assert False, "应该抛出异常"
    except CheckpointError:
        pass
    print("✅ rollback 无任务: 通过")


def test_delete_task():
    """删除任务的所有检查点 — 返回 int"""
    _mgr.save(task_id="ut_delete", phase="a", state={})
    _mgr.save(task_id="ut_delete", phase="b", state={})

    deleted = _mgr.delete_task(task_id="ut_delete")
    assert isinstance(deleted, int)
    assert deleted >= 2

    # 确认已删除
    cps = _mgr.list(task_id="ut_delete")
    assert len(cps) == 0
    print("✅ delete_task: 通过")


def test_clean_all():
    """清理过期检查点 — 返回 int"""
    _mgr.save(task_id="ut_clean", phase="x", state={})
    cleaned = _mgr.clean_all(max_age_days=0)  # 0天 = 清理所有
    assert isinstance(cleaned, int)
    print("✅ clean_all: 通过")


def test_load_nonexistent():
    """加载不存在的检查点 — 应抛出 CheckpointError"""
    try:
        _mgr.load("cp_nonexistent_99999999_000000")
        assert False, "应该抛出异常"
    except CheckpointError:
        pass
    print("✅ load 不存在: 通过")


def test_save_empty_task_id():
    """空 task_id 可以保存（源码未做校验）"""
    cp_id = _mgr.save(task_id="", phase="x", state={})
    assert cp_id.startswith("cp__")
    print("✅ save 空task_id: 通过")


# ── 工具入口测试 ───────────────────────────────────────


def test_tool_definition():
    """工具定义完整性"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "checkpoint"
    params = TOOL_DEFINITION["function"]["parameters"]["properties"]
    assert "action" in params
    actions = params["action"]["enum"]
    assert "save" in actions
    assert "load" in actions
    assert "list" in actions
    assert "rollback" in actions
    assert "delete_task" in actions
    assert "clean_all" in actions
    print("✅ 工具定义: 通过")


def test_execute_tool_save():
    """工具入口 — save"""
    result = execute_checkpoint_tool({
        "action": "save",
        "task_id": "tool_save",
        "phase": "init",
        "state": '{"x": 1}',
    })
    assert "已保存" in result
    print("✅ 工具入口 save: 通过")


def test_execute_tool_save_missing_params():
    """工具入口 — save 缺少参数"""
    result = execute_checkpoint_tool({
        "action": "save",
        "task_id": "",
        "phase": "",
    })
    assert "请提供" in result
    print("✅ 工具入口 save 缺参数: 通过")


def test_execute_tool_load():
    """工具入口 — load"""
    # 先保存
    save_result = execute_checkpoint_tool({
        "action": "save",
        "task_id": "tool_load",
        "phase": "test",
        "state": '{"key":"val"}',
    })
    # 提取 cp_id
    cp_id = save_result.split("[ID: ")[1].split("]")[0]

    result = execute_checkpoint_tool({
        "action": "load",
        "checkpoint_id": cp_id,
    })
    assert "检查点:" in result
    assert "tool_load" in result
    assert "test" in result
    print("✅ 工具入口 load: 通过")


def test_execute_tool_load_missing():
    """工具入口 — load 缺 cp_id"""
    result = execute_checkpoint_tool({
        "action": "load",
        "checkpoint_id": "",
    })
    assert "请提供" in result
    print("✅ 工具入口 load 缺参数: 通过")


def test_execute_tool_list():
    """工具入口 — list"""
    result = execute_checkpoint_tool({"action": "list"})
    assert "检查点列表" in result or "暂无" in result
    print("✅ 工具入口 list: 通过")


def test_execute_tool_rollback():
    """工具入口 — rollback"""
    execute_checkpoint_tool({
        "action": "save",
        "task_id": "tool_rb",
        "phase": "setup",
        "state": '{"ready": true}',
    })
    result = execute_checkpoint_tool({
        "action": "rollback",
        "task_id": "tool_rb",
        "target_phase": "setup",
    })
    assert "已回滚" in result
    print("✅ 工具入口 rollback: 通过")


def test_execute_tool_delete():
    """工具入口 — delete_task"""
    execute_checkpoint_tool({
        "action": "save",
        "task_id": "tool_del",
        "phase": "x",
        "state": "{}",
    })
    result = execute_checkpoint_tool({
        "action": "delete_task",
        "task_id": "tool_del",
    })
    assert "已删除" in result
    print("✅ 工具入口 delete_task: 通过")


def test_execute_tool_clean():
    """工具入口 — clean_all"""
    result = execute_checkpoint_tool({
        "action": "clean_all",
        "max_age_days": 365,
    })
    assert "已清理" in result
    print("✅ 工具入口 clean_all: 通过")


def test_execute_tool_invalid_action():
    """工具入口 — 无效操作"""
    result = execute_checkpoint_tool({"action": "nonexistent"})
    assert "未知" in result
    print("✅ 工具入口 无效操作: 通过")


if __name__ == "__main__":
    all_tests = [
        test_save_and_load,
        test_save_with_metadata,
        test_list_all,
        test_list_by_task,
        test_rollback,
        test_rollback_nonexistent_phase,
        test_rollback_no_task,
        test_delete_task,
        test_clean_all,
        test_load_nonexistent,
        test_save_empty_task_id,
        test_tool_definition,
        test_execute_tool_save,
        test_execute_tool_save_missing_params,
        test_execute_tool_load,
        test_execute_tool_load_missing,
        test_execute_tool_list,
        test_execute_tool_rollback,
        test_execute_tool_delete,
        test_execute_tool_clean,
        test_execute_tool_invalid_action,
    ]

    passed = 0
    failed = 0

    print("=" * 50)
    print("🧪 Checkpoint Manager 单元测试 (v2.0)")
    print("=" * 50)

    for test in all_tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__}: {e}")

    print("=" * 50)
    print(f"🎉 测试完成: {passed} 通过, {failed} 失败")
    print("=" * 50)
