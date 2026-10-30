"""
任务 t13: 提取魔法常量
难度: 中等
能力维度: L2-重构

重构：将重复出现的魔法数字 3.14159 提取为模块级常量 PI，并保持函数行为不变。
"""

TASK_TITLE = "提取魔法常量"
TASK_DIMENSION = "L2-重构"
TASK_DIFFICULTY = "中等"

PI = 3.14159

def circle_area(r):
    return PI * r * r

def circle_circumference(r):
    return 2 * PI * r
# ── 测试（自动评分，请勿修改）──
def _test():
    assert abs(circle_area(1) - 3.14159) < 1e-4
    assert abs(circle_circumference(1) - 6.28318) < 1e-4
    import sys
    mod = sys.modules[__name__]
    assert hasattr(mod, 'PI'), '应提取模块级常量 PI'
