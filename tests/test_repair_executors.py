"""
repair_executors — 自主修复闭环单元测试
=========================================
覆盖 RuleBasedFixer 规则引擎 + 5 个阶段执行器 + 流水线集成。
"""
import sys
import os
import json

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.repair_executors import (
    RuleBasedFixer,
    repair_diagnose,
    repair_plan,
    repair_backup,
    repair_fix,
    repair_verify,
    create_repair_offline_task,
    run_repair_pipeline,
)
from tools.auto_repair import (
    ParsedError,
    AutoRepairError,
    TracebackParser,
    _orchestrator,
)

SANDBOX_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 辅助 ──────────────────────────────────────────────────

_fixer = RuleBasedFixer()
_parser = TracebackParser()

# 伪造一个存在于项目中的模块名用于 import 修复测试
def _find_existing_module() -> str:
    """查找一个真实存在的模块名。"""
    for f in ("tools", "evolver", "memory", "tests"):
        p = os.path.join(SANDBOX_DIR, f)
        if os.path.isdir(p):
            return f
    return "tools"


_EXISTING_MODULE = _find_existing_module()


# ═══════════════════════════════════════════════════════════
# RuleBasedFixer 测试
# ═══════════════════════════════════════════════════════════


def test_can_auto_fix_import():
    """import 分类可自动修复"""
    parsed = ParsedError(
        error_type="ImportError",
        error_message="No module named 'nonexistent'",
        file_path="agent1.py",
        line_number=50,
        category="import",
    )
    assert _fixer.can_auto_fix(parsed) is True
    print("✅ 测试1 can_auto_fix(import): 通过")


def test_can_auto_fix_syntax():
    """syntax 分类可自动修复"""
    parsed = ParsedError(
        error_type="SyntaxError",
        error_message="invalid syntax",
        file_path="tools/foo.py",
        line_number=10,
        category="syntax",
    )
    assert _fixer.can_auto_fix(parsed) is True
    print("✅ 测试2 can_auto_fix(syntax): 通过")


def test_can_auto_fix_runtime():
    """runtime 分类不可自动修复"""
    parsed = ParsedError(
        error_type="RuntimeError",
        error_message="something went wrong",
        category="runtime",
    )
    assert _fixer.can_auto_fix(parsed) is False
    print("✅ 测试3 can_auto_fix(runtime): 通过")


def test_can_auto_fix_unknown():
    """unknown 分类不可自动修复"""
    parsed = ParsedError(
        error_type="CustomError",
        error_message="whatever",
        category="unknown",
    )
    assert _fixer.can_auto_fix(parsed) is False
    print("✅ 测试4 can_auto_fix(unknown): 通过")


# ── ImportError 修复 ──────────────────────────────────────


def test_fix_import_error_existing_module():
    """ImportError: 项目内存在的模块 → 生成修复补丁"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="ImportError",
            error_message=f"No module named '{_EXISTING_MODULE}'",
            file_path="agent1.py",
            line_number=1,
            code_context=f"import {_EXISTING_MODULE}",
            category="import",
        )
    )
    # 应该找到模块并生成补丁 或 标记为需要人工审核（因为可能已正确导入）
    assert "auto_fixable" in result
    # 无论是否可自动修复，结构应完整
    assert "strategy" in result
    assert "patches" in result
    assert "warnings" in result
    print(f"✅ 测试5 fix_import_error(existing): {result['strategy'][:50]}...")


def test_fix_import_error_nonexistent_module():
    """ImportError: 不存在的模块 → 提示 pip install"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="ModuleNotFoundError",
            error_message="No module named 'xkcd_completely_fake_module_xyz'",
            file_path="agent1.py",
            line_number=50,
            code_context="import xkcd_completely_fake_module_xyz",
            category="import",
        )
    )
    assert result["auto_fixable"] is False
    assert result["requires_human_review"] is True
    assert any("pip" in w.lower() or "未安装" in w for w in result["warnings"])
    print("✅ 测试6 fix_import_error(nonexistent): 通过")


def test_fix_import_error_no_file_path():
    """ImportError: 无文件路径 → 无法修复"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="ImportError",
            error_message="No module named 'something'",
            file_path="",
            line_number=0,
            category="import",
        )
    )
    assert result["auto_fixable"] is False
    assert result["requires_human_review"] is True
    print("✅ 测试7 fix_import_error(no_path): 通过")


def test_fix_import_error_pip_map():
    """ImportError: 常见 pip 包映射"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="ModuleNotFoundError",
            error_message="No module named 'yaml'",
            file_path="agent1.py",
            line_number=10,
            code_context="import yaml",
            category="import",
        )
    )
    # yaml → PyYAML 映射
    assert any("PyYAML" in w for w in result["warnings"])
    print("✅ 测试8 fix_import_error(pip_map): 通过")


