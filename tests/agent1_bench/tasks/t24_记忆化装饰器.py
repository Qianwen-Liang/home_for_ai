"""
任务 t24: 记忆化装饰器
难度: 困难
能力维度: L1-代码生成

实现 memoize 装饰器，缓存函数调用结果，相同参数不重复计算。
"""

TASK_TITLE = "记忆化装饰器"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "困难"

def memoize(fn):
    cache = {}
    def wrapper(*args):
        if args not in cache:
            cache[args] = fn(*args)
        return cache[args]
    return wrapper
# ── 测试（自动评分，请勿修改）──
def _test():
    calls = {'n': 0}
    @memoize
    def fib(n):
        calls['n'] += 1
        return n if n < 2 else fib(n - 1) + fib(n - 2)
    assert fib(20) == 6765
    assert calls['n'] == 21, f'应只调用 21 次，实际 {calls["n"]} 次'
