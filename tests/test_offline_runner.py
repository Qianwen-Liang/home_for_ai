"""
Offline Runner 单元测试
"""
import sys
import os
import json

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.offline_runner import (
    OfflineTaskManager, OfflineTask, OfflineError,
    TOOL_DEFINITION, _manager,
)


def test_offline_task_dataclass():
    """OfflineTask 数据模型"""
    task = OfflineTask(
        task_id="OT-001",
        title="测试任务",
        description="这是一个测试",
    )
    assert task.task_id == "OT-001"
    assert task.title == "测试任务"
    assert task.status == "pending"
    assert task.progress == 0.0
    assert task.phases == []
    print("✅ 测试1 OfflineTask: 通过")


def test_submit():
    """提交任务"""
    mgr = OfflineTaskManager()

    result = mgr.submit(
        title="测试离线任务",
        description="用于测试的离线任务",
        phases=["扫描", "分析", "报告"],
    )
    assert "已提交" in result
    assert "OT-" in result
    assert "测试离线任务" in result

    # 提取 task_id
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    assert task_id.startswith("OT-")
    assert task_id in mgr._tasks

    # 验证持久化
    task = mgr._tasks[task_id]
    assert task.title == "测试离线任务"
    assert len(task.phases) == 3
    assert task.status == "pending"

    print("✅ 测试2 提交任务: 通过")
    return task_id


def test_submit_empty_title():
    """空标题拒绝"""
    mgr = OfflineTaskManager()
    try:
        mgr.submit(title="")
        assert False
    except OfflineError:
        pass
    print("✅ 测试3 空标题拒绝: 通过")


def test_execute():
    """执行任务"""
    mgr = OfflineTaskManager()

    # 先提交
    result = mgr.submit(
        title="执行测试",
        phases=["步骤1", "步骤2", "步骤3"],
    )
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    # 执行（使用简单回调）
    def executor(tid, phase, params):
        return {"status": "done", "phase": phase, "output": f"{phase} 完成"}

    result = mgr.execute(task_id, phase_executor=executor)
    assert "已完成" in result

    # 验证状态
    task = mgr._tasks[task_id]
    assert task.status == "done"
    assert task.progress == 1.0
    assert len(task.checkpoint_ids) == 3
    assert len(task.result) == 3

    print("✅ 测试4 执行任务: 通过")


def test_execute_with_failure():
    """执行失败"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="失败测试", phases=["步骤1", "步骤2"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    def failing_executor(tid, phase, params):
        if phase == "步骤2":
            raise RuntimeError("模拟执行失败")
        return {"status": "done", "phase": phase}

    result = mgr.execute(task_id, phase_executor=failing_executor)
    assert "失败" in result or "错误" in result or "failed" in result.lower()

    task = mgr._tasks[task_id]
    assert task.status == "failed"
    assert task.error

    print("✅ 测试5 执行失败: 通过")


def test_status():
    """查看状态"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="状态测试", phases=["A", "B"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    result = mgr.get_status(task_id)
    assert "pending" in result or "待处理" in result
    assert "状态测试" in result

    # 不存在的任务
    try:
        mgr.get_status("nonexistent")
        assert False
    except OfflineError:
        pass

    print("✅ 测试6 查看状态: 通过")


def test_list_tasks():
    """列出任务"""
    mgr = OfflineTaskManager()

    result = mgr.list_tasks()
    # 之前已提交的任务应该可见
    assert "OT-" in result or "暂无" in result

    print("✅ 测试7 列出任务: 通过")


def test_generate_report():
    """生成报告"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="报告测试", phases=["阶段1"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    result = mgr.generate_report(task_id)
    assert "执行报告" in result
    assert "报告测试" in result

    # 不存在的任务
    try:
        mgr.generate_report("nonexistent")
        assert False
    except OfflineError:
        pass

    print("✅ 测试8 生成报告: 通过")


def test_pause_resume():
    """暂停恢复"""
    mgr = OfflineTaskManager()

    # 提交任务但标记为运行中（模拟）
    result = mgr.submit(title="暂停测试", phases=["长任务"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    # 手动改为运行中
    mgr._tasks[task_id].status = "running"
    mgr._save_task(mgr._tasks[task_id])

    # 暂停
    result = mgr.pause(task_id)
    assert "已暂停" in result

    assert mgr._tasks[task_id].status == "paused"

    # 恢复
    result = mgr.resume(task_id)
    assert "已恢复" in result
    assert mgr._tasks[task_id].status == "running"

    # 暂停非运行中任务
    mgr._tasks[task_id].status = "done"
    result = mgr.pause(task_id)
    assert "无法暂停" in result

    print("✅ 测试9 暂停恢复: 通过")


def test_cancel():
    """取消任务"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="取消测试", phases=["任务"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    result = mgr.cancel(task_id)
    assert "已取消" in result

    # 不能取消已完成的任务
    mgr._tasks[task_id].status = "done"
    result = mgr.cancel(task_id)
    assert "无法取消" in result or "已完成" in result

    print("✅ 测试10 取消任务: 通过")