# ── SyntaxError 修复 ──────────────────────────────────────


def test_fix_syntax_unmatched_parens():
    """SyntaxError: 括号不匹配 → 补全"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="SyntaxError",
            error_message="unmatched ')'",
            file_path="agent1.py",
            line_number=1,
            code_context="print(hello",
            category="syntax",
        )
    )
    assert result["auto_fixable"] is True
    assert len(result["patches"]) > 0
    patch = result["patches"][0]
    assert patch["type"] == "replace_line"
    # 补全了右括号
    assert ")" in patch["new_text"]
    print(f"✅ 测试9 fix_syntax(unmatched_parens): {patch['new_text'][:40]}...")


def test_fix_syntax_missing_colon():
    """SyntaxError: 缺少冒号 → 补全"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="SyntaxError",
            error_message="expected ':'",
            file_path="agent1.py",
            line_number=1,
            code_context="    if True",
            category="syntax",
        )
    )
    assert result["auto_fixable"] is True
    if result["patches"]:
        patch = result["patches"][0]
        assert patch["new_text"].rstrip().endswith(":")
    print(f"✅ 测试10 fix_syntax(missing_colon): {result['strategy'][:50]}...")


def test_fix_syntax_no_file():
    """SyntaxError: 文件不存在 → 无法修复"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="SyntaxError",
            error_message="invalid syntax",
            file_path="nonexistent/path.py",
            line_number=1,
            category="syntax",
        )
    )
    assert result["auto_fixable"] is False
    assert result["requires_human_review"] is True
    print("✅ 测试11 fix_syntax(no_file): 通过")


def test_fix_syntax_line_out_of_range():
    """SyntaxError: 行号超出范围"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="SyntaxError",
            error_message="invalid syntax",
            file_path="agent1.py",
            line_number=99999,
            category="syntax",
        )
    )
    assert result["auto_fixable"] is False
    print("✅ 测试12 fix_syntax(line_out_of_range): 通过")


def test_fix_syntax_unterminated_string():
    """SyntaxError: 字符串未闭合"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="SyntaxError",
            error_message="EOL while scanning string literal",
            file_path="agent1.py",
            line_number=1,
            code_context='text = "hello world',
            category="syntax",
        )
    )
    # 应该尝试修复未闭合引号
    assert "auto_fixable" in result
    print(f"✅ 测试13 fix_syntax(unterminated_string): {result['strategy'][:50]}...")


# ── AttributeError 修复 ───────────────────────────────────


def test_fix_attribute_error():
    """AttributeError: 基于 Levenshtein 提示"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="AttributeError",
            error_message="type object 'str' has no attribute 'lenght'",
            file_path="agent1.py",
            line_number=1,
            code_context="len = 'hello'.lenght",
            category="attribute",
        )
    )
    assert "auto_fixable" in result
    # 应该给出建议
    assert len(result["warnings"]) > 0
    print(f"✅ 测试14 fix_attribute_error: {result['strategy'][:50]}...")


def test_fix_attribute_error_no_match():
    """AttributeError: 无法提取属性名"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="AttributeError",
            error_message="some weird error without attribute name",
            category="attribute",
        )
    )
    assert result["auto_fixable"] is False
    print("✅ 测试15 fix_attribute_error(no_match): 通过")


# ── NameError 修复 ────────────────────────────────────────


def test_fix_name_error_builtin_typo():
    """NameError: 内置函数拼写错误 → 建议修正"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="NameError",
            error_message="name 'lenght' is not defined",
            file_path="agent1.py",
            line_number=10,
            code_context="lenght = len(x)",
            category="name",
        )
    )
    assert "auto_fixable" in result
    # 'lenght' 接近 'len'
    if result["auto_fixable"]:
        assert any("len" in w for w in result["warnings"])
    print(f"✅ 测试16 fix_name_error(builtin_typo): {result['strategy'][:50]}...")


