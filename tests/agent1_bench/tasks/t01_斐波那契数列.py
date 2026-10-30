"""
任务 t01: 斐波那契数列
难度: 简单
能力维度: L1-代码生成

实现 fibonacci(n)，返回第 n 个斐波那契数（fib(0)=0, fib(1)=1）。
"""

TASK_TITLE = "斐波那契数列"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "简单"

def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b
# ── 测试（自动评分，请勿修改）──
def _test():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(10) == 55
    assert fibonacci(15) == 610
