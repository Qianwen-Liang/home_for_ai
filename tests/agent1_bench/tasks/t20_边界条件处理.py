"""
任务 t20: 边界条件处理
难度: 中等
能力维度: L5-健壮性

实现 safe_average(values)：返回平均值，空列表返回 None，忽略 None 元素。
"""

TASK_TITLE = "边界条件处理"
TASK_DIMENSION = "L5-健壮性"
TASK_DIFFICULTY = "中等"

def safe_average(values):
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)
# ── 测试（自动评分，请勿修改）──
def _test():
    assert safe_average([1, 2, 3]) == 2.0
    assert safe_average([]) is None
    assert safe_average([None, 2, 4]) == 3.0
    assert safe_average([None, None]) is None