def test_fix_name_error_no_match():
    """NameError: 无法提取变量名"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="NameError",
            error_message="something else entirely",
            category="name",
        )
    )
    assert result["auto_fixable"] is False
    print("✅ 测试17 fix_name_error(no_match): 通过")


# ── generate_fix 非自动分类 ──────────────────────────────


def test_generate_fix_runtime():
    """非可自动修复分类 → 标记需人工审核"""
    result = _fixer.generate_fix(
        ParsedError(
            error_type="RuntimeError",
            error_message="maximum recursion depth exceeded",
            category="runtime",
        )
    )
    assert result["auto_fixable"] is False
    assert result["requires_human_review"] is True
    assert len(result["patches"]) == 0
    print("✅ 测试18 generate_fix(runtime): 通过")


# ═══════════════════════════════════════════════════════════
# 阶段执行器测试
# ═══════════════════════════════════════════════════════════


def test_repair_diagnose_valid():
    """repair_diagnose: 有效的 traceback"""
    traceback = """Traceback (most recent call last):
  File "agent1.py", line 42, in main
    result = broken_function()
  File "agent1.py", line 15, in broken_function
    import nonexistent_module_xyz
ModuleNotFoundError: No module named 'nonexistent_module_xyz'"""

    result = repair_diagnose("T-TEST-01", "诊断", {
        "traceback": traceback,
        "error_source": "test",
    })
    assert result["status"] == "done"
    assert "diag_data" in result
    assert result["diag_data"]["error_type"] == "ModuleNotFoundError"
    assert result["diag_data"]["category"] == "import"
    print(f"✅ 测试19 repair_diagnose(valid): {result['diag_data']['error_type']} ({result['diag_data']['category']})")


def test_repair_diagnose_empty():
    """repair_diagnose: 空 traceback → 失败"""
    result = repair_diagnose("T-TEST-02", "诊断", {
        "traceback": "",
    })
    assert result["status"] == "failed"
    assert "缺少" in result["error"]
    print("✅ 测试20 repair_diagnose(empty): 通过")


def test_repair_diagnose_no_traceback_key():
    """repair_diagnose: 缺少 traceback 键"""
    result = repair_diagnose("T-TEST-03", "诊断", {})
    assert result["status"] == "failed"
    print("✅ 测试21 repair_diagnose(no_traceback): 通过")


def test_repair_plan_no_data():
    """repair_plan: 无诊断数据 → 失败"""
    # 使用一个全新的 task_id 确保无检查点
    import time
    result = repair_plan(f"T-EMPTY-{int(time.time())}", "计划", {})
    assert result["status"] == "failed"
    print("✅ 测试22 repair_plan(no_data): 通过")


def test_repair_plan_with_diagnosis_json():
    """repair_plan: 从 params 直接获取诊断 JSON"""
    diag = json.dumps({
        "error_type": "SyntaxError",
        "error_message": "invalid syntax",
        "file_path": "agent1.py",
        "line_number": 1,
        "category": "syntax",
        "severity": "high",
    }, ensure_ascii=False)

    result = repair_plan("T-DIAG-JSON", "计划", {
        "diagnosis_json": diag,
    })
    assert result["status"] == "done"
    assert "auto_fixable" in result
    assert "fix_strategy" in result
    print(f"✅ 测试23 repair_plan(with_json): {result['fix_strategy'][:50]}...")


def test_repair_backup():
    """repair_backup: 创建备份"""
    result = repair_backup("T-BACKUP-01", "备份", {})
    assert result["status"] == "done"
    assert "checkpoint_id" in result
    print(f"✅ 测试24 repair_backup: 检查点 {result.get('checkpoint_id', '?')}")


def test_repair_fix_no_patches():
    """repair_fix: 无补丁 → 跳过"""
    result = repair_fix("T-NO-PATCHES", "修复", {"auto_apply": True})
    assert result["status"] == "done"
    assert result["applied"] is False
    assert "没有可应用的补丁" in result.get("reason", "")
    print("✅ 测试25 repair_fix(no_patches): 通过")


def test_repair_fix_auto_apply_false():
    """repair_fix: auto_apply=False → 仅生成不应用"""
    result = repair_fix("T-NO-APPLY", "修复", {"auto_apply": False})
    assert result["status"] == "done"
    assert result["applied"] is False
    print("✅ 测试26 repair_fix(auto_apply=False): 通过")


def test_repair_verify_no_files():
    """repair_verify: 无修复文件 → 仍运行全量测试"""
    result = repair_verify("T-VERIFY-01", "验证", {})
    assert result["status"] == "done"
    assert "verification_passed" in result
    assert "output" in result
    print(f"✅ 测试27 repair_verify: passed={result['verification_passed']}")


# ═══════════════════════════════════════════════════════════
# 便捷 API 测试
# ═══════════════════════════════════════════════════════════


def test_create_repair_offline_task():
    """create_repair_offline_task: 生成离线任务参数"""
    traceback = "Traceback (most recent call last):\n  ...\nValueError: test"
    result = create_repair_offline_task(
        traceback_text=traceback,
        auto_apply=False,
        error_source="test",
    )
    assert "title" in result
    assert "phases" in result
    assert result["phases"] == ["诊断", "计划", "备份", "修复", "验证"]
    assert result["params"]["traceback"] == traceback
    assert result["params"]["auto_apply"] is False
    assert result["params"]["error_source"] == "test"
    print("✅ 测试28 create_repair_offline_task: 通过")


def test_create_repair_offline_task_with_webhook():
    """create_repair_offline_task: 含 webhook"""
    result = create_repair_offline_task(
        traceback_text="error",
        auto_apply=True,
        webhook_url="https://hooks.example.com/done",
    )
    assert result["webhook_url"] == "https://hooks.example.com/done"
    assert result["params"]["auto_apply"] is True
    print("✅ 测试29 create_repair_offline_task(webhook): 通过")


def test_run_repair_pipeline_empty():
    """run_repair_pipeline: 空 traceback → 诊断失败"""
    result = run_repair_pipeline("", auto_apply=False)
    assert "诊断" in result
    # 第一阶段就失败了
    print(f"✅ 测试30 run_repair_pipeline(empty): {result[:80]}...")


def test_run_repair_pipeline_syntax_error():
    """run_repair_pipeline: 真实 traceback → 完整流水线"""
    traceback = """Traceback (most recent call last):
  File "agent1.py", line 10, in <module>
    if True
            ^
