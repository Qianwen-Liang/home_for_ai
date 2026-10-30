"""
任务 t08: 修复求最大值
难度: 简单
能力维度: L2-诊断修复

修复 find_max：当列表全为负数时返回错误值（应返回实际最大值，而非初始的 0）。
"""

TASK_TITLE = "修复求最大值"
TASK_DIMENSION = "L2-诊断修复"
TASK_DIFFICULTY = "简单"

def find_max(lst):
    max_val = lst[0]
    for x in lst[1:]:
        if x > max_val:
            max_val = x
    return max_val
# ── 测试（自动评分，请勿修改）──
def _test():
    assert find_max([1, 5, 3]) == 5
    assert find_max([-5, -2, -9]) == -2
    assert find_max([7]) == 7
