"""
任务 t15: 拆分大函数
难度: 较难
能力维度: L2-重构

重构：将 process_data 拆分为 validate 与 normalize 两个函数，保持行为不变。
"""

TASK_TITLE = "拆分大函数"
TASK_DIMENSION = "L2-重构"
TASK_DIFFICULTY = "较难"

def validate(raw):
    return [x for x in raw if x is not None]

def normalize(data):
    return [x.strip() if isinstance(x, str) else x for x in data]

def process_data(raw):
    return normalize(validate(raw))
# ── 测试（自动评分，请勿修改）──
def _test():
    assert process_data([' a ', None, 'b']) == ['a', 'b']
    assert process_data([]) == []
    import sys
    mod = sys.modules[__name__]
    assert hasattr(mod, 'validate') and hasattr(mod, 'normalize'), '应拆分出 validate 与 normalize'
