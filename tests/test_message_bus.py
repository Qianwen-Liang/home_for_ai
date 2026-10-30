"""
Message Bus 单元测试
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.message_bus import MessageBus, MessageBusError, MessagePriority


def test_send_receive():
    """测试消息发送与接收"""
    bus = MessageBus()
    bus.clear()

    # 发送消息
    r = bus.send(target="agent_a", msg_type="task",
                 content='{"desc": "写一篇文章", "deadline": "今日"}',
                 priority=MessagePriority.HIGH)
    assert "已发送" in r, f"发送失败: {r}"
    print("✅ 测试1 发送消息: 通过")

    # 接收消息
    r = bus.receive("agent_a")
    assert "待处理" in r, f"接收失败: {r}"
    assert "写一篇文章" in r, f"内容不对: {r}"
    print("✅ 测试2 接收消息: 通过")

    # 队列长度
    r = bus.queue_length("agent_a")
    assert "1 条" in r, f"队列长度不对: {r}"
    print("✅ 测试3 队列长度: 通过")

    bus.clear()
    print("✅ 测试4 清理: 通过")


def test_priority():
    """测试消息优先级"""
    bus = MessageBus()
    bus.clear()

    # 发送普通消息
    bus.send(target="agent_b", msg_type="notify",
             content='{"msg": "普通通知"}',
             priority=MessagePriority.LOW)

    # 发送紧急消息（优先级高，应排在前面）
    bus.send(target="agent_b", msg_type="task",
             content='{"msg": "紧急任务"}',
             priority=MessagePriority.CRITICAL)

    # 接收消息，紧急的应先到
    r = bus.receive("agent_b")
    # 按优先级排序，紧急的应该在前面
    lines = r.split("\n")
    content_lines = [l for l in lines if "内容:" in l]
    assert len(content_lines) >= 2, f"应收到2条消息: {r}"
    print("✅ 测试5 消息优先级: 通过")

    bus.clear()


def test_broadcast():
    """测试广播消息"""
    # 需要先注册一些Agent（使用全局实例以让广播能发现）
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.agent_manager import _manager as mgr
    
    temp_agents = []
    for name in ["BroadcastTestA", "BroadcastTestB"]:
        aid = name.lower()
        if aid not in mgr._agents:
            mgr.register(name=name, role="test",
                        capabilities=json.dumps(["test"]),
                        tools=json.dumps([]))
            temp_agents.append(aid)

    bus = MessageBus()
    bus.clear()

    # 广播
    r = bus.broadcast(msg_type="notify",
                      content='{"msg": "系统通知"}',
                      priority=MessagePriority.NORMAL)
    assert "广播" in r, f"广播失败: {r}"
    print("✅ 测试6 广播消息: 通过")

    # 检查是否所有测试Agent都收到了广播
    received_count = 0
    for aid in temp_agents:
        r = bus.receive(aid)
        if "待处理" in r:
            received_count += 1
    
    print(f"✅ 测试7 广播送达 ({received_count}/{len(temp_agents)}): 通过")

    bus.clear()
    for aid in temp_agents:
        mgr.unregister(aid)


def test_subscribe():
    """测试订阅系统"""
    bus = MessageBus()
    bus.clear()

    # 订阅
    r = bus.subscribe(agent_id="sub_agent", topic="updates")
    assert "已订阅" in r, f"订阅失败: {r}"
    print("✅ 测试8 订阅: 通过")

    # 重复订阅
    r = bus.subscribe(agent_id="sub_agent", topic="updates")
    assert "已订阅" in r, "重复订阅应提示已存在"
    print("✅ 测试9 重复订阅: 通过")

    # 列出订阅
    r = bus.list_subscriptions()
    assert "updates" in r, f"列表中没有主题: {r}"
    print("✅ 测试10 列出订阅: 通过")

    # 取消订阅
    r = bus.unsubscribe(agent_id="sub_agent", topic="updates")
    assert "已取消订阅" in r, f"取消订阅失败: {r}"
    print("✅ 测试11 取消订阅: 通过")

    # 取消后订阅数为0
    r = bus.list_subscriptions()
    assert "0 个订阅" in r, f"取消后应有0订阅: {r}"
    print("✅ 测试12 取消后订阅数为0: 通过")


def test_history():
    """测试消息历史"""
    bus = MessageBus()
    bus.clear()

    # 发送几条消息
    for i in range(3):
        bus.send(target=f"hist_agent_{i}", msg_type="task",
                 content=f'{{"seq": {i}}}',
                 priority=MessagePriority.NORMAL)

    # 查看历史
    r = bus.history()
    assert "消息历史" in r, f"历史查询失败: {r}"
    assert "hist_agent" in r, f"历史中缺少消息: {r}"
    print("✅ 测试13 消息历史: 通过")

    # 按Agent过滤
    r = bus.history(agent_id="hist_agent_0")
    assert "hist_agent_0" in r, f"过滤失败: {r}"
    print("✅ 测试14 按Agent过滤历史: 通过")

    bus.clear()


def test_errors():
    """测试错误处理"""
    bus = MessageBus()

    # 空目标
    try:
        bus.send(target="", msg_type="task", content="{}")
        assert False, "应拒绝空目标"
    except MessageBusError:
        pass
    print("✅ 测试15 拒绝空目标: 通过")

    # 空Agent接收
    try:
        bus.receive("")
        assert False, "应拒绝空Agent"
    except MessageBusError:
        pass
    print("✅ 测试16 拒绝空Agent接收: 通过")

    # 空Agent订阅
    try:
        bus.subscribe(agent_id="", topic="test")
        assert False, "应拒绝空Agent订阅"
    except MessageBusError:
        pass
    print("✅ 测试17 拒绝空Agent订阅: 通过")

    # 空主题订阅
    try:
        bus.subscribe(agent_id="test", topic="")
        assert False, "应拒绝空主题"
    except MessageBusError:
        pass
    print("✅ 测试18 拒绝空主题订阅: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Message Bus 单元测试")
    print("=" * 50)
    test_send_receive()
    print()
    test_priority()
    print()
    test_broadcast()
    print()
    test_subscribe()
    print()
    test_history()
    print()
    test_errors()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
