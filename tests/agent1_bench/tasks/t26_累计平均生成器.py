"""
任务 t26: 累计平均生成器
难度: 困难
能力维度: L3-数据处理

实现 running_average(iterable)，生成器逐元素产出累计平均值。
"""

TASK_TITLE = "累计平均生成器"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "困难"

def running_average(iterable):
    total = 0
    count = 0
    for x in iterable:
        total += x
        count += 1
        yield total / count
# ── 测试（自动评分，请勿修改）──
def _test():
    assert list(running_average([1, 2, 3])) == [1.0, 1.5, 2.0]
    assert list(running_average([])) == []
    assert list(running_average([10])) == [10.0]
