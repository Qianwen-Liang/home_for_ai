"""
任务 t23: 全排列生成
难度: 困难
能力维度: L1-代码生成

实现 permutations(items)，返回所有排列的列表（顺序不限）。
"""

TASK_TITLE = "全排列生成"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "困难"

def permutations(items):
    if len(items) <= 1:
        return [list(items)]
    result = []
    for i, x in enumerate(items):
        rest = items[:i] + items[i + 1:]
        for p in permutations(rest):
            result.append([x] + p)
    return result
# ── 测试（自动评分，请勿修改）──
def _test():
    r = permutations([1, 2])
    assert sorted(map(tuple, r)) == [(1, 2), (2, 1)]
    assert len(permutations([1, 2, 3])) == 6
    assert permutations([]) == [[]]
