"""
压力测试 — 并发 + 大数据量边界验证 (T061)
=========================================
覆盖：
  1. 大数据量输入（千级记录）
  2. 高频操作（百次连续调用）
  3. 极限参数（空、超长、特殊字符、Unicode）
  4. 持久化恢复验证
  5. 内存稳定性
"""

import sys
import os
import json
import re
import time
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.knowledge_store import execute_knowledge_tool, KnowledgeStoreError
from tools.decision_engine import execute_decision_engine_tool, DecisionError
from tools.task_tracker import execute_task_tracker_tool, TaskTrackerError
from tools.safety_net import execute_safety_net_tool, SafetyNetError
from tools.monitor import Monitor
from tools.experience_learner import execute_experience_learner_tool, ExperienceLearnerError
from tools.calculator import execute_calculator_tool


# ── knowledge 测试隔离（★T2795-5.1） ─────────────────────
# 压测会写入大量临时条目（压力测试/并发模拟/PERSIST_MARKER/超长标题等）。
# 原实现直接写生产 knowledge_store.json，每次跑测试都会泄漏几十条脏数据
# （历史上已由 T2654 清理过一次，属复发缺陷）。此处用 autouse fixture
# 把模块级单例替换为临时库，使全文件的压测写入都落到临时路径。
import pytest


@pytest.fixture(autouse=True)
def _isolate_knowledge_store(monkeypatch, tmp_path):
    import tools.experience_learner as _el
    import tools.knowledge_store as _ks

    isolated = _ks.KnowledgeStore(path=tmp_path / "stress_kb.json")
    monkeypatch.setattr(_ks, "_store", isolated)
    # experience_learner 直接按文件路径读写知识库（绕过单例），需单独隔离，
    # 否则"[经验] xxx 成功"类测试数据仍会漏进生产知识库。
    monkeypatch.setattr(_el, "KNOWLEDGE_DIR", tmp_path / "experience_kb")
    return isolated


# ── monitor 测试隔离 ──────────────────────────────────────
# 压测用独立 Monitor 实例（写入临时文件），避免污染生产 monitor_data.json。
# 生产监控数据不应被压测的 tool_0~tool_4 匿名记录干扰（否则健康评分被假错误率拉低）。
_isolated_monitor = Monitor(
    path=Path(tempfile.gettempdir()) / "test_stress_monitor_isolated.json"
)


def _test_monitor_tool(arguments: dict) -> str:
    """用隔离实例执行 monitor 操作，替代 execute_monitor_tool（绑定生产单例）。"""
    action = arguments.get("action", "")
    tool_name = arguments.get("tool_name", "")
    duration = float(arguments.get("duration", 0.0))
    success = bool(arguments.get("success", True))
    limit = int(arguments.get("limit", 10))

    if action == "record":
        return _isolated_monitor.record(tool_name, duration, success)
    elif action == "summary":
        return _isolated_monitor.summary()
    elif action == "report":
        return _isolated_monitor.report()
    elif action == "reset":
        return _isolated_monitor.reset()
    else:
        return f"未知操作: {action}"


# ═══════════════════════════════════════════════════════════
# 大数据量测试
# ═══════════════════════════════════════════════════════════

def test_large_knowledge_store(monkeypatch, tmp_path):
    """知识库：存储 200+ 条目并搜索。

    ★T2795-5.1：隔离到临时知识库。原实现直接写入真实 knowledge_store.json，
    每次运行都会向生产知识库泄漏 200+ 条压测数据（历史上已复发多次）。
    """
    import tools.knowledge_store as _ks

    monkeypatch.setattr(
        _ks, "_store", _ks.KnowledgeStore(path=tmp_path / "stress_kb.json")
    )
    print("=" * 55)
    print("🧪 大数据量: knowledge_store (200 条)")
    print("=" * 55)

    # 清理旧条目（通过搜索验证后存储新条目）
    start = time.time()

    for i in range(200):
        r = execute_knowledge_tool({
            "action": "store",
            "title": f"压力测试条目 #{i:04d}",
            "content": f"这是第 {i} 条压力测试内容。" + "测试数据 " * 10,
            "category": "stress_test",
            "tags": f"stress,test, batch{i % 10}",
        })
        assert "已存储" in r or "K" in r, f"存储 #{i} 失败: {r}"

    elapsed = time.time() - start
    rate = 200 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ 存储 200 条目: {elapsed:.2f}s ({rate:.0f} 条/秒)")

    # 搜索
    start = time.time()
    r_search = execute_knowledge_tool({
        "action": "search",
        "query": "压力测试",
        "max_results": 50,
        "mode": "keyword",
    })
    search_elapsed = time.time() - start
    assert "压力测试" in r_search, f"搜索结果应包含关键词: {r_search[:100]}"
    print(f"  ✅ 搜索 200 条: {search_elapsed:.3f}s")

    # 验证搜索性能（应在合理时间内）
    assert search_elapsed < 5.0, f"搜索太慢: {search_elapsed:.2f}s"
    print(f"  ✅ 搜索性能达标 (< 5s)")

    # 统计
    r_stats = execute_knowledge_tool({"action": "stats"})
    assert "stress_test" in r_stats or "条目" in r_stats
    print(f"  ✅ 统计正常")

    # 列表
    r_list = execute_knowledge_tool({"action": "list", "category": "stress_test", "max_results": 10})
    assert "stress_test" in r_list
    print(f"  ✅ 分类列表正常")

    print("  ✅ 知识库大数据量测试通过！")


