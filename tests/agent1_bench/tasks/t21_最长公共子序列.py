"""
任务 t21: 最长公共子序列
难度: 困难
能力维度: L1-代码生成

实现 lcs(a, b)，返回两个字符串的最长公共子序列长度。
"""

TASK_TITLE = "最长公共子序列"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "困难"

def lcs(a, b):
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]
# ── 测试（自动评分，请勿修改）──
def _test():
    assert lcs('abcde', 'ace') == 3
    assert lcs('abc', 'def') == 0
    assert lcs('', 'abc') == 0
    assert lcs('aaa', 'aa') == 2