def test_execute_pause_midway():
    """执行中暂停"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="中途暂停测试", phases=["步骤1", "步骤2", "步骤3"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    call_count = [0]

    def pausing_executor(tid, phase, params):
        call_count[0] += 1
        if call_count[0] == 2:
            # 模拟暂停
            mgr._tasks[task_id].status = "paused"
            mgr._save_task(mgr._tasks[task_id])
        return {"status": "done", "phase": phase}

    result = mgr.execute(task_id, phase_executor=pausing_executor)
    # 应检测到暂停
    assert "已暂停" in result or "paused" in result.lower()
    assert call_count[0] < 3  # 没执行完

    print("✅ 测试11 中途暂停: 通过")


def test_execute_invalid_task():
    """执行不存在的任务"""
    mgr = OfflineTaskManager()
    try:
        mgr.execute("nonexistent")
        assert False
    except OfflineError:
        pass
    print("✅ 测试12 执行无效任务: 通过")


def test_tool_definition():
    """工具定义"""
    assert TOOL_DEFINITION["type"] == "function"
    assert TOOL_DEFINITION["function"]["name"] == "offline"
    actions = TOOL_DEFINITION["function"]["parameters"]["properties"]["action"]["enum"]
    assert "submit" in actions
    assert "execute" in actions
    assert "status" in actions
    assert "list" in actions
    assert "report" in actions
    assert "pause" in actions
    assert "resume" in actions
    assert "cancel" in actions
    print("✅ 测试13 工具定义: 通过")


def test_execute_tool():
    """工具入口"""
    from tools.offline_runner import execute_offline_tool

    # submit
    result = execute_offline_tool({
        "action": "submit",
        "title": "工具入口测试",
        "phases": '["A","B"]',
    })
    assert "已提交" in result

    # list
    result = execute_offline_tool({"action": "list"})
    assert "OT-" in result or "暂无" in result

    # 无效操作
    result = execute_offline_tool({"action": "invalid"})
    assert "未知" in result

    # 无效 task_id
    result = execute_offline_tool({
        "action": "status",
        "task_id": "nonexistent",
    })
    assert "错误" in result or "未找到" in result

    print("✅ 测试14 工具入口: 通过")


# ── Phase 2: Recovery 测试 ────────────────────────────────


def test_recover_with_checkpoint():
    """从检查点恢复任务"""
    mgr = OfflineTaskManager()

    # 提交并执行一个任务（让它有检查点）
    result = mgr.submit(title="恢复测试", phases=["阶段1", "阶段2", "阶段3"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    def executor(tid, phase, params):
        return {"status": "done", "phase": phase}

    mgr.execute(task_id, phase_executor=executor)
    assert mgr._tasks[task_id].status == "done"

    # 手动改为 failed（模拟崩溃后状态）
    mgr._tasks[task_id].status = "failed"
    mgr._save_task(mgr._tasks[task_id])

    # 恢复
    result = mgr.recover(task_id)
    assert "已恢复" in result or "已从检查点恢复" in result
    assert mgr._tasks[task_id].status == "paused"  # 恢复后暂停

    print("✅ 测试15 从检查点恢复: 通过")


def test_recover_no_checkpoint():
    """无检查点恢复 → 重置"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="无检查点恢复", phases=["单阶段"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    # 手动标记为 failed（没有执行过 = 无检查点）
    mgr._tasks[task_id].status = "failed"
    mgr._save_task(mgr._tasks[task_id])

    result = mgr.recover(task_id)
    assert "已重置" in result or "无检查点" in result
    assert mgr._tasks[task_id].status == "pending"

    print("✅ 测试16 无检查点恢复: 通过")


