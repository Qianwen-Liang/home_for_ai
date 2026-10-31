"""
工具系统自检脚本
================
验证所有工具模块是否能正确导入和运行基本功能。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def test_calculator() -> list[str]:
    """测试计算工具。"""
    from tools.calculator import Calculator, CalculationError, calculate

    results: list[str] = []
    calc = Calculator()

    # 测试基本运算（使用全局 calculate 函数）
    assert calculate("2 + 3") == "5", "加法失败"
    results.append("✅ 加法: 2 + 3 = 5")

    assert calculate("10 - 4") == "6", "减法失败"
    results.append("✅ 减法: 10 - 4 = 6")

    assert calculate("3 * 7") == "21", "乘法失败"
    results.append("✅ 乘法: 3 * 7 = 21")

    assert calculate("15 / 3") == "5", "除法失败"
    results.append("✅ 除法: 15 / 3 = 5")

    # 测试复杂表达式
    assert calculate("2 + 3 * 4") == "14", "运算优先级失败"
    results.append("✅ 复杂表达式: 2 + 3 * 4 = 14")

    # 测试类方法 evaluate
    assert calc.evaluate("2 + 3") == 5.0, "evaluate 加法失败"
    results.append("✅ evaluate 方法: 2 + 3 = 5.0")

    # 测试数学函数
    result_sqrt = calculate("sqrt(16)")
    assert result_sqrt == "4", f"sqrt(16) 预期 4，得到 {result_sqrt}"
    results.append("✅ 数学函数: sqrt(16) = 4")

    # 测试常量
    pi_result = calculate("pi")
    assert pi_result[:5] == "3.141", "pi 常量错误"
    results.append("✅ 数学常量: pi 可用")

    # 测试精度
    precise = calculate("pi", precision=2)
    assert precise == "3.14", f"精度计算错误: {precise}"
    results.append("✅ 精度控制: pi 保留2位小数 = 3.14")

    # 测试错误处理
    try:
        calc.evaluate("1 / 0")
        assert False, "除零错误未捕获"
    except CalculationError:
        results.append("✅ 错误处理: 除零错误正确捕获")

    # 测试 execute_calculator_tool 函数（工具接口）
    from tools.calculator import execute_calculator_tool
    tool_result = execute_calculator_tool({"expression": "sin(pi/2)", "precision": None})
    assert "1" in tool_result, f"sin(pi/2) 应接近 1，得到 {tool_result}"
    results.append(f"✅ 工具接口: execute_calculator_tool 正常")

    return results


def test_knowledge_store() -> list[str]:
    """测试知识库系统。"""
    from tools.knowledge_store import KnowledgeStore, execute_knowledge_tool

    results: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStore(Path(tmpdir) / "test_knowledge.json")

        # 使用 store 方法（实际的 API）
        store_result = store.store(
            "Python 简介",
            "Python 是一种高级编程语言。",
            category="programming",
            tags="python,编程",
        )
        assert "K" in store_result, f"存储应返回条目 ID，得到: {store_result}"
        results.append("✅ 添加知识条目成功")

        # 列表功能
        entries = store.list_entries()
        assert "Python 简介" in entries, "列表应包含条目标题"
        results.append("✅ 列出知识条目成功")

        # 搜索知识
        search_result = store.search("Python")
        assert "Python" in search_result, "搜索应返回相关结果"
        results.append("✅ 搜索知识条目成功")

        # 统计信息
        stats = store.stats()
        assert "1" in stats or "总条目" in stats, "统计信息应包含总条目数"
        results.append("✅ 知识库统计功能正常")

    # 测试工具接口
    tool_result = execute_knowledge_tool({
        "action": "stats",
    })
    assert "统计" in tool_result or "空" in tool_result, f"工具接口 stats 应正常，得到: {tool_result}"
    results.append("✅ 知识库工具接口正常")

    return results


def test_task_tracker() -> list[str]:
    """测试任务追踪器。"""
    from tools.task_tracker import TaskTracker, TaskStatus, execute_task_tracker_tool

    results: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = TaskTracker(Path(tmpdir) / "test_tasks.json")

        # 使用 create 方法（实际的 API）
        create_result = tracker.create("测试任务", "这是一个测试任务", phase="A")
        assert "T001" in create_result, f"创建应返回任务 ID，得到: {create_result}"
        results.append("✅ 创建任务成功")

        # 再创建一个任务
        tracker.create("第二个任务", phase="B")

        # 更新状态为进行中
        start_result = tracker.start("T001")
        assert "进行中" in start_result or "已开始" in start_result, f"开始任务失败: {start_result}"
        results.append("✅ 开始任务成功")

        # 标记完成
        complete_result = tracker.complete("T001")
        assert "完成" in complete_result, f"完成任务失败: {complete_result}"
        results.append("✅ 完成任务成功")

        # 生成报告
        report = tracker.report()
        assert "测试任务" in report, "报告应包含任务标题"
        results.append("✅ 生成任务报告成功")

        # 列出任务
        tasks = tracker.list_tasks()
        assert "T001" in tasks, "列出任务应包含任务"
        results.append("✅ 列出任务成功")

    # 测试工具接口
    tool_result = execute_task_tracker_tool({
        "action": "list",
    })
    assert "没有" not in tool_result or "任务" in tool_result, f"工具接口 list 应正常，得到: {tool_result}"
    results.append("✅ 任务追踪器工具接口正常")

    return results


def test_file_utils() -> list[str]:
    """测试文件工具集。"""
    from tools.file_utils import execute_file_utils_tool

    results: list[str] = []

    # 测试查找文件
    find_result = execute_file_utils_tool({
        "action": "find",
        "pattern": "calculator*",
        "limit": 5,
    })
    assert "calculator" in find_result, f"查找文件应找到 calculator，得到: {find_result}"
    results.append("✅ 文件查找功能正常")

    # 测试类型统计
    stats_result = execute_file_utils_tool({
        "action": "type_stats",
    })
    assert ".py" in stats_result, "类型统计应包含 .py 文件"
    results.append("✅ 文件类型统计功能正常")

    # 测试大小分析
    size_result = execute_file_utils_tool({
        "action": "size_analysis",
    })
    assert "文件" in size_result or "大小" in size_result, f"大小分析应正常: {size_result[:50]}"
    results.append("✅ 文件大小分析功能正常")

    # 测试最近文件
    recent_result = execute_file_utils_tool({
        "action": "recent_files",
        "limit": 5,
    })
    assert "文件" in recent_result or ":" in recent_result, f"最近文件应正常: {recent_result[:50]}"
    results.append("✅ 最近文件列表功能正常")

    return results


def test_runner() -> list[str]:
    """测试命令请求工具。"""
    from tools.runner import execute_runner_tool, RunnerError, pending_commands

    results: list[str] = []

    # 测试命令提交（不应实际执行）
    result = execute_runner_tool({"command": "echo hello", "timeout": 10})
    assert "等待用户批准" in result, f"命令提交应返回等待批准信息，得到: {result}"
    results.append("✅ 命令提交功能正常")

    # 测试待批准列表
    pending = pending_commands()
    assert "echo" in pending, "待批准列表应包含刚提交的命令"
    results.append("✅ 待批准列表功能正常")

    return results


def test_monitor() -> list[str]:
    """测试监控系统。"""
    from tools.monitor import execute_monitor_tool

    results: list[str] = []

    # 测试记录
    record = execute_monitor_tool({
        "action": "record",
        "tool_name": "test_tool",
        "duration": 0.1,
        "success": True,
    })
    assert "已记录" in record, f"记录应成功，得到: {record}"
    results.append("✅ 记录工具调用正常")

    # 测试摘要
    summary = execute_monitor_tool({"action": "summary"})
    assert "摘要" in summary or "运行" in summary, f"摘要应正常，得到: {summary[:50]}"
    results.append("✅ 监控摘要正常")

    return results


def test_safety_net() -> list[str]:
    """测试安全网系统。"""
    from tools.safety_net import execute_safety_net_tool

    results: list[str] = []

    # 测试检查
    check = execute_safety_net_tool({"action": "check"})
    assert "安全网" in check, f"检查应正常，得到: {check[:50]}"
    results.append("✅ 安全网检查正常")

    # 测试状态
    status = execute_safety_net_tool({"action": "status"})
    assert "安全网" in status or "状态" in status, f"状态应正常，得到: {status[:50]}"
    results.append("✅ 安全网状态正常")

    return results


def test_decision_engine() -> list[str]:
    """测试决策引擎。"""
    from tools.decision_engine import execute_decision_engine_tool

    results: list[str] = []

    # 测试建议
    advise = execute_decision_engine_tool({
        "action": "advise",
        "problem": "如何测试代码",
        "context": "我在进行工具测试",
    })
    assert "建议" in advise or "找到" in advise, f"建议应正常，得到: {advise[:50]}"
    results.append("✅ 决策建议功能正常")

    # 测试记录决策
    record = execute_decision_engine_tool({
        "action": "record_decision",
        "decision": "运行所有工具测试",
        "outcome": "测试通过",
    })
    assert "已记录" in record, f"记录决策应正常，得到: {record}"
    results.append("✅ 记录决策功能正常")

    return results


def main() -> int:
    """运行所有工具测试。"""
    print("=" * 50)
    print("🧪 Agent 1 工具系统自检")
    print("=" * 50)
    print()

    all_results: list[str] = []
    failures = 0

    tests = [
        ("计算器", test_calculator),
        ("知识库", test_knowledge_store),
        ("任务追踪器", test_task_tracker),
        ("文件工具集", test_file_utils),
        ("命令请求器", test_runner),
        ("监控系统", test_monitor),
        ("安全网", test_safety_net),
        ("决策引擎", test_decision_engine),
    ]

    for name, test_func in tests:
        print(f"📦 测试: {name}")
        print("-" * 30)
        try:
            results = test_func()
            all_results.extend(results)
            for r in results:
                print(f"  {r}")
        except Exception as exc:
            import traceback
            print(f"  ❌ 测试失败: {exc}")
            traceback.print_exc()
            failures += 1
        print()

    print("=" * 50)
    if failures == 0:
        print(f"🎉 所有测试通过！共 {len(all_results)} 项检查。")
    else:
        print(f"⚠️  有 {failures} 个模块测试失败。")
    print("=" * 50)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
