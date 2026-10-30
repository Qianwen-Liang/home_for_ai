"""
Calculator — 安全可靠的数学计算工具
===================================
提供基本的数学运算功能，使用安全求值方式，避免代码注入风险。
支持作为独立工具调用，也支持直接导入使用。
"""

from __future__ import annotations

import math
import operator
import re
from typing import Any, Callable

# ── 错误类型 ──────────────────────────────────────────────


class CalculationError(RuntimeError):
    """计算过程中出现的错误。"""


# ── 安全白名单 ────────────────────────────────────────────

# 允许的运算符映射
_OPERATORS: dict[str, Callable[..., Any]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}

# 允许的数学函数
_MATH_FUNCS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "degrees": math.degrees,
    "radians": math.radians,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
}

# 允许的常量
_MATH_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": float("inf"),
}

# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": (
            "执行安全的数学计算，支持四则运算、数学函数和常量。"
            "支持：+ - * / // % ** 和数学函数。"
            "示例：'2 + 3 * 4'、'sqrt(16)'、'sin(pi/2)'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式，如 '2 + 3 * 4'",
                },
                "precision": {
                    "type": "integer",
                    "description": "小数精度（四舍五入到几位小数），默认不限制",
                    "default": None,
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
}


# ── 安全求值 ──────────────────────────────────────────────

_TOKEN_PATTERN = re.compile(
    r"(\d+\.?\d*|[a-zA-Z_]\w*|"
    r"//|\*\*|"
    r"[\+\-\*\/\%\(\)])"
)


class Calculator:
    """安全数学计算器，不依赖 eval。"""

    def __init__(self) -> None:
        self._vars: dict[str, float] = dict(_MATH_CONSTS)

    def evaluate(self, expression: str) -> float:
        """安全地计算表达式，返回数值结果。"""

        expression = expression.strip()
        if not expression:
            raise CalculationError("表达式不能为空")

        # 安全检查：只允许白名单字符
        allowed = re.compile(r"^[0-9a-zA-Z_\.\+\-\*\/\%\(\)\s]+$")
        if not allowed.match(expression):
            raise CalculationError("表达式包含不允许的字符")

        tokens = self._tokenize(expression)
        if not tokens:
            raise CalculationError("无法解析表达式")

        result = self._parse_expression(tokens)
        if tokens:  # 还有剩余 token，说明语法有误
            raise CalculationError(f"表达式语法错误，无法解析剩余: {' '.join(tokens)}")
        return result

    def _tokenize(self, expression: str) -> list[str]:
        """将表达式拆分为 token 列表。"""
        tokens = _TOKEN_PATTERN.findall(expression)
        return tokens

    def _parse_expression(self, tokens: list[str]) -> float:
        """解析加减法表达式。"""
        value = self._parse_term(tokens)
        while tokens and tokens[0] in ("+", "-"):
            op = tokens.pop(0)
            right = self._parse_term(tokens)
            if op == "+":
                value = operator.add(value, right)
            else:
                value = operator.sub(value, right)
        return value

    def _parse_term(self, tokens: list[str]) -> float:
        """解析乘除法表达式。"""
        value = self._parse_power(tokens)
        while tokens and tokens[0] in ("*", "/", "%", "//"):
            op = tokens.pop(0)
            right = self._parse_power(tokens)
            if op == "*":
                value = operator.mul(value, right)
            elif op == "/":
                if right == 0:
                    raise CalculationError("除数不能为零")
                value = operator.truediv(value, right)
            elif op == "%":
                value = operator.mod(value, right)
            elif op == "//":
                if right == 0:
                    raise CalculationError("除数不能为零")
                value = operator.floordiv(value, right)
        return value

    def _parse_power(self, tokens: list[str]) -> float:
        """解析幂运算表达式。"""
        value = self._parse_factor(tokens)
        if tokens and tokens[0] == "**":
            tokens.pop(0)
            right = self._parse_factor(tokens)
            value = operator.pow(value, right)
        return value

    def _parse_factor(self, tokens: list[str]) -> float:
        """解析基本因子：数字、函数、常量或括号表达式。"""
        if not tokens:
            raise CalculationError("表达式意外结束")

        token = tokens.pop(0)

        # 括号表达式
        if token == "(":
            value = self._parse_expression(tokens)
            if not tokens or tokens.pop(0) != ")":
                raise CalculationError("缺少右括号")
            return value

        # 数字
        try:
            return float(token)
        except ValueError:
            pass

        # 函数调用
        if token in _MATH_FUNCS:
            if not tokens or tokens[0] != "(":
                raise CalculationError(f"函数 '{token}' 需要括号参数")
            tokens.pop(0)  # 移除 '('
            arg = self._parse_expression(tokens)
            if not tokens or tokens.pop(0) != ")":
                raise CalculationError(f"函数 '{token}' 缺少右括号")
            return _MATH_FUNCS[token](arg)

        # 常量
        if token in _MATH_CONSTS:
            return _MATH_CONSTS[token]

        # 一元负号
        if token == "-":
            return -self._parse_factor(tokens)

        # 一元正号
        if token == "+":
            return self._parse_factor(tokens)

        raise CalculationError(f"未知标识符: '{token}'")


# ── 全局实例 ──────────────────────────────────────────────

_calculator = Calculator()


def calculate(expression: str, precision: int | None = None) -> str:
    """计算数学表达式，返回格式化结果。"""

    result = _calculator.evaluate(expression)

    if precision is not None:
        result = round(result, precision)

    # 格式化输出
    if result == float("inf"):
        return "∞ (无穷大)"
    if result == float("-inf"):
        return "-∞ (负无穷大)"
    if result == int(result) and (precision is None or precision == 0):
        return str(int(result))

    return f"{result:.{precision or 10}f}".rstrip("0").rstrip(".")


def execute_calculator_tool(arguments: dict[str, Any]) -> str:
    expression = arguments.get("expression", "")
    precision = arguments.get("precision", None)
    try:
        return calculate(expression, precision)
    except CalculationError as exc:
        return f"❌ 计算错误: {exc}"