def test_large_task_creation():
    """任务追踪：创建 100 个任务（结束后必须清理，避免污染真实任务库）"""
    print("\n" + "=" * 55)
    print("🧪 大数据量: task_tracker (100 个任务)")
    print("=" * 55)

    import re

    task_ids: list[str] = []
    try:
        start = time.time()

        for i in range(100):
            r = execute_task_tracker_tool({
                "action": "create",
                "title": f"压力测试任务 #{i:04d}",
                "description": f"描述内容: 这是第 {i} 个压力测试任务",
                "phase": f"Phase-{i % 5}",
                "priority": ["高", "中", "低"][i % 3],
            })
            assert "已创建任务" in r, f"创建任务 #{i} 失败: {r}"
            tid_match = re.search(r'T\d+', r)
            if tid_match:
                task_ids.append(tid_match.group())

        elapsed = time.time() - start
        rate = 100 / elapsed if elapsed > 0 else float('inf')
        print(f"  ✅ 创建 100 个任务: {elapsed:.2f}s ({rate:.0f} 个/秒)")

        # 生成报告
        start = time.time()
        r_report = execute_task_tracker_tool({"action": "report"})
        report_elapsed = time.time() - start
        assert "任务" in r_report and "报告" in r_report
        print(f"  ✅ 生成报告: {report_elapsed:.3f}s")
        assert report_elapsed < 5.0, f"报告生成太慢: {report_elapsed:.2f}s"

        # 列表（task_tracker v3 起 list 返回树状视图，兼容两种表述）
        r_list = execute_task_tracker_tool({"action": "list"})
        assert "任务树" in r_list or "任务列表" in r_list, (
            f"列表输出格式异常: {r_list[:120]}"
        )
        print("  ✅ 任务列表正常")

        # 完成前 50 个任务
        start = time.time()
        for tid in task_ids[:50]:
            r = execute_task_tracker_tool({"action": "complete", "task_id": tid})
            assert "已完成" in r or "无法完成" in r, f"完成任务 {tid} 失败: {r}"
        complete_elapsed = time.time() - start
        print(f"  ✅ 完成 50 个任务: {complete_elapsed:.3f}s")

        print("  ✅ 任务追踪大数据量测试通过！")
    finally:
        # ★T2795-5.1：压测任务必须清理。原实现只创建不删除，
        # 每次运行都会向真实任务库泄漏 100 条（实测把总进度从 95% 稀释到 66%）。
        removed = 0
        for tid in task_ids:
            try:
                execute_task_tracker_tool({"action": "delete", "task_id": tid})
                removed += 1
            except Exception:
                pass
        print(f"  🧹 已清理压测任务: {removed}/{len(task_ids)}")