SyntaxError: expected ':'"""

    result = run_repair_pipeline(traceback, auto_apply=False)
    assert "流水线报告" in result
    assert "诊断" in result
    assert "计划" in result
    print(f"✅ 测试31 run_repair_pipeline(syntax): 流水线完成")


# ═══════════════════════════════════════════════════════════
# 解析器健壮性测试
# ═══════════════════════════════════════════════════════════


def test_parse_minimal_traceback():
    """仅一行异常消息 → 解析成功"""
    parsed = _parser.parse("ValueError: something went wrong")
    assert parsed.error_type == "ValueError"
    assert parsed.error_message == "something went wrong"
    assert parsed.category == "value"
    print("✅ 测试32 parse(minimal): 通过")


def test_parse_indentation_error():
    """IndentationError 解析"""
    traceback = """  File "tools/foo.py", line 42
    print(x)
            ^
IndentationError: unexpected indent"""
    parsed = _parser.parse(traceback)
    assert parsed.error_type == "IndentationError"
    assert parsed.category == "syntax"
    assert parsed.line_number == 42
    print("✅ 测试33 parse(IndentationError): 通过")


def test_parse_nested_traceback():
    """嵌套 traceback（during handling）"""
    traceback = """Traceback (most recent call last):
  File "a.py", line 1, in f
    1/0
ZeroDivisionError: division by zero

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "b.py", line 2, in g
    raise ValueError("nested")
