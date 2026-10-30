"""
任务 t19: 空值处理
难度: 简单
能力维度: L5-健壮性

实现 first_non_none(values)：返回第一个非 None 元素，全为 None 返回 None。
"""

TASK_TITLE = "空值处理"
TASK_DIMENSION = "L5-健壮性"
TASK_DIFFICULTY = "简单"

def first_non_none(values):
    for v in values:
        if v is not None:
            return v
    return None
# ── 测试（自动评分，请勿修改）──
def _test():
    assert first_non_none([None, 2, 3]) == 2
    assert first_non_none([None, None]) is None
    assert first_non_none([]) is None
    assert first_non_none([0, None]) == 0
