"""
任务 t05: 修复除零异常
难度: 简单
能力维度: L2-诊断修复

修复 safe_divide：当 b 为 0 时应返回 None，而不是抛出异常。
"""

TASK_TITLE = "修复除零异常"
TASK_DIMENSION = "L2-诊断修复"
TASK_DIFFICULTY = "简单"

def safe_divide(a, b):
    if b == 0:
        return None
    return a / b
# ── 测试（自动评分，请勿修改）──
def _test():
    assert safe_divide(10, 2) == 5.0
    assert safe_divide(10, 0) is None
    assert safe_divide(0, 5) == 0.0
