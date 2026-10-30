"""
任务 t10: 合并有序列表
难度: 中等
能力维度: L3-数据处理

实现 merge_sorted(a, b)，合并两个已排序列表，返回新的有序列表。
"""

TASK_TITLE = "合并有序列表"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "中等"

def merge_sorted(a, b):
    result = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result
# ── 测试（自动评分，请勿修改）──
def _test():
    assert merge_sorted([1, 3], [2, 4]) == [1, 2, 3, 4]
    assert merge_sorted([], [1]) == [1]
    assert merge_sorted([1], []) == [1]
    assert merge_sorted([1, 1], [1, 2]) == [1, 1, 1, 2]
