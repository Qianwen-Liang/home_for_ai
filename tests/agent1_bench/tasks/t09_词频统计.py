"""
任务 t09: 词频统计
难度: 中等
能力维度: L3-数据处理

实现 word_frequency(text)，按空格分词（小写），返回单词频次字典。
"""

TASK_TITLE = "词频统计"
TASK_DIMENSION = "L3-数据处理"
TASK_DIFFICULTY = "中等"

def word_frequency(text):
    result = {}
    for w in text.lower().split():
        result[w] = result.get(w, 0) + 1
    return result
# ── 测试（自动评分，请勿修改）──
def _test():
    assert word_frequency('a b a') == {'a': 2, 'b': 1}
    assert word_frequency('') == {}
    assert word_frequency('hello') == {'hello': 1}
    assert word_frequency('A a') == {'a': 2}