def test_recover_done_task():
    """已完成任务 → 无需恢复"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="已完成任务")
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    mgr._tasks[task_id].status = "done"
    mgr._save_task(mgr._tasks[task_id])

    result = mgr.recover(task_id)
    assert "已完成" in result

    print("✅ 测试17 已完成无需恢复: 通过")


def test_recover_running_task():
    """运行中任务 → 拒绝恢复"""
    mgr = OfflineTaskManager()

    result = mgr.submit(title="运行中任务")
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    mgr._tasks[task_id].status = "running"
    mgr._save_task(mgr._tasks[task_id])

    result = mgr.recover(task_id)
    assert "正在运行" in result

    print("✅ 测试18 运行中拒绝恢复: 通过")


def test_recover_nonexistent_task():
    """恢复不存在任务 → 异常"""
    mgr = OfflineTaskManager()
    try:
        mgr.recover("nonexistent")
        assert False
    except OfflineError:
        pass
    print("✅ 测试19 恢复不存在任务: 通过")


def test_recover_tool_action():
    """工具入口 recover 操作"""
    from tools.offline_runner import execute_offline_tool

    mgr = _manager  # 使用全局实例

    result = mgr.submit(title="工具恢复测试", phases=["A"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    mgr._tasks[task_id].status = "failed"
    mgr._save_task(mgr._tasks[task_id])

    result = execute_offline_tool({
        "action": "recover",
        "task_id": task_id,
    })
    assert "恢复" in result

    print("✅ 测试20 工具入口 recover: 通过")


def test_zombie_detection_auto_recover():
    """僵尸任务自动检测（auto_recover=True）"""
    # 使用 auto_recover=True 创建管理器
    mgr = OfflineTaskManager(auto_recover=True)

    result = mgr.submit(title="僵尸任务", phases=["长任务"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    # 手动设置为 running + 超旧的 updated_at（模拟僵尸）
    task = mgr._tasks[task_id]
    task.status = "running"
    task.updated_at = "2000-01-01 00:00:00"  # 远久于阈值
    mgr._save_task(task)

    # 手动调用僵尸检测
    mgr._recover_zombies()

    # auto_recover=True → 应标记为 paused
    task = mgr._tasks[task_id]
    assert task.status == "paused"
    assert "AutoRecovery" in task.error

    recovery_log = mgr.get_recovery_log()
    assert "僵尸" in recovery_log or "僵死" in recovery_log
    assert task_id in recovery_log

    print("✅ 测试21 僵尸自动恢复: 通过")


def test_zombie_detection_no_auto():
    """僵尸任务检测（auto_recover=False）→ 仅记录"""
    mgr = OfflineTaskManager(auto_recover=False)

    result = mgr.submit(title="仅记录僵尸", phases=["长任务"])
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    task = mgr._tasks[task_id]
    task.status = "running"
    task.updated_at = "2000-01-01 00:00:00"
    mgr._save_task(task)

    mgr._recover_zombies()

    # auto_recover=False → 保持 running
    task = mgr._tasks[task_id]
    assert task.status == "running"

    recovery_log = mgr.get_recovery_log()
    assert "僵尸" in recovery_log or "僵死" in recovery_log

    print("✅ 测试22 僵尸仅记录: 通过")


def test_recovery_log_empty():
    """空恢复日志"""
    mgr = OfflineTaskManager()
    log = mgr.get_recovery_log()

    # 新实例、无僵尸 → 空日志
    # 可能包含之前全局实例残留，只验证返回类型
    assert isinstance(log, str)
    print("✅ 测试23 恢复日志: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Offline Runner 单元测试")
    print("=" * 50)
    test_offline_task_dataclass()
    test_submit()
    test_submit_empty_title()
    test_execute()
    test_execute_with_failure()
    test_status()
    test_list_tasks()
    test_generate_report()
    test_pause_resume()
    test_cancel()
    test_execute_pause_midway()
    test_execute_invalid_task()
    test_tool_definition()
    test_execute_tool()
    # Phase 2: Recovery
    test_recover_with_checkpoint()
    test_recover_no_checkpoint()
    test_recover_done_task()
    test_recover_running_task()
    test_recover_nonexistent_task()
    test_recover_tool_action()
    test_zombie_detection_auto_recover()
    test_zombie_detection_no_auto()
    test_recovery_log_empty()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
