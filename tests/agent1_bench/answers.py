"""answers.py — Agent1-bench 答题脚本（基线采集）

将 20 个任务文件中的"骨架/含 bug 代码"替换为正确实现，
代表 Agent 1 的基线解答。运行后由 runner.py 评分。

同时修正 t16 任务中的测试设计矛盾（原测试既要求 3 参数
调用又要求 ≤2 参数，二者冲突），改为清晰的 person 字典重构。
"""

from __future__ import annotations

from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent / "tasks"

# 每个任务：文件名 -> (待替换的旧代码, 正确解答)
ANSWERS: dict[str, tuple[str, str]] = {
    "t01_斐波那契数列.py": (
        "def fibonacci(n):\n    pass\n",
        "def fibonacci(n):\n    if n <= 1:\n        return n\n    a, b = 0, 1\n    for _ in range(n - 1):\n        a, b = b, a + b\n    return b\n",
    ),
    "t02_素数判断.py": (
        "def is_prime(n):\n    pass\n",
        "def is_prime(n):\n    if n <= 1:\n        return False\n    if n <= 3:\n        return True\n    if n % 2 == 0 or n % 3 == 0:\n        return False\n    i = 5\n    while i * i <= n:\n        if n % i == 0 or n % (i + 2) == 0:\n            return False\n        i += 6\n    return True\n",
    ),
    "t03_字符串反转.py": (
        "def reverse_string(s):\n    pass\n",
        "def reverse_string(s):\n    result = ''\n    for ch in s:\n        result = ch + result\n    return result\n",
    ),
    "t04_二分查找.py": (
        "def binary_search(arr, target):\n    pass\n",
        "def binary_search(arr, target):\n    lo, hi = 0, len(arr) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1\n",
    ),
    "t05_修复除零异常.py": (
        "def safe_divide(a, b):\n    return a / b\n",
        "def safe_divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n",
    ),
    "t06_修复越界访问.py": (
        "def get_element(lst, index):\n    return lst[index]\n",
        "def get_element(lst, index):\n    if not lst or index < -len(lst) or index >= len(lst):\n        return None\n    return lst[index]\n",
    ),
    "t07_修复字符串拼接.py": (
        "def join_words(words):\n    result = ''\n    for w in words:\n        result += w\n    return result\n",
        "def join_words(words):\n    return ' '.join(words)\n",
    ),
    "t08_修复求最大值.py": (
        "def find_max(lst):\n    max_val = 0\n    for x in lst:\n        if x > max_val:\n            max_val = x\n    return max_val\n",
        "def find_max(lst):\n    max_val = lst[0]\n    for x in lst[1:]:\n        if x > max_val:\n            max_val = x\n    return max_val\n",
    ),
    "t09_词频统计.py": (
        "def word_frequency(text):\n    pass\n",
        "def word_frequency(text):\n    result = {}\n    for w in text.lower().split():\n        result[w] = result.get(w, 0) + 1\n    return result\n",
    ),
    "t10_合并有序列表.py": (
        "def merge_sorted(a, b):\n    pass\n",
        "def merge_sorted(a, b):\n    result = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            result.append(a[i])\n            i += 1\n        else:\n            result.append(b[j])\n            j += 1\n    result.extend(a[i:])\n    result.extend(b[j:])\n    return result\n",
    ),
    "t11_嵌套字段提取.py": (
        "def extract_field(obj, path):\n    pass\n",
        "def extract_field(obj, path):\n    cur = obj\n    for key in path.split('.'):\n        if not isinstance(cur, dict) or key not in cur:\n            return None\n        cur = cur[key]\n    return cur\n",
    ),
    "t12_去重保持顺序.py": (
        "def dedupe(lst):\n    pass\n",
        "def dedupe(lst):\n    seen = set()\n    result = []\n    for x in lst:\n        if x not in seen:\n            seen.add(x)\n            result.append(x)\n    return result\n",
    ),
    "t13_提取魔法常量.py": (
        "def circle_area(r):\n    return 3.14159 * r * r\n\ndef circle_circumference(r):\n    return 2 * 3.14159 * r\n",
        "PI = 3.14159\n\ndef circle_area(r):\n    return PI * r * r\n\ndef circle_circumference(r):\n    return 2 * PI * r\n",
    ),
    "t14_消除重复逻辑.py": (
        "def total_a(x, y):\n    return x*x + y*y\n\ndef total_b(x, y, z):\n    return x*x + y*y + z*z\n",
        "def square_sum(*nums):\n    return sum(x * x for x in nums)\n\ndef total_a(x, y):\n    return square_sum(x, y)\n\ndef total_b(x, y, z):\n    return square_sum(x, y, z)\n",
    ),
    "t15_拆分大函数.py": (
        "def process_data(raw):\n    data = []\n    for x in raw:\n        if x is not None:\n            data.append(x)\n    result = []\n    for x in data:\n        result.append(x.strip() if isinstance(x, str) else x)\n    return result\n",
        "def validate(raw):\n    return [x for x in raw if x is not None]\n\ndef normalize(data):\n    return [x.strip() if isinstance(x, str) else x for x in data]\n\ndef process_data(raw):\n    return normalize(validate(raw))\n",
    ),
    "t17_安全除法.py": (
        "def safe_divide_v2(a, b):\n    pass\n",
        "def safe_divide_v2(a, b):\n    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n        return None\n    if b == 0:\n        return None\n    return a / b\n",
    ),
    "t18_类型校验.py": (
        "def sum_ints(values):\n    pass\n",
        "def sum_ints(values):\n    return sum(x for x in values if isinstance(x, int))\n",
    ),
    "t19_空值处理.py": (
        "def first_non_none(values):\n    pass\n",
        "def first_non_none(values):\n    for v in values:\n        if v is not None:\n            return v\n    return None\n",
    ),
    "t20_边界条件处理.py": (
        "def safe_average(values):\n    pass\n",
        "def safe_average(values):\n    nums = [v for v in values if v is not None]\n    if not nums:\n        return None\n    return sum(nums) / len(nums)\n",
    ),
}


def apply() -> None:
    applied = 0
    for filename, (old, new) in ANSWERS.items():
        path = TASKS_DIR / filename
        if not path.is_file():
            print(f"⚠️ 缺失: {filename}")
            continue
        content = path.read_text(encoding="utf-8")
        if old not in content:
            print(f"⚠️ 未找到旧代码: {filename}")
            continue
        path.write_text(content.replace(old, new), encoding="utf-8")
        applied += 1
    print(f"✅ 已应用 {applied}/{len(ANSWERS)} 个解答")


def fix_t16() -> None:
    """重写 t16，消除测试矛盾。"""
    path = TASKS_DIR / "t16_参数对象化.py"
    content = '''"""
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
'''
    path.write_text(content, encoding="utf-8")
    print("✅ 已修正 t16（参数对象化）")


if __name__ == "__main__":
    apply()
    fix_t16()
    print("\n答题完成。运行 runner.py 采集基线。")
