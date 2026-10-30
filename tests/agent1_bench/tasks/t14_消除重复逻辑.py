"""
任务 t14: 消除重复逻辑
难度: 中等
能力维度: L2-重构

重构：两个函数含重复的平方和计算逻辑，提取公共函数 square_sum，保持行为不变。
"""

TASK_TITLE = "消除重复逻辑"
TASK_DIMENSION = "L2-重构"
TASK_DIFFICULTY = "中等"

def square_sum(*nums):
    return sum(x * x for x in nums)

def total_a(x, y):
    return square_sum(x, y)

def total_b(x, y, z):
    return square_sum(x, y, z)
# ── 测试（自动评分，请勿修改）──
def _test():
    assert total_a(3, 4) == 25
    assert total_b(1, 2, 3) == 14
    import sys
    mod = sys.modules[__name__]
    assert hasattr(mod, 'square_sum'), '应提取公共函数 square_sum'
