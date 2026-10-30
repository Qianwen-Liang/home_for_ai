"""
任务 t28: 平衡括号判断
难度: 困难
能力维度: L1-代码生成

实现 is_balanced(s)，判断字符串中的括号 ()[]{} 是否匹配。
"""

TASK_TITLE = "平衡括号判断"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "困难"

def is_balanced(s):
    pairs = {')': '(', ']': '[', '}': '{'}
    stack = []
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack
# ── 测试（自动评分，请勿修改）──
def _test():
    assert is_balanced('()') is True
    assert is_balanced('(]') is False
    assert is_balanced('([)]') is False
    assert is_balanced('{[]}') is True
    assert is_balanced('') is True
