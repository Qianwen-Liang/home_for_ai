"""测试用含 bug 脚本 — 用于验证自我修复闭环"""


def calculate_average(numbers):
    """计算平均值（已修复：空列表返回 None）"""
    if not numbers:
        return None
    total = sum(numbers)
    count = len(numbers)
    return total / count


def process_data(data):
    """处理数据（含 bug：未处理 None 元素）"""
    result = []
    for item in data:
        result.append(item.upper())
    return result


if __name__ == "__main__":
    print(calculate_average([1, 2, 3, 4]))
    print(process_data(["a", "b", "c"]))
