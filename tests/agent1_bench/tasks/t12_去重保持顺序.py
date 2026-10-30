"""
任务 t12: 去重保持顺序
难度: 简单
能力维度: L3-数据处理

实现 dedupe(lst)，去除重复元素并保持首次出现的顺序。
"""

TASK_TITLE = "去重保持顺序"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "简单"

def dedupe(lst):
    seen = set()
    result = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result
# ── 测试（自动评分，请勿修改）──
def _test():
    assert dedupe([1, 2, 2, 3, 1]) == [1, 2, 3]
    assert dedupe([]) == []
    assert dedupe([5, 5, 5]) == [5]
    assert dedupe(['a', 'b', 'a']) == ['a', 'b']
