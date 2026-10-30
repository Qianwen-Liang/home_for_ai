"""gen_tasks.py — Agent1-bench 任务生成脚本

一次性生成 tests/agent1_bench/tasks/ 下的 20 个基准任务文件。
每个任务文件含：任务元信息 + 初始代码（骨架或含 bug）+ 测试函数。

任务分类（对齐六层指标体系）：
  L1-代码生成   (t01~t04)  算法实现
  L2-诊断修复   (t05~t08)  Bug 修复
  L3-数据处理   (t09~t12)  实用编码
  L2-重构       (t13~t16)  代码结构改善
  L5-健壮性     (t17~t20)  防御编程
"""

from __future__ import annotations

from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent / "tasks"

TASKS = [
    # ── L1 代码生成 ──────────────────────────────────────
    {
        "id": "t01",
        "title": "斐波那契数列",
        "dimension": "L1-代码生成",
        "difficulty": "简单",
        "desc": "实现 fibonacci(n)，返回第 n 个斐波那契数（fib(0)=0, fib(1)=1）。",
        "initial_code": "def fibonacci(n):\n    pass\n",
        "test_code": "def _test():\n    assert fibonacci(0) == 0\n    assert fibonacci(1) == 1\n    assert fibonacci(2) == 1\n    assert fibonacci(10) == 55\n    assert fibonacci(15) == 610\n",
    },
    {
        "id": "t02",
        "title": "素数判断",
        "dimension": "L1-代码生成",
        "difficulty": "简单",
        "desc": "实现 is_prime(n)，判断 n 是否为素数（n<=1 返回 False）。",
        "initial_code": "def is_prime(n):\n    pass\n",
        "test_code": "def _test():\n    assert is_prime(2) is True\n    assert is_prime(3) is True\n    assert is_prime(4) is False\n    assert is_prime(17) is True\n    assert is_prime(1) is False\n    assert is_prime(0) is False\n",
    },
    {
        "id": "t03",
        "title": "字符串反转",
        "dimension": "L1-代码生成",
        "difficulty": "简单",
        "desc": "实现 reverse_string(s)，反转字符串，不使用切片 [::-1]。",
        "initial_code": "def reverse_string(s):\n    pass\n",
        "test_code": "def _test():\n    assert reverse_string('hello') == 'olleh'\n    assert reverse_string('') == ''\n    assert reverse_string('a') == 'a'\n    assert reverse_string('ab') == 'ba'\n",
    },
    {
        "id": "t04",
        "title": "二分查找",
        "dimension": "L1-代码生成",
        "difficulty": "中等",
        "desc": "实现 binary_search(arr, target)，在有序数组 arr 中查找 target，返回索引，不存在返回 -1。",
        "initial_code": "def binary_search(arr, target):\n    pass\n",
        "test_code": "def _test():\n    assert binary_search([1, 3, 5, 7, 9], 5) == 2\n    assert binary_search([1, 3, 5, 7, 9], 2) == -1\n    assert binary_search([], 1) == -1\n    assert binary_search([1], 1) == 0\n    assert binary_search([1, 2, 3], 3) == 2\n",
    },
    # ── L2 诊断修复 ──────────────────────────────────────
    {
        "id": "t05",
        "title": "修复除零异常",
        "dimension": "L2-诊断修复",
        "difficulty": "简单",
        "desc": "修复 safe_divide：当 b 为 0 时应返回 None，而不是抛出异常。",
        "initial_code": "def safe_divide(a, b):\n    return a / b\n",
        "test_code": "def _test():\n    assert safe_divide(10, 2) == 5.0\n    assert safe_divide(10, 0) is None\n    assert safe_divide(0, 5) == 0.0\n",
    },
    {
        "id": "t06",
        "title": "修复越界访问",
        "dimension": "L2-诊断修复",
        "difficulty": "简单",
        "desc": "修复 get_element：当索引越界或列表为空时返回 None，而不是抛 IndexError。",
        "initial_code": "def get_element(lst, index):\n    return lst[index]\n",
        "test_code": "def _test():\n    assert get_element([1, 2, 3], 1) == 2\n    assert get_element([1, 2, 3], 5) is None\n    assert get_element([], 0) is None\n    assert get_element([1, 2], -1) == 2\n",
    },
    {
        "id": "t07",
        "title": "修复字符串拼接",
        "dimension": "L2-诊断修复",
        "difficulty": "简单",
        "desc": "修复 join_words：应以单个空格连接单词，而不是直接拼接。",
        "initial_code": "def join_words(words):\n    result = ''\n    for w in words:\n        result += w\n    return result\n",
        "test_code": "def _test():\n    assert join_words(['a', 'b', 'c']) == 'a b c'\n    assert join_words([]) == ''\n    assert join_words(['single']) == 'single'\n    assert join_words(['hello', 'world']) == 'hello world'\n",
    },
    {
        "id": "t08",
        "title": "修复求最大值",
        "dimension": "L2-诊断修复",
        "difficulty": "简单",
        "desc": "修复 find_max：当列表全为负数时返回错误值（应返回实际最大值，而非初始的 0）。",
        "initial_code": "def find_max(lst):\n    max_val = 0\n    for x in lst:\n        if x > max_val:\n            max_val = x\n    return max_val\n",
        "test_code": "def _test():\n    assert find_max([1, 5, 3]) == 5\n    assert find_max([-5, -2, -9]) == -2\n    assert find_max([7]) == 7\n",
    },
    # ── L3 数据处理 ──────────────────────────────────────
    {
        "id": "t09",
        "title": "词频统计",
        "dimension": "L3-数据处理",
        "difficulty": "中等",
        "desc": "实现 word_frequency(text)，按空格分词（小写），返回单词频次字典。",
        "initial_code": "def word_frequency(text):\n    pass\n",
        "test_code": "def _test():\n    assert word_frequency('a b a') == {'a': 2, 'b': 1}\n    assert word_frequency('') == {}\n    assert word_frequency('hello') == {'hello': 1}\n    assert word_frequency('A a') == {'a': 2}\n",
    },
    {
        "id": "t10",
        "title": "合并有序列表",
        "dimension": "L3-数据处理",
        "difficulty": "中等",
        "desc": "实现 merge_sorted(a, b)，合并两个已排序列表，返回新的有序列表。",
        "initial_code": "def merge_sorted(a, b):\n    pass\n",
        "test_code": "def _test():\n    assert merge_sorted([1, 3], [2, 4]) == [1, 2, 3, 4]\n    assert merge_sorted([], [1]) == [1]\n    assert merge_sorted([1], []) == [1]\n    assert merge_sorted([1, 1], [1, 2]) == [1, 1, 1, 2]\n",
    },
    {
        "id": "t11",
        "title": "嵌套字段提取",
        "dimension": "L3-数据处理",
        "difficulty": "中等",
        "desc": "实现 extract_field(obj, path)，按点分路径（如 'a.b.c'）提取嵌套字段，缺失返回 None。",
        "initial_code": "def extract_field(obj, path):\n    pass\n",
        "test_code": "def _test():\n    assert extract_field({'a': {'b': 1}}, 'a.b') == 1\n    assert extract_field({'a': {}}, 'a.b') is None\n    assert extract_field({'a': {'b': {'c': 2}}}, 'a.b.c') == 2\n    assert extract_field({}, 'a') is None\n",
    },
    {
        "id": "t12",
        "title": "去重保持顺序",
        "dimension": "L3-数据处理",
        "difficulty": "简单",
        "desc": "实现 dedupe(lst)，去除重复元素并保持首次出现的顺序。",
        "initial_code": "def dedupe(lst):\n    pass\n",
        "test_code": "def _test():\n    assert dedupe([1, 2, 2, 3, 1]) == [1, 2, 3]\n    assert dedupe([]) == []\n    assert dedupe([5, 5, 5]) == [5]\n    assert dedupe(['a', 'b', 'a']) == ['a', 'b']\n",
    },
    # ── L2 重构 ──────────────────────────────────────────
    {
        "id": "t13",
        "title": "提取魔法常量",
        "dimension": "L2-重构",
        "difficulty": "中等",
        "desc": "重构：将重复出现的魔法数字 3.14159 提取为模块级常量 PI，并保持函数行为不变。",
        "initial_code": "def circle_area(r):\n    return 3.14159 * r * r\n\ndef circle_circumference(r):\n    return 2 * 3.14159 * r\n",
        "test_code": "def _test():\n    assert abs(circle_area(1) - 3.14159) < 1e-4\n    assert abs(circle_circumference(1) - 6.28318) < 1e-4\n    import sys\n    mod = sys.modules[__name__]\n    assert hasattr(mod, 'PI'), '应提取模块级常量 PI'\n",
    },
    {
        "id": "t14",
        "title": "消除重复逻辑",
        "dimension": "L2-重构",
        "difficulty": "中等",
        "desc": "重构：两个函数含重复的平方和计算逻辑，提取公共函数 square_sum，保持行为不变。",
        "initial_code": "def total_a(x, y):\n    return x*x + y*y\n\ndef total_b(x, y, z):\n    return x*x + y*y + z*z\n",
        "test_code": "def _test():\n    assert total_a(3, 4) == 25\n    assert total_b(1, 2, 3) == 14\n    import sys\n    mod = sys.modules[__name__]\n    assert hasattr(mod, 'square_sum'), '应提取公共函数 square_sum'\n",
    },
    {
        "id": "t15",
        "title": "拆分大函数",
        "dimension": "L2-重构",
        "difficulty": "较难",
        "desc": "重构：将 process_data 拆分为 validate 与 normalize 两个函数，保持行为不变。",
        "initial_code": "def process_data(raw):\n    data = []\n    for x in raw:\n        if x is not None:\n            data.append(x)\n    result = []\n    for x in data:\n        result.append(x.strip() if isinstance(x, str) else x)\n    return result\n",
        "test_code": "def _test():\n    assert process_data([' a ', None, 'b']) == ['a', 'b']\n    assert process_data([]) == []\n    import sys\n    mod = sys.modules[__name__]\n    assert hasattr(mod, 'validate') and hasattr(mod, 'normalize'), '应拆分出 validate 与 normalize'\n",
    },
    {
        "id": "t16",
        "title": "参数对象化",
        "dimension": "L2-重构",
        "difficulty": "较难",
        "desc": "重构：将散落的关联参数（name/age/city）合并为字典 person，保持 create_greeting 行为不变。",
        "initial_code": "def create_greeting(name, age, city):\n    return f'{name} is {age} years old from {city}'\n",
        "test_code": "def _test():\n    assert create_greeting('Alice', 30, 'NY') == 'Alice is 30 years old from NY'\n    import inspect\n    sig = inspect.signature(create_greeting)\n    params = list(sig.parameters.keys())\n    assert len(params) <= 2, f'应合并参数（当前 {len(params)} 个），建议 person 字典'\n",
    },
    # ── L5 健壮性 ────────────────────────────────────────
    {
        "id": "t17",
        "title": "安全除法",
        "dimension": "L5-健壮性",
        "difficulty": "简单",
        "desc": "实现 safe_divide_v2(a, b)：b 为 0 返回 None，a 或 b 非数字返回 None。",
        "initial_code": "def safe_divide_v2(a, b):\n    pass\n",
        "test_code": "def _test():\n    assert safe_divide_v2(10, 2) == 5.0\n    assert safe_divide_v2(10, 0) is None\n    assert safe_divide_v2('a', 2) is None\n    assert safe_divide_v2(10, 'b') is None\n",
    },
    {
        "id": "t18",
        "title": "类型校验",
        "dimension": "L5-健壮性",
        "difficulty": "简单",
        "desc": "实现 sum_ints(values)：仅累加 int 类型元素，忽略其他类型，返回总和。",
        "initial_code": "def sum_ints(values):\n    pass\n",
        "test_code": "def _test():\n    assert sum_ints([1, 2, 3]) == 6\n    assert sum_ints([1, 'a', 2.5, 3]) == 4\n    assert sum_ints([]) == 0\n    assert sum_ints(['x', 'y']) == 0\n",
    },
    {
        "id": "t19",
        "title": "空值处理",
        "dimension": "L5-健壮性",
        "difficulty": "简单",
        "desc": "实现 first_non_none(values)：返回第一个非 None 元素，全为 None 返回 None。",
        "initial_code": "def first_non_none(values):\n    pass\n",
        "test_code": "def _test():\n    assert first_non_none([None, 2, 3]) == 2\n    assert first_non_none([None, None]) is None\n    assert first_non_none([]) is None\n    assert first_non_none([0, None]) == 0\n",
    },
    {
        "id": "t20",
        "title": "边界条件处理",
        "dimension": "L5-健壮性",
        "difficulty": "中等",
        "desc": "实现 safe_average(values)：返回平均值，空列表返回 None，忽略 None 元素。",
        "initial_code": "def safe_average(values):\n    pass\n",
        "test_code": "def _test():\n    assert safe_average([1, 2, 3]) == 2.0\n    assert safe_average([]) is None\n    assert safe_average([None, 2, 4]) == 3.0\n    assert safe_average([None, None]) is None\n",
    },
]


def generate() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        content = f'''"""
任务 {task["id"]}: {task["title"]}
难度: {task["difficulty"]}
能力维度: {task["dimension"]}

{task["desc"]}
"""

TASK_TITLE = "{task["title"]}"
TASK_DIMENSION = "{task["dimension"]}"
TASK_DIFFICULTY = "{task["difficulty"]}"

{task["initial_code"]}# ── 测试（自动评分，请勿修改）──
{task["test_code"]}'''
        path = TASKS_DIR / f"{task['id']}_{task['title']}.py"
        path.write_text(content, encoding="utf-8")
        print(f"✅ 生成 {path.name}")

    print(f"\n共生成 {len(TASKS)} 个任务文件 → {TASKS_DIR}")


if __name__ == "__main__":
    generate()
