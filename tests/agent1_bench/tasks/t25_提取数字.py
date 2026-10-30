"""
任务 t25: 提取数字
难度: 困难
能力维度: L3-数据处理

实现 extract_numbers(text)，返回文本中出现的所有整数列表（按出现顺序）。
"""

TASK_TITLE = "提取数字"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "困难"

def extract_numbers(text):
    import re
    return [int(x) for x in re.findall(r'-?\d+', text)]
# ── 测试（自动评分，请勿修改）──
def _test():
    assert extract_numbers('a1b22c333') == [1, 22, 333]
    assert extract_numbers('') == []
    assert extract_numbers('x-5y10') == [-5, 10]
    assert extract_numbers('no numbers') == []