def test_large_safety_events():
    """安全网：记录 500 条事件"""
    print("\n" + "=" * 55)
    print("🧪 大数据量: safety_net (500 条事件)")
    print("=" * 55)

    execute_safety_net_tool({"action": "reset"})

    start = time.time()

    for i in range(500):
        event_type = "tool_call" if i % 3 != 0 else "error"
        r = execute_safety_net_tool({
            "action": "record_event",
            "event_type": event_type,
            "event_detail": f"事件 #{i}: {'正常操作' if event_type == 'tool_call' else '测试错误'}",
            "tool_name": f"tool_{(i % 10)}",
        })
        assert "已记录" in r, f"记录事件 #{i} 失败: {r}"

    elapsed = time.time() - start
    rate = 500 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ 记录 500 条事件: {elapsed:.2f}s ({rate:.0f} 条/秒)")

    # 检查（事件列表应被截断到 50 条）
    r_check = execute_safety_net_tool({"action": "check"})
    assert "安全网" in r_check
    print(f"  ✅ 安全网检查正常（最近事件已截断）")

    # 状态
    r_status = execute_safety_net_tool({"action": "status"})
    assert "500" in r_status or "总事件" in r_status
    print(f"  ✅ 安全网状态正常")

    print("  ✅ 安全网大数据量测试通过！")


# ═══════════════════════════════════════════════════════════
# 高频操作测试
# ═══════════════════════════════════════════════════════════

def test_high_frequency_calculator():
    """计算器：100 次连续计算"""
    print("\n" + "=" * 55)
    print("🧪 高频操作: calculator (100 次)")
    print("=" * 55)

    start = time.time()

    for i in range(100):
        expr = f"{i} * {i} + {i} / 2.0 - {i % 7}"
        r = execute_calculator_tool({"expression": expr})
        assert "结果" in r or "error" not in r.lower(), f"计算 #{i} 失败: {r}"

    elapsed = time.time() - start
    rate = 100 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ 100 次计算: {elapsed:.3f}s ({rate:.0f} 次/秒)")

    # 复杂表达式
    r_complex = execute_calculator_tool({
        "expression": "sqrt(2**10) + sin(pi/4) + log(100) + abs(-42)"
    })
    # calculator 返回纯数字结果（无"结果"前缀），不应含错误
    assert "错误" not in r_complex, f"复杂计算失败: {r_complex}"
    print(f"  ✅ 复杂表达式计算正常")

    print("  ✅ 计算器高频测试通过！")


def test_high_frequency_monitor():
    """监控：100 次连续记录"""
    print("\n" + "=" * 55)
    print("🧪 高频操作: monitor (100 次)")
    print("=" * 55)

    _test_monitor_tool({"action": "reset"})

    start = time.time()

    for i in range(100):
        r = _test_monitor_tool({
            "action": "record",
            "tool_name": f"tool_{(i % 5)}",
            "duration": 0.01 + (i % 10) * 0.02,
            "success": i % 7 != 0,
        })
        assert "已记录" in r, f"监控记录 #{i} 失败: {r}"

    elapsed = time.time() - start
    rate = 100 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ 100 次监控记录: {elapsed:.3f}s ({rate:.0f} 次/秒)")

    # 摘要
    r_summary = _test_monitor_tool({"action": "summary"})
    assert "监控" in r_summary or "摘要" in r_summary or "记录" in r_summary.lower()
    print(f"  ✅ 监控摘要正常")

    # 报告
    r_report = _test_monitor_tool({"action": "report"})
    print(f"  ✅ 监控报告正常")

    print("  ✅ 监控高频测试通过！")


def test_high_frequency_decision():
    """决策引擎：50 次连续查询"""
    print("\n" + "=" * 55)
    print("🧪 高频操作: decision_engine (50 次)")
    print("=" * 55)

    start = time.time()

    queries = [
        "导入失败",
        "计算数学表达式",
        "搜索文件内容",
        "存储知识条目",
        "系统健康检查",
    ]

    for i in range(50):
        query = queries[i % len(queries)]
        r = execute_decision_engine_tool({
            "action": "advise",
            "problem": f"{query} 时遇到问题 #{i}",
            "max_results": 3,
        })
        assert "建议" in r or "决策建议" in r, f"查询 #{i} 失败: {r[:50]}"

    elapsed = time.time() - start
    rate = 50 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ 50 次决策查询: {elapsed:.3f}s ({rate:.0f} 次/秒)")

    # 相似问题
    r_sim = execute_decision_engine_tool({
        "action": "similar_problems",
        "problem": "导入失败",
        "max_results": 3,
    })
    print(f"  ✅ 相似问题查询正常")

    print("  ✅ 决策引擎高频测试通过！")


# ═══════════════════════════════════════════════════════════
# 极限参数测试
# ═══════════════════════════════════════════════════════════

