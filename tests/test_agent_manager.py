"""
Agent Manager 单元测试
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.agent_manager import AgentManager, AgentManagerError
from tools.agent_manager import create_default_specialists


def test_basic():
    """基础功能测试"""
    m = AgentManager()

    # 1. 注册
    r = m.register(name="WriterBot", role="内容创作专家",
                   capabilities=json.dumps(["writing", "creative"]),
                   tools=json.dumps(["knowledge", "web_search"]))
    assert "注册成功" in r, f"注册失败: {r}"
    assert "writerbot" in r.lower(), f"ID缺失: {r}"
    print("✅ 测试1 注册: 通过")

    # 2. 列表
    r = m.list_agents()
    assert "WriterBot" in r, f"列表中没有WriterBot: {r}"
    print("✅ 测试2 列表: 通过")

    # 3. 查找能力
    r = m.discover("writing")
    assert "WriterBot" in r, f"查找不到WriterBot: {r}"
    print("✅ 测试3 能力查找: 通过")

    # 4. 查找不存在的能力
    r = m.discover("nonexistent")
    assert "未找到" in r, f"应提示未找到: {r}"
    print("✅ 测试4 查找不存在能力: 通过")

    # 5. 分配任务
    r = m.assign_task(agent_id="writerbot", task_id="T001",
                      task_description="撰写一篇AI文章")
    assert "已分配" in r, f"分配失败: {r}"
    print("✅ 测试5 分配任务: 通过")

    # 6. 状态检查（应该忙碌）
    r = m.get_status("writerbot")
    assert "busy" in r or "忙碌" in r, f"应显示忙碌: {r}"
    print("✅ 测试6 状态检查(忙碌): 通过")

    # 7. 完成任��
    r = m.complete_task(agent_id="writerbot", task_id="T001",
                        result="文章已完成")
    assert "任务完成" in r, f"完成任务失败: {r}"
    print("✅ 测试7 完成任务: 通过")

    # 8. 状态检查（应该空闲）
    r = m.get_status("writerbot")
    assert "idle" in r or "空闲" in r, f"应显示空闲: {r}"
    print("✅ 测试8 状态检查(空闲): 通过")

    # 9. 心跳
    r = m.heartbeat("writerbot")
    assert "心跳已更新" in r, f"心跳失败: {r}"
    print("✅ 测试9 心跳: 通过")

    # 10. 健康报告
    r = m.report()
    assert "健康报告" in r, f"报告格式错误: {r[:100]}"
    assert "WriterBot" in r, f"报告中无Agent: {r[:100]}"
    print("✅ 测试10 健康报告: 通过")

    # 11. 指定ID重复注册
    try:
        m.register(name="AnotherBot", role="R", capabilities="[]",
                   tools="[]", agent_id="writerbot")
        assert False, "应拒绝重复ID"
    except AgentManagerError as e:
        assert "已存在" in str(e), f"错误信息不对: {e}"
    print("✅ 测试11 重复ID拒绝: 通过")

    # 12. 注销
    r = m.unregister("writerbot")
    assert "已注销" in r, f"注销失败: {r}"
    print("✅ 测试12 注销: 通过")

    # 13. 注销后查找
    r = m.discover("writing")
    assert "未找到" in r, f"应提示未找到: {r}"
    print("✅ 测试13 注销后查找: 通过")


def test_default_specialists():
    """默认Specialist创建测试"""
    m = AgentManager()
    created = create_default_specialists(m)

    assert len(created) > 0, f"应创建至少一个Specialist: {created}"
    print(f"✅ 测试14 创建默认Specialist ({len(created)}个): 通过")
    for cid in created:
        print(f"   - {cid}")

    # 检查列表中包含所有创建
    r = m.list_agents()
    for cid in created:
        assert cid in r, f"列表中缺少{cid}: {r[:200]}"
    print("✅ 测试15 列表包含所有Specialist: 通过")

    # 查看报告
    r = m.report()
    print(f"✅ 测试16 生成报告: 通过 ({len(r)} chars)")

    # 清理
    for cid in created:
        m.unregister(cid)
    print("✅ 测试17 清理: 通过")


def test_task_failure():
    """任务失败测试"""
    m = AgentManager()
    m.register(name="TestBot", role="测试用",
               capabilities=json.dumps(["testing"]),
               tools=json.dumps([]))

    m.assign_task(agent_id="testbot", task_id="T002",
                  task_description="一个会失败的任务")
    r = m.task_failed(agent_id="testbot", task_id="T002",
                      error="发生了错误")
    assert "失败" in r, f"失败报告不对: {r}"
    print("✅ 测试18 任务失败报告: 通过")

    # 检查统计
    r = m.get_status("testbot")
    assert "1 失败" in r, f"统计更新不对: {r}"
    print("✅ 测试19 失败统计: 通过")

    m.unregister("testbot")
    print("✅ 测试20 清理: 通过")


def test_edge_cases():
    """边界情况测试"""
    m = AgentManager()

    # 空名称
    try:
        m.register(name="", role="R", capabilities="[]", tools="[]")
        assert False, "应拒绝空名称"
    except AgentManagerError:
        pass
    print("✅ 测试21 拒绝空名称: 通过")

    # 未注册的Agent
    try:
        m.get_status("nonexistent")
        assert False, "应拒绝未注册Agent"
    except AgentManagerError:
        pass
    print("✅ 测试22 拒绝未注册查询: 通过")

    # 列表为空
    r = m.list_agents()
    assert "暂无" in r, f"空列表提示不对: {r}"
    print("✅ 测试23 空列表: 通过")

    # 不指定Agent注销
    try:
        m.unregister("")
        assert False, "应拒绝空ID注销"
    except AgentManagerError:
        pass
    print("✅ 测试24 拒绝空ID注销: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Agent Manager 单元测试")
    print("=" * 50)
    test_basic()
    print()
    test_default_specialists()
    print()
    test_task_failure()
    print()
    test_edge_cases()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
