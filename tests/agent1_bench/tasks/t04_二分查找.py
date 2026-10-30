"""
任务 t04: 二分查找
难度: 中等
能力维度: L1-代码生成

实现 binary_search(arr, target)，在有序数组 arr 中查找 target，返回索引，不存在返回 -1。
"""

TASK_TITLE = "二分查找"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "中等"

def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
# ── 测试（自动评分，请勿修改）──
def _test():
    assert binary_search([1, 3, 5, 7, 9], 5) == 2
    assert binary_search([1, 3, 5, 7, 9], 2) == -1
    assert binary_search([], 1) == -1
    assert binary_search([1], 1) == 0
    assert binary_search([1, 2, 3], 3) == 2