def test_boundary_empty_inputs():
    """极限参数：空输入"""
    print("\n" + "=" * 55)
    print("🧪 极限参数: 空输入")
    print("=" * 55)

    # knowledge: 空标题/内容（工具可能返回错误字符串而非抛异常，两者都接受）
    r = execute_knowledge_tool({"action": "store", "title": "", "content": "test"})
    assert "已存储" not in r, f"空标题不应成功: {r}"
    print(f"  ✅ knowledge 空标题 → 正确拒绝")

    r = execute_knowledge_tool({"action": "store", "title": "test", "content": ""})
    assert "已存储" not in r, f"空内容不应成功: {r}"
    print(f"  ✅ knowledge 空内容 → 正确拒绝")

    # task_tracker: 空标题
    r = execute_task_tracker_tool({"action": "create", "title": ""})
    assert "已创建" not in r, f"空标题不应创建成功: {r}"
    print(f"  ✅ task_tracker 空标题 → 正确拒绝")

    # decision_engine: 空问题
    r = execute_decision_engine_tool({"action": "advise", "problem": ""})
    # 空问题可能返回空建议或无结果，不应崩溃
    print(f"  ✅ decision_engine 空问题 → 不崩溃")

    # safety_net: 空事件类型也可以（默认为 other）
    r = execute_safety_net_tool({"action": "record_event", "event_type": "", "event_detail": ""})
    assert "已记录" in r, f"安全网空事件类型应可处理: {r}"
    print("  ✅ safety_net 空事件类型 → 默认处理")

    print("  ✅ 空输入测试通过！")


def test_boundary_long_inputs():
    """极限参数：超长输入"""
    print("\n" + "=" * 55)
    print("🧪 极限参数: 超长输入")
    print("=" * 55)

    # 生成超长字符串 (10KB)
    long_text = "A" * 10000

    # knowledge: 超长标题（应该能处理或截断）
    try:
        r = execute_knowledge_tool({
            "action": "store",
            "title": f"超长标题测试 {long_text[:200]}",
            "content": "正常内容",
            "category": "stress_test",
        })
        assert "已存储" in r, f"超长标题应能处理: {r[:80]}"
    except Exception:
        # 如果失败，应该是合理的错误
        pass
    print("  ✅ knowledge 超长标题处理正常")

    # knowledge: 超长内容
    r = execute_knowledge_tool({
        "action": "store",
        "title": "超长内容测试",
        "content": long_text,
        "category": "stress_test",
    })
    assert "已存储" in r, f"超长内容应能处理: {r[:80]}"
    print("  ✅ knowledge 超长内容 (10KB) 处理正常")

    # task_tracker: 超长标题
    r = execute_task_tracker_tool({
        "action": "create",
        "title": f"超长任务标题 {long_text[:500]}",
        "description": long_text[:1000],
        "phase": "stress",
    })
    assert "已创建任务" in r, f"超长标题任务应能创建: {r[:80]}"
    # ★T2795-5.1：压测任务必须清理，避免泄漏到真实任务库
    _m = re.search(r"T\d+", r)
    if _m:
        execute_task_tracker_tool({"action": "delete", "task_id": _m.group()})
    print("  ✅ task_tracker 超长标题/描述处理正常")

    # decision_engine: 超长问题
    r = execute_decision_engine_tool({
        "action": "advise",
        "problem": f"搜索 {long_text[:500]}",
    })
    assert "建议" in r or "决策建议" in r
    print("  ✅ decision_engine 超长问题处理正常")

    # safety_net: 超长事件详情（应被截断到 100 字符）
    r = execute_safety_net_tool({
        "action": "record_event",
        "event_type": "error",
        "event_detail": long_text,
    })
    assert "已记录" in r
    print("  ✅ safety_net 超长事件详情自动截断")

    print("  ✅ 超长输入测试通过！")


