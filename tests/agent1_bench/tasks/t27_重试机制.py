"""
任务 t27: 重试机制
难度: 困难
能力维度: L5-健壮性

实现 retry(fn, times)，调用 fn，失败时重试（最多 times 次），全部失败抛最后异常。
"""

TASK_TITLE = "重试机制"
TASK_DIMENSION = "L5-健壮性"
TASK_DIFFICULTY = "困难"

def retry(fn, times):
    last = None
    for _ in range(times + 1):
        try:
            return fn()
        except Exception as e:
            last = e
    raise last
# ── 测试（自动评分，请勿修改）──
def _test():
    state = {'n': 0}
    def flaky():
        state['n'] += 1
        if state['n'] < 3:
            raise ValueError('fail')
        return 'ok'
    assert retry(flaky, 2) == 'ok'
    state2 = {'n': 0}
    def always_fail():
        state2['n'] += 1
        raise RuntimeError('boom')
    try:
        retry(always_fail, 1)
        assert False, '应抛出异常'
    except RuntimeError:
        assert state2['n'] == 2
