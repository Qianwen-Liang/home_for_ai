"""message_bus 确定性回归测试（T2831）。

调研结论（实测，见 memory/cmd_output/msgbus_concurrency.py）：
  - 8 线程 x 40 条并发 send：队列 320、历史 320、唯一 ID 320，**无丢失**
  - 重新加载后仍为 320，**持久化一致**
  - 实现无锁，但 Python GIL 下 list.append / dict 操作具备原子性，
    且 _save() 每次写完整内存快照，最终状态自洽

因此本模块**不做功能改动**，只补回归测试锁定现状：
一旦将来引入异步写、批量缓冲或多进程，这些断言会立刻报警。

另记录一条能力边界：message_bus 无幂等键，同一逻辑消息重复 send 会产生多条。
当前系统没有消息重试机制，该缺口不构成实际风险；若将来引入重试，
需要参考 idemkit 的做法增加幂等键（相同 key 返回首次结果、不重复入队）。
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.message_bus as MB  # noqa: E402


@pytest.fixture()
def bus(monkeypatch, tmp_path):
    """隔离到临时文件，绝不触碰生产 memory/messages.json。"""
    monkeypatch.setattr(MB, "MESSAGE_FILE", tmp_path / "messages.json")
    return MB.MessageBus()


def test_concurrent_send_loses_nothing(bus) -> None:
    """并发发送不得丢消息，ID 必须唯一。"""
    n_per_thread, threads_n = 25, 6
    errors: list[str] = []

    def worker(tid: int) -> None:
        for i in range(n_per_thread):
            try:
                bus.send(target="agent_x", content='{"i": %d}' % i, source=f"t{tid}")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = n_per_thread * threads_n
    assert not errors, f"并发发送出现异常: {errors[:3]}"
    queued = bus._queues["agent_x"]
    assert len(queued) == expected, f"队列丢消息: {len(queued)}/{expected}"
    assert len({m.msg_id for m in queued}) == expected, "存在重复 msg_id"


def test_persistence_survives_reload(bus) -> None:
    """发送后重新加载，消息数量与内容一致。"""
    for i in range(10):
        bus.send(target="agent_y", content='{"i": %d}' % i)

    reloaded = MB.MessageBus()
    assert len(reloaded._queues.get("agent_y", [])) == 10


def test_priority_order_is_stable(bus) -> None:
    """同优先级消息保持插入顺序（Python sort 稳定性的依赖点）。"""
    for i in range(5):
        bus.send(target="agent_z", content='{"i": %d}' % i, priority=5)
    bus.send(target="agent_z", content='{"urgent": 1}', priority=9)

    queue = bus._queues["agent_z"]
    assert queue[0].content == {"urgent": 1}, "高优先级未排到队首"
    same_prio = [m.content["i"] for m in queue[1:]]
    assert same_prio == [0, 1, 2, 3, 4], f"同优先级顺序被打乱: {same_prio}"


def test_no_idempotency_key_by_design(bus) -> None:
    """记录能力边界：无幂等键，重复 send 会产生多条。

    这不是 bug 而是当前设计边界——系统中没有消息重试机制。
    此测试把边界显式化：若将来引入重试而忘了加幂等，
    这里的断言会先失败，提醒补上 idempotency_key。
    """
    bus.send(target="agent_w", content='{"k": 1}')
    bus.send(target="agent_w", content='{"k": 1}')
    assert len(bus._queues["agent_w"]) == 2, "若出现去重，说明已引入幂等键，请同步更新文档"


def test_error_on_missing_target(bus) -> None:
    with pytest.raises(MB.MessageBusError):
        bus.send(target="", content="{}")


def test_error_on_invalid_json(bus) -> None:
    with pytest.raises(MB.MessageBusError):
        bus.send(target="a", content="not-json")