ValueError: nested"""
    parsed = _parser.parse(traceback)
    # 应解析最内层异常
    assert parsed.error_type == "ValueError"
    assert parsed.error_message == "nested"
    print("✅ 测试34 parse(nested): 通过")


def test_parse_empty_traceback():
    """空 traceback → 异常"""
    try:
        _parser.parse("")
        assert False, "应抛出异常"
    except AutoRepairError:
        pass
    print("✅ 测试35 parse(empty): 通过")


# ═══════════════════════════════════════════════════════════
# 置信度评分器测试
# ═══════════════════════════════════════════════════════════


def test_confidence_green():
    """高置信度 → GREEN"""
    score, level = _orchestrator._scorer.score(
        error_category="syntax",
        test_coverage_ratio=0.9,
        fix_line_count=1,
        verification_passed=True,
    )
    assert level == "green"
    assert score >= 0.7
    print(f"✅ 测试36 confidence(green): score={score:.2f}, level={level}")


def test_confidence_red():
    """低置信度 → RED"""
    score, level = _orchestrator._scorer.score(
        error_category="network",
        test_coverage_ratio=0.0,
        fix_line_count=100,
        verification_passed=False,
    )
    assert level == "red"
    assert score < 0.3
    print(f"✅ 测试37 confidence(red): score={score:.2f}, level={level}")


def test_confidence_yellow():
    """中等置信度 → YELLOW"""
    score, level = _orchestrator._scorer.score(
        error_category="runtime",
        test_coverage_ratio=0.5,
        fix_line_count=5,
        verification_passed=False,
    )
    assert level == "yellow"
    assert 0.3 <= score < 0.7
    print(f"✅ 测试38 confidence(yellow): score={score:.2f}, level={level}")


# ═══════════════════════════════════════════════════════════
# _compute_import_path 测试
# ═══════════════════════════════════════════════════════════


def test_compute_import_path():
    """计算导入路径"""
    from pathlib import Path

    source_dir = Path(SANDBOX_DIR) / "tools"
    target = Path(SANDBOX_DIR) / "tools" / "auto_repair.py"
    result = _fixer._compute_import_path(source_dir, target)
    # 应该得到相对于 tools/ 的路径
    assert "auto_repair" in result
    print(f"✅ 测试39 _compute_import_path: {result}")


def test_compute_import_path_same_level():
    """计算同级路径"""
    from pathlib import Path

    source_dir = Path(SANDBOX_DIR)
    target = Path(SANDBOX_DIR) / "agent1.py"
    result = _fixer._compute_import_path(source_dir, target)
    assert "agent1" in result
    print(f"✅ 测试40 _compute_import_path(same_level): {result}")


# ═══════════════════════════════════════════════════════════
# _replace_import_target 测试
# ═══════════════════════════════════════════════════════════


def test_replace_import_target():
    """替换 import 语句中的模块名"""
    result = _fixer._replace_import_target(
        "import old_module",
        "old_module",
        "new.path.module",
    )
    assert result == "import new.path.module"
    print("✅ 测试41 _replace_import_target: 通过")


def test_replace_import_target_from():
    """替换 from...import 语句中的模块名"""
    result = _fixer._replace_import_target(
        "from old.module import func",
        "old.module",
        "new.module",
    )
    assert result == "from new.module import func"
    print("✅ 测试42 _replace_import_target(from): 通过")


# ═══════════════════════════════════════════════════════════
# 执行器异常处理测试
# ═══════════════════════════════════════════════════════════


def test_executor_catches_exceptions():
    """执行器不应让异常向上传播"""
    # repair_fix 在遇到各种边界情况时应返回 status=failed 而非抛异常
    result = repair_fix("T-BAD", "修复", {"auto_apply": True})
    # 即使没有诊断数据，也应该正常返回
    assert "status" in result
    print("✅ 测试43 executor异常安全: 通过")


# ═══════════════════════════════════════════════════════════
# 端到端: offline submit → execute 集成
# ═══════════════════════════════════════════════════════════


def test_offline_integration_submit():
    """通过 offline_runner 提交修复任务"""
    from tools.offline_runner import _manager as offline_mgr

    task = create_repair_offline_task(
        traceback_text="ValueError: test error",
        auto_apply=False,
    )

    result = offline_mgr.submit(
        title=task["title"],
        description=task["description"],
        phases=task["phases"],
        params=task["params"],
    )

    assert "已提交" in result
    # 提取 task_id
    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break
    assert task_id.startswith("OT-")

    # 验证任务已创建
    assert task_id in offline_mgr._tasks
    task_obj = offline_mgr._tasks[task_id]
    assert task_obj.phases == ["诊断", "计划", "备份", "修复", "验证"]

    print(f"✅ 测试44 offline集成提交: task_id={task_id}")


def test_offline_integration_execute():
    """通过 offline_runner 执行修复任务（使用已注册执行器）"""
    from tools.offline_runner import _manager as offline_mgr

    traceback = """Traceback (most recent call last):
  File "agent1.py", line 10, in <module>
    if True
            ^
