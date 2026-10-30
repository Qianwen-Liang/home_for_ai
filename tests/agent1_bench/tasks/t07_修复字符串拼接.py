"""
任务 t07: 修复字符串拼接
难度: 简单
能力维度: L2-诊断修复

修复 join_words：应以单个空格连接单词，而不是直接拼接。
"""

TASK_TITLE = "修复字符串拼接"
TASK_DIMENSION = "L2-诊断修复"
TASK_DIFFICULTY = "简单"

def join_words(words):
    return ' '.join(words)
# ── 测试（自动评分，请勿修改）──
def _test():
    assert join_words(['a', 'b', 'c']) == 'a b c'
    assert join_words([]) == ''
    assert join_words(['single']) == 'single'
    assert join_words(['hello', 'world']) == 'hello world'
