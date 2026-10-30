"""
任务 t06: 修复越界访问
难度: 简单
能力维度: L2-诊断修复

修复 get_element：当索引越界或列表为空时返回 None，而不是抛 IndexError。
"""

TASK_TITLE = "修复越界访问"
TASK_DIMENSION = "L2-诊断修复"
TASK_DIFFICULTY = "简单"

def get_element(lst, index):
    if not lst or index < -len(lst) or index >= len(lst):
        return None
    return lst[index]
# ── 测试（自动评分，请勿修改）──
def _test():
    assert get_element([1, 2, 3], 1) == 2
    assert get_element([1, 2, 3], 5) is None
    assert get_element([], 0) is None
    assert get_element([1, 2], -1) == 2
