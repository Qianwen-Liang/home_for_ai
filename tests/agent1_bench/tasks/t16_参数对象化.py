"""
任务 t16: 参数对象化
难度: 较难
能力维度: L2-重构

重构：将散落的关联参数（name/age/city）合并为字典 person，保持行为不变。
"""

TASK_TITLE = "参数对象化"
TASK_DIMENSION = "L2-重构"
TASK_DIFFICULTY = "较难"

def create_greeting(person):
    return f"{person['name']} is {person['age']} years old from {person['city']}"

# ── 测试（自动评分，请勿修改）──
def _test():
    assert create_greeting({'name': 'Alice', 'age': 30, 'city': 'NY'}) == 'Alice is 30 years old from NY'
    import inspect
    assert len(inspect.signature(create_greeting).parameters) == 1
