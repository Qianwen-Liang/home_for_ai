"""
任务 t11: 嵌套字段提取
难度: 中等
能力维度: L3-数据处理

实现 extract_field(obj, path)，按点分路径（如 'a.b.c'）提取嵌套字段，缺失返回 None。
"""

TASK_TITLE = "嵌套字段提取"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "中等"

def extract_field(obj, path):
    cur = obj
    for key in path.split('.'):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur
# ── 测试（自动评分，请勿修改）──
def _test():
    assert extract_field({'a': {'b': 1}}, 'a.b') == 1
    assert extract_field({'a': {}}, 'a.b') is None
    assert extract_field({'a': {'b': {'c': 2}}}, 'a.b.c') == 2
    assert extract_field({}, 'a') is None