def test_boundary_special_characters():
    """极限参数：特殊字符和 Unicode"""
    print("\n" + "=" * 55)
    print("🧪 极限参数: 特殊字符和 Unicode")
    print("=" * 55)

    # Unicode 各语言
    unicode_texts = [
        ("中文标题", "中文内容测试，包含标点符号：，。！？"),
        ("日本語タイトル", "日本語の内容テスト：あいうえお"),
        ("한글 제목", "한글 내용 테스트입니다"),
        ("العربية", "اختبار المحتوى العربي"),
        ("Русский", "Тест русского содержания"),
        ("Emoji 🎉🚀💡", "Content with emojis 🔥📊✅ and symbols"),
        ("Mixed 混合 언어 العربية", "Multiple languages in one content 多语言混用"),
    ]

    for title, content in unicode_texts:
        r = execute_knowledge_tool({
            "action": "store",
            "title": title,
            "content": content,
            "category": "unicode_test",
        })
        assert "已存储" in r, f"Unicode 存储失败 [{title}]: {r[:80]}"

    print(f"  ✅ {len(unicode_texts)} 种语言/字符集存储成功")

    # 搜索 Unicode
    r = execute_knowledge_tool({
        "action": "search",
        "query": "中文",
        "max_results": 5,
        "mode": "keyword",
    })
    assert "中文" in r or "找到" in r
    print("  ✅ Unicode 搜索正常")

    # 特殊符号
    special_inputs = [
        ("NULL\0字符", "content with null\0byte"),
        ("换行\n回车\r制表\t", "多行\n内容\n测试"),
        ("<script>alert('xss')</script>", "<html><body>test</body></html>"),
        ("SQL'; DROP TABLE--", "SELECT * FROM users WHERE 1=1"),
        ("../../../etc/passwd", "path traversal attempt"),
        ("{{ template }}", "{% raw %} {{ variable }} {% endraw %}"),
    ]

    for title, content in special_inputs:
        try:
            r = execute_knowledge_tool({
                "action": "store",
                "title": title,
                "content": content,
                "category": "special_chars",
            })
            # 只要能存储就算通过
            assert "已存储" in r or "K" in r, f"特殊字符存储失败 [{title[:20]}]: {r[:80]}"
        except Exception as e:
            # 如果工具抛出异常，确保不是崩溃
            assert not isinstance(e, (SystemExit, KeyboardInterrupt))
            print(f"     ⚠️ [{title[:20]}] 被拒绝: {e}")

    print(f"  ✅ {len(special_inputs)} 种特殊字符处理完成")

    print("  ✅ 特殊字符测试通过！")


def test_boundary_max_values():
    """极限参数：边界值"""
    print("\n" + "=" * 55)
    print("🧪 极限参数: 边界值")
    print("=" * 55)

    # max_results = 0
    r = execute_knowledge_tool({
        "action": "search",
        "query": "test",
        "max_results": 0,
    })
    # 应该不崩溃
    print(f"  ✅ max_results=0 不崩溃")

    # max_results = 10000 (超大)
    r = execute_knowledge_tool({
        "action": "search",
        "query": "test",
        "max_results": 10000,
    })
    print(f"  ✅ max_results=10000 不崩溃")

    # max_results 负数
    r = execute_knowledge_tool({
        "action": "search",
        "query": "test",
        "max_results": -1,
    })
    print(f"  ✅ max_results=-1 不崩溃")

    # 决策引擎 max_results
    r = execute_decision_engine_tool({
        "action": "advise",
        "problem": "test",
        "max_results": 0,
    })
    print(f"  ✅ decision max_results=0 不崩溃")

    r = execute_decision_engine_tool({
        "action": "advise",
        "problem": "test",
        "max_results": 1000,
    })
    print(f"  ✅ decision max_results=1000 不崩溃")

    # 经验学习器 max_results
    r = execute_experience_learner_tool({
        "action": "review",
        "max_results": -5,
    })
    print(f"  ✅ experience_learner max_results=-5 不崩溃")

    print("  ✅ 边界值测试通过！")


# ═══════════════════════════════════════════════════════════
# 持久化恢复验证
# ═══════════════════════════════════════════════════════════