SyntaxError: expected ':'"""

    task = create_repair_offline_task(
        traceback_text=traceback,
        auto_apply=False,
        error_source="integration_test",
    )

    result = offline_mgr.submit(
        title=task["title"],
        description=task["description"],
        phases=task["phases"],
        params=task["params"],
    )

    task_id = ""
    for line in result.split("\n"):
        if "任务ID:" in line:
            task_id = line.split("任务ID:")[1].strip()
            break

    # 执行（使用已注册的阶段执行器）
    from tools.executor_registry import get_registry
    executor = get_registry().get_executor_for_runner()

    exec_result = offline_mgr.execute(task_id, phase_executor=executor)
    assert "已完成" in exec_result or "完成" in exec_result

    task_obj = offline_mgr._tasks[task_id]
    assert task_obj.status == "done"
    assert task_obj.progress == 1.0

    # 生成报告
    report = offline_mgr.generate_report(task_id)
    assert "执行报告" in report

    print(f"✅ 测试45 offline集成执行: task_id={task_id}, status={task_obj.status}")


if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        # RuleBasedFixer
        ("can_auto_fix(import)", test_can_auto_fix_import),
        ("can_auto_fix(syntax)", test_can_auto_fix_syntax),
        ("can_auto_fix(runtime)", test_can_auto_fix_runtime),
        ("can_auto_fix(unknown)", test_can_auto_fix_unknown),
        ("fix_import_error(existing)", test_fix_import_error_existing_module),
        ("fix_import_error(nonexistent)", test_fix_import_error_nonexistent_module),
        ("fix_import_error(no_path)", test_fix_import_error_no_file_path),
        ("fix_import_error(pip_map)", test_fix_import_error_pip_map),
        ("fix_syntax(unmatched_parens)", test_fix_syntax_unmatched_parens),
        ("fix_syntax(missing_colon)", test_fix_syntax_missing_colon),
        ("fix_syntax(no_file)", test_fix_syntax_no_file),
        ("fix_syntax(line_range)", test_fix_syntax_line_out_of_range),
        ("fix_syntax(unterminated)", test_fix_syntax_unterminated_string),
        ("fix_attribute_error", test_fix_attribute_error),
        ("fix_attribute_error(no_match)", test_fix_attribute_error_no_match),
        ("fix_name_error(typo)", test_fix_name_error_builtin_typo),
        ("fix_name_error(no_match)", test_fix_name_error_no_match),
        ("generate_fix(runtime)", test_generate_fix_runtime),
        # 阶段执行器
        ("repair_diagnose(valid)", test_repair_diagnose_valid),
        ("repair_diagnose(empty)", test_repair_diagnose_empty),
        ("repair_diagnose(no_key)", test_repair_diagnose_no_traceback_key),
        ("repair_plan(no_data)", test_repair_plan_no_data),
        ("repair_plan(with_json)", test_repair_plan_with_diagnosis_json),
        ("repair_backup", test_repair_backup),
        ("repair_fix(no_patches)", test_repair_fix_no_patches),
        ("repair_fix(auto_apply=False)", test_repair_fix_auto_apply_false),
        ("repair_verify", test_repair_verify_no_files),
        # 便捷 API
        ("create_repair_offline_task", test_create_repair_offline_task),
        ("create_repair_offline_task(webhook)", test_create_repair_offline_task_with_webhook),
        ("run_repair_pipeline(empty)", test_run_repair_pipeline_empty),
        ("run_repair_pipeline(syntax)", test_run_repair_pipeline_syntax_error),
        # 解析器
        ("parse(minimal)", test_parse_minimal_traceback),
        ("parse(IndentationError)", test_parse_indentation_error),
        ("parse(nested)", test_parse_nested_traceback),
        ("parse(empty)", test_parse_empty_traceback),
        # 置信度
        ("confidence(green)", test_confidence_green),
        ("confidence(red)", test_confidence_red),
        ("confidence(yellow)", test_confidence_yellow),
        # 辅助方法
        ("_compute_import_path", test_compute_import_path),
        ("_compute_import_path(same)", test_compute_import_path_same_level),
        ("_replace_import_target", test_replace_import_target),
        ("_replace_import_target(from)", test_replace_import_target_from),
        # 异常安全
        ("executor_exception_safety", test_executor_catches_exceptions),
        # 端到端集成
        ("offline_integration_submit", test_offline_integration_submit),
        ("offline_integration_execute", test_offline_integration_execute),
    ]

    print("=" * 60)
    print("🧪 自主修复闭环 (repair_executors) 单元测试")
    print(f"   共 {len(tests)} 个测试")
    print("=" * 60)

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ 测试 [{name}] 失败: {e}")

    print()
    print("=" * 60)
    print(f"🎯 结果: ✅ {passed} 通过 | ❌ {failed} 失败 | 总计 {len(tests)}")
    if failed == 0:
        print("🎉 全部通过！")
    print("=" * 60)
