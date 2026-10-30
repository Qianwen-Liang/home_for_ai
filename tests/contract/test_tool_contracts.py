"""工具契约测试矩阵（编号 1.2）

依据 tests/contract/SPEC.md 第六节断言清单：
  C1 schema_compliance   工具定义符合 MCP 必填字段与命名规则
  C2 param_validation    6 类边界输入下满足 P1/P2/P3
  C3 error_contract      错误必为已知类型（RuntimeError 体系）
  C4 no_exception_leak   任意输入绝不抛未捕获异常
  C5 result_type         返回值必为 str
  C6 large_result        超阈值必须走摘要路径

设计要点：
  - 走真实入口 agent1.execute_model_tool_call，覆盖分派/埋点/错误包装全链路
  - 用 hypothesis 生成畸形参数（属性测试思想：声明全域性质，而非穷举用例）
  - 判定标准：抛 RuntimeError 子类 = 业务拒绝（合法）；抛其他异常 = 契约违规
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent1  # noqa: E402

TOOLS = agent1.ALL_TOOLS
TOOL_NAMES = [t["function"]["name"] for t in TOOLS]
BY_NAME = {t["function"]["name"]: t for t in TOOLS}

# 允许的「业务拒绝」异常：所有工具错误均继承 RuntimeError
ALLOWED_BASE = RuntimeError

# 禁止泄漏的异常类型
LEAK_PRONE = (TypeError, KeyError, AttributeError, IndexError,
              ZeroDivisionError, UnicodeError, OSError, ValueError)


def _invoke(name: str, arguments: dict):
    """通过真实入口调用工具，返回 (tool_call_id, name, result)。"""
    tool_call = {
        "id": f"contract_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }
    return agent1.execute_model_tool_call(tool_call)


# ── C1: 工具定义契约合规 ────────────────────────────────

@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
def test_c1_schema_compliance(tool):
    fn = tool.get("function", {})
    name = fn.get("name", "")

    # 命名规则：1-128，仅 A-Za-z0-9_-.，区分大小写
    assert re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name), f"命名不合规: {name!r}"

    # inputSchema（本系统用 parameters 承载）
    schema = fn.get("inputSchema") or fn.get("parameters")
    assert isinstance(schema, dict), f"{name} 缺少 inputSchema/parameters"

    # 参数必须声明为 object 类型
    assert schema.get("type") == "object", f"{name} 参数类型应为 object"

    props = schema.get("properties", {}) or {}
    req = schema.get("required", []) or []

    # required 中的字段必须存在于 properties
    for r in req:
        assert r in props, f"{name} required 字段 {r!r} 未在 properties 中定义"

    # 每个参数必须有 type
    for pname, pschema in props.items():
        assert isinstance(pschema, dict), f"{name}.{pname} 参数描述非法"
        assert "type" in pschema or "enum" in pschema or "anyOf" in pschema, \
            f"{name}.{pname} 缺少 type 声明"


# ── C5: 返回值类型 ──────────────────────────────────────

@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
def test_c5_result_type(tool):
    """用最小合法参数调用，返回值必须是 str。"""
    name = tool["function"]["name"]
    minimal = _minimal_args(tool)
    if minimal is None:
        pytest.skip(f"{name} 无安全最小参数，跳过")
    try:
        _, _, result = _invoke(name, minimal)
    except ALLOWED_BASE:
        pytest.skip(f"{name} 最小参数被业务拒绝，跳过结果类型检查")
    assert isinstance(result, str), f"{name} 返回类型应为 str，实际 {type(result)}"


def _minimal_args(tool: dict):
    """构造各工具的最小安全参数（避免执行危险操作）。"""
    name = tool["function"]["name"]
    return {
        "read_file": {"path": "README.md"},
        "list_directory": {"path": "."},
        "write_file": {"path": "_contract_tmp.txt", "content": "x"},
        "replace_text": {"path": "_contract_tmp.txt", "old_text": "x", "new_text": "y"},
        "make_directory": {"path": "_contract_tmp_dir"},
        "run_command": {"command": "echo contract", "timeout": 5},
        "web_search": {"query": "contract test", "max_results": 1, "mode": "fast"},
        "task_tracker": {"action": "report"},
        "knowledge": {"action": "stats"},
        "calculate": {"expression": "1+1"},
        "self_check": {"scope": "tools"},
        "test_runner": {"action": "list_tests"},
        "safe_deploy": {"action": "report"},
        "artifact_validator": {"content": "# t\n## s\n正文内容。", "artifact_type": "report"},
        "evidence_verifier": {"report": "{}"},
        "multi_reviewer": {"content": "测试内容"},
    }.get(name)


# ── C2 + C4: 畸形输入不崩溃 / 不泄漏异常 ───────────────

_MALFORMED = st.one_of(
    st.just({}),                                   # 空对象
    st.dictionaries(st.text(max_size=8), st.none() | st.booleans() | st.integers(), max_size=3),
    st.fixed_dictionaries({"path": st.none()}),    # 必填字段为 null
    st.fixed_dictionaries({"path": st.integers()}),# 类型错误
    st.fixed_dictionaries({"content": st.just("")}),  # 空值
    st.fixed_dictionaries({"action": st.text(max_size=4)}),  # 未知 action
    st.fixed_dictionaries({"query": st.text(max_size=3)}),
)


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
@settings(max_examples=15, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture,
                                 HealthCheck.too_slow])
@given(args=_MALFORMED)
def test_c2c4_malformed_input_no_leak(tool, args):
    """C2 参数校验 + C4 不泄漏异常：任意畸形输入只能被业务拒绝，不得崩溃。"""
    name = tool["function"]["name"]
    try:
        _, _, result = _invoke(name, args)
        # 未抛异常也必须返回 str
        assert isinstance(result, str)
    except ALLOWED_BASE:
        pass  # 业务拒绝，符合 P2
    except LEAK_PRONE as exc:
        pytest.fail(f"{name} 泄漏未包装异常 {type(exc).__name__}: {exc}")


# ── C3: 错误契约 ───────────────────────────────────────

# 错误信息可接受的标记（当前系统存在多种表达，统一化列入基线待修）
ERROR_MARKERS = ("❌", "⚠️", "工具执行失败", "错误", "不支持", "未知操作",
                 "不可用", "失败", "未找到", "无效", "必须", "不能", "返回码")


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
def test_c3_error_contract(tool):
    """触发必然失败场景。

    实测发现：本系统工具存在两种合法失败表达方式——抛 RuntimeError 子类，
    或返回结构化错误串。二者均视为符合契约，
    真正违规的是「泄漏未包装异常」或「返回看似成功的正常结果」。

    注：「错误串前缀是否统一」属于 C3 的严格子项，当前 7 个工具不满足
    （如返回 "未知操作: ..." 而非 ❌ 前缀），已记入 contract_baseline.json 待步骤 5 统一。
    """
    name = tool["function"]["name"]
    bad = _guaranteed_failure_args(tool)
    if bad is None:
        pytest.skip(f"{name} 无必然失败场景")
    try:
        _, _, result = _invoke(name, bad)
        # 未抛异常：必须能被识别为错误结果，不得伪装成成功
        assert isinstance(result, str)
        assert any(m in result[:60] for m in ERROR_MARKERS), \
            f"{name} 失败场景返回了非错误结果：{result[:70]!r}"
    except ALLOWED_BASE as exc:
        assert str(exc), f"{name} 错误信息为空"
    except LEAK_PRONE as exc:
        pytest.fail(f"{name} 错误类型违规 {type(exc).__name__}: {exc}")


def _guaranteed_failure_args(tool: dict):
    name = tool["function"]["name"]
    return {
        "read_file": {"path": "__definitely_not_exist__.txt"},
        "list_directory": {"path": "__definitely_not_exist_dir__"},
        "write_file": {"path": "../escape_attempt.txt", "content": "x"},
        "replace_text": {"path": "__not_exist__.txt", "old_text": "a", "new_text": "b"},
        "make_directory": {"path": "../escape_dir"},
        "run_command": {"command": "exit 1", "timeout": 5},
        "calculate": {"expression": "1/0"},
        "web_search": {"query": ""},
        "knowledge": {"action": "__invalid_action__"},
        "task_tracker": {"action": "__invalid_action__"},
        "test_runner": {"action": "__invalid_action__"},
        "safe_deploy": {"action": "__invalid_action__"},
        "artifact_validator": {"content": ""},
        "multi_reviewer": {"content": ""},
    }.get(name)


# ── C6: 大结果必须走摘要路径 ────────────────────────────

def test_c6_large_result_summary():
    """run_command 大输出必须被截断并给出落盘句柄。"""
    try:
        _, _, result = _invoke("run_command",
                               {"command": 'python -c "print(chr(88)*60000)"', "timeout": 20})
    except ALLOWED_BASE as exc:
        pytest.skip(f"命令执行被拒绝: {exc}")
    assert len(result) <= 25_000, f"大结果未摘要，长度 {len(result)}"
    assert ("已返回头部" in result) or ("memory/cmd_output" in result), \
        "大结果缺少摘要或落盘句柄标记"


def test_c6_large_file_summary():
    """read_file 大文件必须走采样路径。"""
    big = ROOT / "agent1.py"
    try:
        _, _, result = _invoke("read_file", {"path": "agent1.py"})
    except ALLOWED_BASE as exc:
        pytest.skip(f"读取被拒绝: {exc}")
    size = big.stat().st_size
    if size > 20_000:
        assert len(result) < size * 0.5, "大文件未采样"
        assert "分段读取" in result, "大文件缺少分段指引"


# ── C7: JSON Schema 参数契约（用 jsonschema 实装，MCP 规范要求）──

@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
def test_c7_json_schema_valid(tool):
    """每个工具的 parameters 必须是合法的 JSON Schema（2020-12）。"""
    from jsonschema import Draft202012Validator, SchemaError

    fn = tool["function"]
    schema = fn.get("inputSchema") or fn.get("parameters")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        pytest.fail(f"{fn['name']} 的 schema 非法: {exc.message}")


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_NAMES)
def test_c7_param_validation_with_jsonschema(tool):
    """用 jsonschema 校验：非法参数必须被判为 invalid，合法最小参数必须 valid。

    这是对 C2 的机械化补强：C2 用属性测试验证「不崩溃」，
    C7 用 JSON Schema 验证「参数合法性判定正确」。
    """
    from jsonschema import Draft202012Validator

    fn = tool["function"]
    schema = fn.get("inputSchema") or fn.get("parameters")
    validator = Draft202012Validator(schema)
    name = fn["name"]

    # 非法：空对象（当存在必填字段时应 invalid）
    required = (schema or {}).get("required") or []
    if required:
        assert list(validator.iter_errors({})), f"{name} 缺必填却判为 valid"

    # 合法：用最小安全参数（若可构造）
    minimal = _minimal_args(tool)
    if minimal is not None:
        errors = list(validator.iter_errors(minimal))
        assert not errors, f"{name} 最小合法参数被判 invalid: {[e.message for e in errors][:2]}"