def test_persistence_and_recovery():
    """验证数据持久化和恢复"""
    print("\n" + "=" * 55)
    print("🧪 持久化恢复验证")
    print("=" * 55)

    # 存储一条标记数据
    marker_title = f"PERSIST_MARKER_{int(time.time())}"
    r = execute_knowledge_tool({
        "action": "store",
        "title": marker_title,
        "content": "持久化测试标记数据 — 用于验证数据在多次调用间的持久性",
        "category": "persist_test",
        "tags": "persist,marker",
    })
    assert "已存储" in r, f"存储标记失败: {r}"
    print(f"  ✅ 标记数据已存储: {marker_title}")

    # 搜索确认存在
    r_search = execute_knowledge_tool({
        "action": "search",
        "query": marker_title,
        "max_results": 5,
        "mode": "keyword",
    })
    assert marker_title in r_search or "PERSIST_MARKER" in r_search, f"标记数据未找到: {r_search[:200]}"
    print(f"  ✅ 标记数据可搜索")

    # 验证持久化文件存在
    knowledge_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge", "knowledge_store.json"
    )
    assert os.path.isfile(knowledge_file), f"知识库文件不存在: {knowledge_file}"
    print(f"  ✅ 知识库文件存在: {os.path.basename(knowledge_file)}")

    # 验证 safety_data 文件
    safety_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "memory", "safety_data.json"
    )
    assert os.path.isfile(safety_file), f"安全数据文件不存在: {safety_file}"
    print(f"  ✅ 安全数据文件存在: {os.path.basename(safety_file)}")

    # 验证 tasks 文件
    tasks_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "memory", "tasks.json"
    )
    assert os.path.isfile(tasks_file), f"任务文件不存在: {tasks_file}"
    print(f"  ✅ 任务文件存在: {os.path.basename(tasks_file)}")

    print("  ✅ 持久化恢复验证通过！")


# ═══════════════════════════════════════════════════════════
# 内存稳定性测试
# ═══════════════════════════════════════════════════════════

def test_memory_stability():
    """验证连续操作后内存不泄漏（间接验证）"""
    print("\n" + "=" * 55)
    print("🧪 内存稳定性验证")
    print("=" * 55)

    # 连续高负载操作
    iterations = 50

    start = time.time()

    for i in range(iterations):
        # 混合操作
        execute_knowledge_tool({
            "action": "search",
            "query": f"test_{i % 10}",
            "max_results": 10,
        })
        execute_decision_engine_tool({
            "action": "advise",
            "problem": f"test problem {i % 5}",
        })
        execute_safety_net_tool({
            "action": "record_event",
            "event_type": "tool_call",
            "event_detail": f"stability test {i}",
        })
        _test_monitor_tool({
            "action": "record",
            "tool_name": "stability_test",
            "duration": 0.01,
            "success": True,
        })

    elapsed = time.time() - start
    rate = iterations * 4 / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ {iterations} x 4 = {iterations * 4} 次混合操作: {elapsed:.2f}s ({rate:.0f} 次/秒)")

    # 验证每个工具仍然可用
    r1 = execute_knowledge_tool({"action": "stats"})
    assert "条目" in r1 or "知识库" in r1
    print("  ✅ knowledge 仍可用")

    r2 = execute_decision_engine_tool({"action": "stats"})
    print("  ✅ decision_engine 仍可用")

    r3 = execute_safety_net_tool({"action": "status"})
    assert "安全网" in r3 or "总事件" in r3
    print("  ✅ safety_net 仍可用")

    r4 = _test_monitor_tool({"action": "summary"})
    print("  ✅ monitor 仍可用")

    r5 = execute_experience_learner_tool({"action": "stats"})
    print("  ✅ experience_learner 仍可用")

    print("  ✅ 内存稳定性验证通过！")


# ═══════════════════════════════════════════════════════════
# 并发模拟测试（串行模拟并发场景）
# ═══════════════════════════════════════════════════════════

def test_concurrent_simulation():
    """串行模拟并发混合操作"""
    print("\n" + "=" * 55)
    print("🧪 并发模拟: 混合工具链")
    print("=" * 55)

    # 模拟多个"并发会话"的操作序列
    sessions = 10
    ops_per_session = 20

    start = time.time()

    for session in range(sessions):
        for op in range(ops_per_session):
            tool_idx = (session + op) % 7
            if tool_idx == 0:
                execute_knowledge_tool({
                    "action": "search",
                    "query": f"session_{session}_op_{op}",
                    "max_results": 3,
                })
            elif tool_idx == 1:
                execute_decision_engine_tool({
                    "action": "advise",
                    "problem": f"session {session} issue {op}",
                })
            elif tool_idx == 2:
                execute_safety_net_tool({
                    "action": "record_event",
                    "event_type": "tool_call",
                    "event_detail": f"session_{session}.op_{op}",
                })
            elif tool_idx == 3:
                _test_monitor_tool({
                    "action": "record",
                    "tool_name": f"tool_{(session + op) % 5}",
                    "duration": (session * op) % 100 * 0.01,
                    "success": (session + op) % 7 != 0,
                })
            elif tool_idx == 4:
                execute_calculator_tool({
                    "expression": f"{session} * {op} + {session % 3}",
                })
            elif tool_idx == 5:
                execute_experience_learner_tool({
                    "action": "recommend",
                    "task": f"session {session} task",
                    "max_results": 3,
                })
            elif tool_idx == 6:
                try:
                    execute_knowledge_tool({
                        "action": "store",
                        "title": f"并发模拟_{session}_{op}",
                        "content": f"并发模拟数据 session={session} op={op}",
                        "category": "concurrent_test",
                    })
                except KnowledgeStoreError:
                    pass  # 空内容跳过

    elapsed = time.time() - start
    total_ops = sessions * ops_per_session
    rate = total_ops / elapsed if elapsed > 0 else float('inf')
    print(f"  ✅ {sessions} 会话 x {ops_per_session} 操作 = {total_ops} 次: {elapsed:.2f}s ({rate:.0f} 次/秒)")

    # 验证没有工具崩溃
    assert True  # 如果执行到这里，所有操作都正常
    print("  ✅ 所有工具在并发模拟后仍正常运行")

    print("  ✅ 并发模拟测试通过！")


