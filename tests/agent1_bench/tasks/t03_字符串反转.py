"""
任务 t03: 字符串反转
难度: 简单
能力维度: L1-代码生成

实现 reverse_string(s)，反转字符串，不使用切片 [::-1]。
"""

TASK_TITLE = "字符串反转"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "简单"

def reverse_string(s):
    result = ''
    for ch in s:
        result = ch + result
    return result
# ── 测试（自动评分，请勿修改）──
def _test():
    assert reverse_string('hello') == 'olleh'
    assert reverse_string('') == ''
    assert reverse_string('a') == 'a'
    assert reverse_string('ab') == 'ba'
