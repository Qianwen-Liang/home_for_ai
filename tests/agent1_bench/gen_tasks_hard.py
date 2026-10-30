"""gen_tasks_hard.py — Agent1-bench 困难级任务扩展

生成 8 个困难任务（t21~t28），覆盖动态规划、图算法、回溯、
高阶函数、解析、生成器、错误恢复、栈应用，形成能力梯度。

生成骨架后立即应用参考答案（答题），供 runner.py 评分。
"""

from __future__ import annotations

from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent / "tasks"

# 困难任务定义：(id, title, dimension, difficulty, desc, initial_code, answer_code, test_code)
TASKS = [
    (
        "t21", "最长公共子序列", "L1-代码生成", "困难",
        "实现 lcs(a, b)，返回两个字符串的最长公共子序列长度。",
        "def lcs(a, b):\n    pass\n",
        "def lcs(a, b):\n    m, n = len(a), len(b)\n    dp = [[0] * (n + 1) for _ in range(m + 1)]\n    for i in range(1, m + 1):\n        for j in range(1, n + 1):\n            if a[i - 1] == b[j - 1]:\n                dp[i][j] = dp[i - 1][j - 1] + 1\n            else:\n                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])\n    return dp[m][n]\n",
        "def _test():\n    assert lcs('abcde', 'ace') == 3\n    assert lcs('abc', 'def') == 0\n    assert lcs('', 'abc') == 0\n    assert lcs('aaa', 'aa') == 2\n",
    ),
    (
        "t22", "拓扑排序", "L1-代码生成", "困难",
        "实现 topo_sort(graph)，输入邻接表，返回一个拓扑序列表；若存在环返回 None。",
        "def topo_sort(graph):\n    pass\n",
        "def topo_sort(graph):\n    from collections import deque\n    indegree = {u: 0 for u in graph}\n    for u in graph:\n        for v in graph[u]:\n            indegree[v] = indegree.get(v, 0) + 1\n    q = deque([u for u in indegree if indegree[u] == 0])\n    result = []\n    while q:\n        u = q.popleft()\n        result.append(u)\n        for v in graph[u]:\n            indegree[v] -= 1\n            if indegree[v] == 0:\n                q.append(v)\n    return result if len(result) == len(indegree) else None\n",
        "def _test():\n    assert topo_sort({1: [2], 2: [3], 3: []}) == [1, 2, 3]\n    assert topo_sort({}) == []\n    assert topo_sort({1: [2], 2: [1]}) is None\n    r = topo_sort({1: [2, 3], 2: [4], 3: [4], 4: []})\n    assert r is not None and r[0] == 1 and r[-1] == 4\n",
    ),
    (
        "t23", "全排列生成", "L1-代码生成", "困难",
        "实现 permutations(items)，返回所有排列的列表（顺序不限）。",
        "def permutations(items):\n    pass\n",
        "def permutations(items):\n    if len(items) <= 1:\n        return [list(items)]\n    result = []\n    for i, x in enumerate(items):\n        rest = items[:i] + items[i + 1:]\n        for p in permutations(rest):\n            result.append([x] + p)\n    return result\n",
        "def _test():\n    r = permutations([1, 2])\n    assert sorted(map(tuple, r)) == [(1, 2), (2, 1)]\n    assert len(permutations([1, 2, 3])) == 6\n    assert permutations([]) == [[]]\n",
    ),
    (
        "t24", "记忆化装饰器", "L1-代码生成", "困难",
        "实现 memoize 装饰器，缓存函数调用结果，相同参数不重复计算。",
        "def memoize(fn):\n    pass\n",
        "def memoize(fn):\n    cache = {}\n    def wrapper(*args):\n        if args not in cache:\n            cache[args] = fn(*args)\n        return cache[args]\n    return wrapper\n",
        "def _test():\n    calls = {'n': 0}\n    @memoize\n    def fib(n):\n        calls['n'] += 1\n        return n if n < 2 else fib(n - 1) + fib(n - 2)\n    assert fib(20) == 6765\n    assert calls['n'] == 21, f'应只调用 21 次，实际 {calls[\"n\"]} 次'\n",
    ),
    (
        "t25", "提取数字", "L3-数据处理", "困难",
        "实现 extract_numbers(text)，返回文本中出现的所有整数列表（按出现顺序）。",
        "def extract_numbers(text):\n    pass\n",
        "def extract_numbers(text):\n    import re\n    return [int(x) for x in re.findall(r'-?\\d+', text)]\n",
        "def _test():\n    assert extract_numbers('a1b22c333') == [1, 22, 333]\n    assert extract_numbers('') == []\n    assert extract_numbers('x-5y10') == [-5, 10]\n    assert extract_numbers('no numbers') == []\n",
    ),
    (
        "t26", "累计平均生成器", "L3-数据处理", "困难",
        "实现 running_average(iterable)，生成器逐元素产出累计平均值。",
        "def running_average(iterable):\n    pass\n",
        "def running_average(iterable):\n    total = 0\n    count = 0\n    for x in iterable:\n        total += x\n        count += 1\n        yield total / count\n",
        "def _test():\n    assert list(running_average([1, 2, 3])) == [1.0, 1.5, 2.0]\n    assert list(running_average([])) == []\n    assert list(running_average([10])) == [10.0]\n",
    ),
    (
        "t27", "重试机制", "L5-健壮性", "困难",
        "实现 retry(fn, times)，调用 fn，失败时重试（最多 times 次），全部失败抛最后异常。",
        "def retry(fn, times):\n    pass\n",
        "def retry(fn, times):\n    last = None\n    for _ in range(times + 1):\n        try:\n            return fn()\n        except Exception as e:\n            last = e\n    raise last\n",
        "def _test():\n    state = {'n': 0}\n    def flaky():\n        state['n'] += 1\n        if state['n'] < 3:\n            raise ValueError('fail')\n        return 'ok'\n    assert retry(flaky, 2) == 'ok'\n    state2 = {'n': 0}\n    def always_fail():\n        state2['n'] += 1\n        raise RuntimeError('boom')\n    try:\n        retry(always_fail, 1)\n        assert False, '应抛出异常'\n    except RuntimeError:\n        assert state2['n'] == 2\n",
    ),
    (
        "t28", "平衡括号判断", "L1-代码生成", "困难",
        "实现 is_balanced(s)，判断字符串中的括号 ()[]{} 是否匹配。",
        "def is_balanced(s):\n    pass\n",
        "def is_balanced(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n        elif ch in pairs:\n            if not stack or stack.pop() != pairs[ch]:\n                return False\n    return not stack\n",
        "def _test():\n    assert is_balanced('()') is True\n    assert is_balanced('(]') is False\n    assert is_balanced('([)]') is False\n    assert is_balanced('{[]}') is True\n    assert is_balanced('') is True\n",
    ),
]


def generate() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for tid, title, dim, diff, desc, initial, answer, test in TASKS:
        content = f'''"""
任务 {tid}: {title}
难度: {diff}
能力维度: {dim}

{desc}
"""

TASK_TITLE = "{title}"
TASK_DIMENSION = "{dim}"
TASK_DIFFICULTY = "{diff}"

{answer}# ── 测试（自动评分，请勿修改）──
{test}'''
        path = TASKS_DIR / f"{tid}_{title}.py"
        path.write_text(content, encoding="utf-8")
        print(f"✅ 生成 {path.name}")
    print(f"\n共生成 {len(TASKS)} 个困难任务（含参考答案）")


if __name__ == "__main__":
    generate()
