"""
任务 t17: 安全除法
难度: 简单
能力维度: L5-健壮性

实现 safe_divide_v2(a, b)：b 为 0 返回 None，a 或 b 非数字返回 None。
"""

TASK_TITLE = "安全除法"
TASK_DIMENSION = "L5-健壮性"
TASK_DIFFICULTY = "简单"

def safe_divide_v2(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    if b == 0:
        return None
    return a / b
# ── 测试（自动评分，请勿修改）──
def _test():
    assert safe_divide_v2(10, 2) == 5.0
    assert safe_divide_v2(10, 0) is None
    assert safe_divide_v2('a', 2) is None
    assert safe_divide_v2(10, 'b') is None
