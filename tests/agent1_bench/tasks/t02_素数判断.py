"""
任务 t02: 素数判断
难度: 简单
能力维度: L1-代码生成

实现 is_prime(n)，判断 n 是否为素数（n<=1 返回 False）。
"""

TASK_TITLE = "素数判断"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "简单"

def is_prime(n):
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True
# ── 测试（自动评分，请勿修改）──
def _test():
    assert is_prime(2) is True
    assert is_prime(3) is True
    assert is_prime(4) is False
    assert is_prime(17) is True
    assert is_prime(1) is False
    assert is_prime(0) is False