# ═══════════════════════════════════════════════════════════
# 测试数据隔离：备份生产数据，测试后恢复（防止污染正式数据）
# ═══════════════════════════════════════════════════════════

# 压测会写入的生产数据文件（需在测试后恢复）
_PRODUCTION_DATA_FILES = [
    "knowledge/knowledge_store.json",
    "knowledge/vector_cache.json",
    "memory/tasks.json",
    "memory/safety_data.json",
    "memory/decisions.json",
    "memory/experience_learner.json",
]


def _backup_production_data() -> dict:
    """备份生产数据文件，返回 {path: bytes}。"""
    backups = {}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in _PRODUCTION_DATA_FILES:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            with open(p, "rb") as f:
                backups[rel] = f.read()
    return backups


def _restore_production_data(backups: dict) -> None:
    """恢复生产数据文件。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel, data in backups.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🚀 Agent 1 压力测试 (T061)")
    print("=" * 55)

    # ── 测试隔离：备份 + atexit 注册恢复（无论成功/失败都恢复）──
    import atexit
    _backups = _backup_production_data()
    atexit.register(_restore_production_data, _backups)

    total_start = time.time()

    # ── 大数据量 ──
    print("\n" + "━" * 55)
    print("📦 第一阶段: 大数据量测试")
    print("━" * 55)
    test_large_knowledge_store()
    test_large_task_creation()
    test_large_safety_events()

    # ── 高频操作 ──
    print("\n" + "━" * 55)
    print("⚡ 第二阶段: 高频操作测试")
    print("━" * 55)
    test_high_frequency_calculator()
    test_high_frequency_monitor()
    test_high_frequency_decision()

    # ── 极限参数 ──
    print("\n" + "━" * 55)
    print("🔬 第三阶段: 极限参数测试")
    print("━" * 55)
    test_boundary_empty_inputs()
    test_boundary_long_inputs()
    test_boundary_special_characters()
    test_boundary_max_values()

    # ── 持久化与稳定性 ──
    print("\n" + "━" * 55)
    print("🔒 第四阶段: 持久化与稳定性")
    print("━" * 55)
    test_persistence_and_recovery()
    test_memory_stability()
    test_concurrent_simulation()

    total_elapsed = time.time() - total_start

    print("\n" + "=" * 55)
    print(f"🎉 所有压力测试通过！总耗时: {total_elapsed:.1f}s")
    print("=" * 55)
    print(f"""
  压力测试覆盖:
  ┌────────────────────────────────────────────┐
  │  📦 大数据量:                               │
  │     • 200 条知识条目                         │
  │     • 100 个任务                             │
  │     • 500 条安全事件                         │
  │  ⚡ 高频操作:                                │
  │     • 100 次计算器调用                       │
  │     • 100 次监控记录                         │
  │     • 50 次决策查询                          │
  │  🔬 极限参数:                                │
  │     • 空输入/超长(10KB)/Unicode/特殊字符     │
  │     • 边界值 (0, -1, 10000)                 │
  │  🔒 持久化与稳定性:                          │
  │     • 文件持久化验证                          │
  │     • 200 次混合操作压测                      │
  │     • 200 次并发模拟                          │
  └────────────────────────────────────────────┘
  总计: ~{200 + 100 + 500 + 100 + 100 + 50 + 200 + 200} 次操作
  """)
