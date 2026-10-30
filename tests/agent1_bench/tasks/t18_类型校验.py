"""
任务 t18: 类型校验
难度: 简单
能力维度: L5-健壮性

实现 sum_ints(values)：仅累加 int 类型元素，忽略其他类型，返回总和。
"""

TASK_TITLE = "类型校验"
TASK_DIMENSION = "L5-健壮性"
TASK_DIFFICULTY = "简单"

def sum_ints(values):
    return sum(x for x in values if isinstance(x, int))
# ── 测试（自动评分，请勿修改）──
def _test():
    assert sum_ints([1, 2, 3]) == 6
    assert sum_ints([1, 'a', 2.5, 3]) == 4
    assert sum_ints([]) == 0
    assert sum_ints(['x', 'y']) == 0
