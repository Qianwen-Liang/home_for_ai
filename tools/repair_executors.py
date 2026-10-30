"""
repair_executors — 自主修复闭环的阶段执行器注册 & 规则修复引擎 (v1.0)
====================================================================
桥接 auto_repair 模块与 offline_runner，注册 5 个阶段执行器，
使离线任务能够端到端驱动自主修复流水线。

核心组件：
  - RuleBasedFixer: 规则引擎，针对 19 种异常分类中的确定性场景自动生成修复补丁
  - 5 个 @register_executor 阶段: 诊断→计划→备份→修复→验证

使用方式（一条命令触发端到端闭环）：
  offline action=submit title="自动修复: ImportError" phases='["诊断","计划","备份","修复","验证"]' params='{"traceback":"...", "auto_apply":true}'
  offline action=execute task_id="OT-..."
"""

from __future__ import annotations

import ast
import difflib
import json
import re
from pathlib import Path
from typing import Any

from .executor_registry import register_executor
from .auto_repair import (
    _orchestrator,
    _parser,
    RepairOrchestrator,
    ParsedError,
    AutoRepairError,
)
from .checkpoint_manager import CheckpointManager

SANDBOX_DIR = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════
# RuleBasedFixer — 规则驱动的自动修复引擎
# ═══════════════════════════════════════════════════════════

class RuleBasedFixer:
    """
    基于规则的代码修复引擎。

    针对确定性场景自动生成修复补丁，不依赖 LLM：
      - ImportError / ModuleNotFoundError → 搜索模块位置，修正导入路径
      - SyntaxError → 补全括号/冒号/引号
      - IndentationError / TabError → 统一缩进
      - AttributeError → 基于 Levenshtein 距离提示拼写修正
      - NameError → 检测常见导入缺失

    确定性场景标记 auto_fixable=True
    非确定性场景标记 requires_human_review=True
    """

    # 可自动修复的异常分类
    AUTO_FIXABLE_CATEGORIES = {
        "import",      # ~70% 可自动
        "syntax",      # ~60% 可自动
        "attribute",   # ~40% 可自动
        "name",        # ~30% 可自动
    }

    def can_auto_fix(self, parsed: ParsedError) -> bool:
        """判断该异常是否可自动修复（确定性场景）。"""
        return parsed.category in self.AUTO_FIXABLE_CATEGORIES

    def generate_fix(
        self,
        parsed: ParsedError,
        task_id: str = "",
    ) -> dict[str, Any]:
        """
        根据解析后的异常生成修复方案。

        Returns:
            {
                "auto_fixable": bool,
                "requires_human_review": bool,
                "strategy": str,           # 修复策略描述
                "patches": [               # 修复补丁列表
                    {
                        "file": str,
                        "line": int,
                        "old_text": str,   # 原始代码行
                        "new_text": str,   # 修复后代码行
                        "type": str,       # replace_line | replace_block | insert_line
                        "confidence": float,
                    }
                ],
                "warnings": [str],         # 注意事项
            }
        """
        category = parsed.category
        if category == "import":
            return self._fix_import_error(parsed)
        elif category == "syntax":
            return self._fix_syntax_error(parsed)
        elif category == "attribute":
            return self._fix_attribute_error(parsed)
        elif category == "name":
            return self._fix_name_error(parsed)
        else:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"非确定性场景 ({parsed.category})，需要人工分析",
                "patches": [],
                "warnings": [f"异常类型 '{parsed.error_type}' 不支持自动修复"],
            }

    # ── ImportError 修复 ─────────────────────────────────

    def _fix_import_error(self, parsed: ParsedError) -> dict[str, Any]:
        """修复导入错误。"""
        # 从错误消息中提取模块名
        # "No module named 'foo'" 或 "No module named 'foo.bar'"
        module_match = re.search(
            r"(?:No module named|named)\s+['\"](\S+?)['\"]",
            parsed.error_message,
        )
        if not module_match:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "无法从错误消息中提取模块名",
                "patches": [],
                "warnings": ["无法解析模块名，请手动检查 import 语句"],
            }

        missing_module = module_match.group(1)

        # 在 SANDBOX_DIR 下搜索同名 .py 文件
        candidates = list(SANDBOX_DIR.rglob(f"{missing_module}.py"))
        # 也搜索包含该名字的目录（__init__.py）
        candidates += [
            d / "__init__.py"
            for d in SANDBOX_DIR.rglob(missing_module)
            if d.is_dir() and (d / "__init__.py").is_file()
        ]

        if not candidates:
            # 检查是否是第三方库（pip 可安装）
            common_pip_map: dict[str, str] = {
                "yaml": "PyYAML",
                "PIL": "Pillow",
                "cv2": "opencv-python",
                "numpy": "numpy",
                "pandas": "pandas",
                "requests": "requests",
                "bs4": "beautifulsoup4",
                "lxml": "lxml",
                "dotenv": "python-dotenv",
                "psycopg2": "psycopg2-binary",
                "sklearn": "scikit-learn",
            }
            pip_name = common_pip_map.get(missing_module, missing_module)

            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"模块 '{missing_module}' 未在项目内找到，可能是第三方依赖",
                "patches": [],
                "warnings": [
                    f"模块 '{missing_module}' 可能未安装",
                    f"尝试: pip install {pip_name}",
                    f"或检查 PYTHONPATH 是否包含该模块所在目录",
                ],
            }

        # 找到候选文件，计算相对导入路径
        if not parsed.file_path:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"找到模块文件但无法确定源文件路径",
                "patches": [],
                "warnings": ["traceback 中缺少文件路径信息"],
            }

        source_file = SANDBOX_DIR / parsed.file_path
        target_file = candidates[0]

        # 计算从源文件到目标模块的相对导入路径
        try:
            source_dir = source_file.parent.resolve()
            target_path = target_file.resolve()

            # 计算相对路径
            import_path = self._compute_import_path(source_dir, target_path)

            # 读取源文件中出错的那一行
            source_lines = source_file.read_text(encoding="utf-8").split("\n")
            if parsed.line_number < 1 or parsed.line_number > len(source_lines):
                return {
                    "auto_fixable": False,
                    "requires_human_review": True,
                    "strategy": "行号超出文件范围",
                    "patches": [],
                    "warnings": [f"行号 {parsed.line_number} 超出文件范围"],
                }

            old_line = source_lines[parsed.line_number - 1]
            # 尝试替换 import 语句中的模块路径
            new_line = self._replace_import_target(old_line, missing_module, import_path)

            return {
                "auto_fixable": True,
                "requires_human_review": False,
                "strategy": (
                    f"将 '{parsed.file_path}' 第 {parsed.line_number} 行的 "
                    f"import '{missing_module}' 修正为 '{import_path}'"
                ),
                "patches": [
                    {
                        "file": parsed.file_path,
                        "line": parsed.line_number,
                        "old_text": old_line,
                        "new_text": new_line,
                        "type": "replace_line",
                        "confidence": 0.85,
                    }
                ],
                "warnings": [
                    f"自动修正导入路径: {missing_module} → {import_path}",
                    "请人工确认导入路径正确后再运行测试",
                ],
            }
        except Exception as exc:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"计算导入路径时出错: {exc}",
                "patches": [],
                "warnings": [str(exc)],
            }

    def _compute_import_path(self, source_dir: Path, target_path: Path) -> str:
        """计算从 source_dir 到 target_path 的 Python 导入路径。"""
        # 如果目标在源目录或其子目录下
        try:
            rel = target_path.relative_to(source_dir)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].replace(".py", "")
            return ".".join(parts)
        except ValueError:
            pass

        # 目标在源目录的父级或同级
        try:
            rel = target_path.relative_to(SANDBOX_DIR)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].replace(".py", "")
            return ".".join(parts)
        except ValueError:
            pass

        # 回退：使用目标文件名
        return target_path.stem

    def _replace_import_target(
        self,
        old_line: str,
        old_module: str,
        new_module: str,
    ) -> str:
        """替换 import 语句中的模块名。"""
        # import foo.bar → import new.path.bar
        # from foo.bar import baz → from new.path.bar import baz
        return old_line.replace(old_module, new_module, 1)

    # ── SyntaxError 修复 ─────────────────────────────────

    def _fix_syntax_error(self, parsed: ParsedError) -> dict[str, Any]:
        """修复语法错误。"""
        patches: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not parsed.file_path or not parsed.line_number:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "缺少文件/行号信息，无法自动修复",
                "patches": [],
                "warnings": ["traceback 信息不完整"],
            }

        full_path = SANDBOX_DIR / parsed.file_path
        if not full_path.is_file():
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"文件 '{parsed.file_path}' 不存在",
                "patches": [],
                "warnings": [f"无法读取文件: {parsed.file_path}"],
            }

        try:
            lines = full_path.read_text(encoding="utf-8").split("\n")
        except Exception:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "无法读取文件",
                "patches": [],
                "warnings": ["文件读取失败"],
            }

        if parsed.line_number > len(lines):
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "行号超出文件范围",
                "patches": [],
                "warnings": [f"行号 {parsed.line_number} > 文件总行数 {len(lines)}"],
            }

        err_line = lines[parsed.line_number - 1] if not parsed.code_context else parsed.code_context
        err_msg = parsed.error_message

        # 模式 1: 括号不匹配
        if "unmatched" in err_msg.lower() or "was never closed" in err_msg.lower():
            fix = self._fix_unmatched_parens(lines, parsed.line_number, err_line)
            if fix:
                patches.append(fix)

        # 模式 2: 缺少冒号
        if "expected ':'" in err_msg.lower() or ":" in err_msg and "expected" in err_msg.lower():
            fix = self._fix_missing_colon(err_line, parsed.line_number)
            if fix:
                patches.append(fix)

        # 模式 3: 缩进问题
        if isinstance(parsed, ParsedError) and parsed.error_type in ("IndentationError", "TabError"):
            fix = self._fix_indentation(lines, parsed.line_number)
            if fix:
                patches.append(fix)

        # 模式 4: 字符串未闭合
        if "unterminated" in err_msg.lower() or "EOL while scanning" in err_msg:
            fix = self._fix_unterminated_string(err_line, parsed.line_number)
            if fix:
                patches.append(fix)

        # 模式 5: 无效语法 — 尝试用 ast.parse 定位具体列
        if "invalid syntax" in err_msg.lower() and not patches:
            fix = self._fix_invalid_syntax(lines, parsed.line_number, err_msg)
            if fix:
                patches.append(fix)

        if patches:
            return {
                "auto_fixable": True,
                "requires_human_review": False,
                "strategy": f"自动修复 {parsed.file_path}:{parsed.line_number} 的 {parsed.error_type}",
                "patches": patches,
                "warnings": warnings or ["语法修复已自动应用，请人工复审"],
            }
        else:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"无法自动修复 '{parsed.error_type}'，需人工介入",
                "patches": [],
                "warnings": [f"错误行: {err_line}", f"错误消息: {err_msg}"],
            }

    def _fix_unmatched_parens(
        self,
        lines: list[str],
        line_no: int,
        err_line: str,
    ) -> dict[str, Any] | None:
        """尝试修复括号不匹配。"""
        # 统计整行的括号
        counts = {
            "(": err_line.count("(") - err_line.count(")"),
            "[": err_line.count("[") - err_line.count("]"),
            "{": err_line.count("{") - err_line.count("}"),
        }

        missing_closers = []
        for opener, count in counts.items():
            if count > 0:
                closer = {")": "(", "]": "[", "}": "{"}
                # 反向查找
                rev = {v: k for k, v in closer.items()}
                missing_closers.extend([rev.get(opener, opener)] * count)

        if missing_closers:
            new_line = err_line.rstrip() + "".join(missing_closers)
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": new_line,
                "type": "replace_line",
                "confidence": 0.9,
            }

        # 检查是否有未闭合的括号跨行
        # 向上查找未闭合的括号
        opener_stack: list[str] = []
        for i in range(max(0, line_no - 10), min(len(lines), line_no + 1)):
            for ch in lines[i]:
                if ch in "([{":
                    opener_stack.append(ch)
                elif ch in ")]}":
                    if opener_stack and (
                        (ch == ")" and opener_stack[-1] == "(")
                        or (ch == "]" and opener_stack[-1] == "[")
                        or (ch == "}" and opener_stack[-1] == "{")
                    ):
                        opener_stack.pop()

        if opener_stack:
            closer_map = {"(": ")", "[": "]", "{": "}"}
            new_line = err_line.rstrip() + "".join(
                closer_map.get(op, op) for op in reversed(opener_stack)
            )
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": new_line,
                "type": "replace_line",
                "confidence": 0.75,
            }

        return None

    def _fix_missing_colon(self, err_line: str, line_no: int) -> dict[str, Any] | None:
        """修复缺少冒号。"""
        stripped = err_line.rstrip()
        # 以 def/if/else/elif/for/while/class/try/except/finally/with 开头
        # 但结尾没有冒号的行
        col_keywords = r'^\s*(def|if|elif|else|for|while|class|try|except|finally|with|match|case)\b'
        if re.match(col_keywords, stripped) and not stripped.endswith(":"):
            # 检查是否在注释/字符串之后
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": stripped + ":",
                "type": "replace_line",
                "confidence": 0.95,
            }
        return None

    def _fix_indentation(
        self,
        lines: list[str],
        line_no: int,
    ) -> dict[str, Any] | None:
        """修复缩进问题 — 检测并统一当前代码块缩进。"""
        if line_no < 1 or line_no > len(lines):
            return None

        err_line = lines[line_no - 1]

        # 检测缩进风格：查找附近行的缩进
        indent_sizes: dict[int, int] = {}
        for i in range(max(0, line_no - 20), min(len(lines), line_no + 20)):
            line = lines[i]
            if not line.strip():
                continue
            ws = len(line) - len(line.lstrip())
            if ws > 0:
                indent_sizes[ws] = indent_sizes.get(ws, 0) + 1

        if not indent_sizes:
            return None

        # 找到最常见缩进
        most_common_indent = max(indent_sizes, key=lambda k: indent_sizes[k])

        # 检测是否混用 tab/空格
        has_tabs = any("\t" in lines[i] for i in range(max(0, line_no - 10), min(len(lines), line_no + 10)))
        has_spaces = any(
            lines[i].startswith(" ")
            for i in range(max(0, line_no - 10), min(len(lines), line_no + 10))
            if lines[i].strip()
        )

        if has_tabs and has_spaces:
            # 统一为空格
            spaces_per_tab = most_common_indent or 4
            new_line = err_line.replace("\t", " " * spaces_per_tab)
            # 规范化前导空格
            leading_ws = len(new_line) - len(new_line.lstrip())
            normalized_ws = (leading_ws // spaces_per_tab) * spaces_per_tab
            new_line = " " * normalized_ws + new_line.lstrip()
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": new_line,
                "type": "replace_line",
                "confidence": 0.7,
            }

        return None

    def _fix_unterminated_string(
        self,
        err_line: str,
        line_no: int,
    ) -> dict[str, Any] | None:
        """尝试修复未闭合的字符串。"""
        stripped = err_line.strip()

        # 检测未闭合的三引号
        if stripped.count('"""') % 2 == 1:
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": err_line.rstrip() + '"""',
                "type": "replace_line",
                "confidence": 0.6,
            }
        if stripped.count("'''") % 2 == 1:
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": err_line.rstrip() + "'''",
                "type": "replace_line",
                "confidence": 0.6,
            }

        # 检测未闭合的单引号/双引号
        # 简单启发式：引号数量为奇数
        single_quotes = stripped.count("'") - stripped.count('"') * 0  # 粗略
        if stripped.count("'") % 2 == 1:
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": err_line.rstrip() + "'",
                "type": "replace_line",
                "confidence": 0.5,
            }
        if stripped.count('"') % 2 == 1:
            return {
                "file": "",
                "line": line_no,
                "old_text": err_line,
                "new_text": err_line.rstrip() + '"',
                "type": "replace_line",
                "confidence": 0.5,
            }

        return None

    def _fix_invalid_syntax(
        self,
        lines: list[str],
        line_no: int,
        err_msg: str,
    ) -> dict[str, Any] | None:
        """尝试修复无效语法（通过 ast 检查）。"""
        if line_no < 1 or line_no > len(lines):
            return None

        err_line = lines[line_no - 1]

        # 尝试常见的 Python 语法转换
        fixes_to_try: list[tuple[str, str]] = []

        # Python 2 style print → Python 3
        if re.match(r'^\s*print\s+[^(]', err_line):
            new_line = re.sub(r'^(\\s*print)\\s+(.+)$', r'\\1(\\2)', err_line)
            fixes_to_try.append(("Python 2 print → Python 3", new_line))

        # 缺少 'pass' 的空代码块
        if re.match(r'^\s*(def|if|elif|else|for|while|class|try|except|finally|with)\b.*:\s*$', err_line):
            # 检查下一行是否为空或没有缩进
            if line_no < len(lines) and not lines[line_no].strip():
                new_line = err_line + " pass"
                fixes_to_try.append(("添加 pass", new_line))

        # 常见的拼写/操作符错误
        if "=+" in err_line:
            new_line = err_line.replace("=+", "+=")
            fixes_to_try.append(("=+ → +=", new_line))
        if "=-" in err_line:
            new_line = err_line.replace("=-", "-=")
            fixes_to_try.append(("=- → -=", new_line))
        if "is not" in err_line and "!=" not in err_line:
            # 可能是 'is not None' 之类的正确用法，跳过
            pass

        for desc, new_line in fixes_to_try:
            try:
                ast.parse(new_line)
                return {
                    "file": "",
                    "line": line_no,
                    "old_text": err_line,
                    "new_text": new_line,
                    "type": "replace_line",
                    "confidence": 0.8,
                }
            except SyntaxError:
                continue

        return None

    # ── AttributeError 修复 ───────────────────────────────

    def _fix_attribute_error(self, parsed: ParsedError) -> dict[str, Any]:
        """修复属性错误 — 基于 Levenshtein 距离提示拼写修正。"""
        err_msg = parsed.error_message

        # "type object 'Foo' has no attribute 'bar'"
        # "'Foo' object has no attribute 'bar'"
        attr_match = re.search(
            r"has no attribute\s+['\"](\w+)['\"]",
            err_msg,
        )
        obj_match = re.search(
            r"(?:type object|object)\s+['\"](\w+)['\"]",
            err_msg,
        )

        if not attr_match:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "无法从错误消息中提取属性名",
                "patches": [],
                "warnings": ["请手动检查对象类型和可用属性"],
            }

        missing_attr = attr_match.group(1)
        obj_name = obj_match.group(1) if obj_match else "Unknown"

        # 尝试读取源文件，搜索该对象的所有属性引用
        suggestions: list[str] = []
        if parsed.file_path:
            full_path = SANDBOX_DIR / parsed.file_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    # 搜索 obj.xxx 模式
                    attr_pattern = re.compile(
                        rf'\b{re.escape(obj_name)}\.(\w+)'
                    )
                    all_attrs = set(attr_pattern.findall(content))

                    # 基于 Levenshtein 距离找最接近的属性
                    close_matches = difflib.get_close_matches(
                        missing_attr,
                        list(all_attrs),
                        n=3,
                        cutoff=0.6,
                    )
                    suggestions = close_matches
                except Exception:
                    pass

        if suggestions:
            return {
                "auto_fixable": True,
                "requires_human_review": True,  # 属性修复需要人工确认
                "strategy": (
                    f"属性 '{missing_attr}' 可能拼写错误，"
                    f"建议替换为: {', '.join(suggestions)}"
                ),
                "patches": [
                    {
                        "file": parsed.file_path,
                        "line": parsed.line_number,
                        "old_text": parsed.code_context or missing_attr,
                        "new_text": f"# FIXME: '{missing_attr}' 可能应为 '{suggestions[0]}'",
                        "type": "replace_line",
                        "confidence": 0.6,
                    }
                ],
                "warnings": [
                    f"属性 '{missing_attr}' 在 {obj_name} 上不存在",
                    f"最接近的已有属性: {suggestions}",
                    "⚠️ 属性修复需人工确认后应用",
                ],
            }
        else:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": f"对象 '{obj_name}' 没有属性 '{missing_attr}'，需要人工分析",
                "patches": [],
                "warnings": [
                    f"未找到与 '{missing_attr}' 相似的属性",
                    "可能需要添加属性定义或检查对象类型",
                ],
            }

    # ── NameError 修复 ────────────────────────────────────

    def _fix_name_error(self, parsed: ParsedError) -> dict[str, Any]:
        """修复名称错误 — 检测未定义的变量/函数名。"""
        err_msg = parsed.error_message

        # "name 'foo' is not defined"
        name_match = re.search(r"name\s+['\"](\w+)['\"]\s+is not defined", err_msg)
        if not name_match:
            return {
                "auto_fixable": False,
                "requires_human_review": True,
                "strategy": "无法从错误消息中提取变量名",
                "patches": [],
                "warnings": ["请手动查找未定义的名称"],
            }

        missing_name = name_match.group(1)

        # 检查是否是常见的内置函数/模块名拼写错误
        common_builtins = {
            "len": "len",
            "print": "print",
            "range": "range",
            "int": "int",
            "str": "str",
            "list": "list",
            "dict": "dict",
            "set": "set",
            "tuple": "tuple",
            "bool": "bool",
            "float": "float",
            "type": "type",
            "open": "open",
            "input": "input",
            "enumerate": "enumerate",
            "zip": "zip",
            "map": "map",
            "filter": "filter",
            "sorted": "sorted",
            "reversed": "reversed",
            "max": "max",
            "min": "min",
            "sum": "sum",
            "abs": "abs",
            "round": "round",
            "isinstance": "isinstance",
            "hasattr": "hasattr",
            "getattr": "getattr",
            "setattr": "setattr",
            "True": "True",
            "False": "False",
            "None": "None",
            "Exception": "Exception",
            "ValueError": "ValueError",
            "TypeError": "TypeError",
        }

        # Levenshtein 距离检查
        close = difflib.get_close_matches(
            missing_name,
            list(common_builtins.keys()),
            n=3,
            cutoff=0.7,
        )

        if close and close[0] != missing_name:
            return {
                "auto_fixable": True,
                "requires_human_review": True,
                "strategy": f"'{missing_name}' 可能拼写错误，最接近: '{close[0]}'",
                "patches": [
                    {
                        "file": parsed.file_path,
                        "line": parsed.line_number,
                        "old_text": parsed.code_context or missing_name,
                        "new_text": f"# FIXME: '{missing_name}' 可能应为 '{close[0]}'",
                        "type": "replace_line",
                        "confidence": 0.55,
                    }
                ],
                "warnings": [
                    f"'{missing_name}' 可能拼写错误",
                    f"建议: {', '.join(close)}",
                    "⚠️ 请人工确认后应用修复",
                ],
            }

        # 检查是否是忘记导入
        if parsed.file_path:
            full_path = SANDBOX_DIR / parsed.file_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    # 搜索整个项目中是否有定义该名字的文件
                    found_defs = []
                    for py_file in SANDBOX_DIR.rglob("*.py"):
                        if py_file == full_path:
                            continue
                        try:
                            fc = py_file.read_text(encoding="utf-8")
                            if re.search(rf'\bdef\s+{re.escape(missing_name)}\b', fc):
                                rel_path = self._compute_import_path(
                                    full_path.parent,
                                    py_file,
                                )
                                found_defs.append(rel_path)
                            elif re.search(rf'\bclass\s+{re.escape(missing_name)}\b', fc):
                                found_defs.append(py_file.stem)
                        except Exception:
                            pass

                    if found_defs:
                        return {
                            "auto_fixable": True,
                            "requires_human_review": True,
                            "strategy": f"'{missing_name}' 可能缺少导入",
                            "patches": [],
                            "warnings": [
                                f"'{missing_name}' 定义位置: {found_defs}",
                                f"建议添加: from {found_defs[0]} import {missing_name}",
                                "⚠️ 自动添加导入需要 LLM 辅助",
                            ],
                        }
                except Exception:
                    pass

        return {
            "auto_fixable": False,
            "requires_human_review": True,
            "strategy": f"'{missing_name}' 未定义，需要手动添加定义或导入",
            "patches": [],
            "warnings": [
                f"未定义的名称: '{missing_name}'",
                "检查是否拼写错误、作用域问题或缺少导入",
            ],
        }


# ═══════════════════════════════════════════════════════════
# 5 个阶段执行器 — 注册到 executor_registry
# ═══════════════════════════════════════════════════════════

_fixer = RuleBasedFixer()


@register_executor("诊断", description="解析 traceback，生成诊断报告")
def repair_diagnose(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    阶段 1: 诊断
    从 params 中读取 traceback 文本，解析并生成结构化诊断报告。
    将诊断结果写入 checkpoint，供后续阶段使用。
    """
    traceback_text = params.get("traceback", "")
    error_source = params.get("error_source", "offline")

    if not traceback_text:
        return {
            "status": "failed",
            "error": "缺少 traceback 文本（params.traceback）",
            "phase": phase,
        }

    # 调用 auto_repair 的诊断
    diagnosis_text = _orchestrator.diagnose(traceback_text, error_source)

    # 同时获取结构化的 ParsedError
    try:
        parsed = _parser.parse(traceback_text)
        diag_data = {
            "error_type": parsed.error_type,
            "error_message": parsed.error_message,
            "file_path": parsed.file_path,
            "line_number": parsed.line_number,
            "function_name": parsed.function_name,
            "code_context": parsed.code_context,
            "category": parsed.category,
            "severity": parsed.severity,
            "full_traceback": traceback_text,
        }
    except AutoRepairError:
        diag_data = {"error_type": "Unknown", "category": "unknown", "full_traceback": traceback_text}

    diagnosis_json = json.dumps(diag_data, ensure_ascii=False)

    return {
        "status": "done",
        "phase": phase,
        "diagnosis_text": diagnosis_text,
        "diagnosis_json": diagnosis_json,
        "diag_data": diag_data,
        "output": f"诊断完成: {diag_data.get('error_type', 'Unknown')} ({diag_data.get('category', 'unknown')})",
    }


@register_executor("计划", description="基于诊断报告生成修复计划")
def repair_plan(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    阶段 2: 计划
    从上一阶段的 checkpoint 中读取诊断结果，生成修复计划。
    """
    cp = CheckpointManager()
    checkpoints = cp.list(task_id=task_id)

    # 从最近的检查点中提取诊断数据（list 只返回摘要，需用 load 读完整 state）
    diag_data: dict[str, Any] = {}
    for ckpt in reversed(checkpoints):
        try:
            full = cp.load(ckpt["checkpoint_id"])
        except CheckpointError:
            continue
        state = full.get("state", {})
        if isinstance(state, dict):
            results = state.get("results", {})
            if isinstance(results, dict):
                diag_phase_result = results.get("诊断", {})
                if isinstance(diag_phase_result, dict) and diag_phase_result.get("diag_data"):
                    diag_data = diag_phase_result["diag_data"]
                    break

    if not diag_data:
        # 尝试从 params 中直接获取
        diag_json_str = params.get("diagnosis_json", "")
        if diag_json_str:
            try:
                diag_data = json.loads(diag_json_str)
            except json.JSONDecodeError:
                pass

    if not diag_data:
        return {
            "status": "failed",
            "error": "无法找到诊断数据（检查点为空或无诊断阶段结果）",
            "phase": phase,
        }

    # 调用 auto_repair 的计划生成
    plan_text = _orchestrator.plan(json.dumps(diag_data, ensure_ascii=False))

    # 同时用 RuleBasedFixer 评估可自动修复性
    parsed = ParsedError(
        error_type=diag_data.get("error_type", "Exception"),
        error_message=diag_data.get("error_message", ""),
        file_path=diag_data.get("file_path", ""),
        line_number=diag_data.get("line_number", 0),
        function_name=diag_data.get("function_name", ""),
        code_context=diag_data.get("code_context", ""),
        category=diag_data.get("category", "unknown"),
        severity=diag_data.get("severity", "medium"),
    )

    fix_plan = _fixer.generate_fix(parsed, task_id)

    return {
        "status": "done",
        "phase": phase,
        "plan_text": plan_text,
        "auto_fixable": fix_plan.get("auto_fixable", False),
        "requires_human_review": fix_plan.get("requires_human_review", True),
        "fix_strategy": fix_plan.get("strategy", ""),
        "fix_patches": fix_plan.get("patches", []),
        "fix_warnings": fix_plan.get("warnings", []),
        "diag_data": diag_data,
        "output": (
            f"修复计划: {'✅ 可自动修复' if fix_plan.get('auto_fixable') else '⚠️ 需人工介入'}"
            f" — {fix_plan.get('strategy', '未知策略')}"
        ),
    }


@register_executor("备份", description="创建预修复检查点，保存文件快照")
def repair_backup(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    阶段 3: 备份
    创建预修复检查点，保存即将修改的文件快照。
    """
    cp = CheckpointManager()
    checkpoints = cp.list(task_id=task_id)

    # 从上一阶段获取文件列表
    files_to_backup: list[str] = []
    for ckpt in reversed(checkpoints):
        state = ckpt.get("state", {})
        if isinstance(state, dict):
            results = state.get("results", {})
            if isinstance(results, dict):
                plan_result = results.get("计划", {})
                if isinstance(plan_result, dict):
                    patches = plan_result.get("fix_patches", [])
                    files_to_backup = list(set(
                        p.get("file", "") for p in patches if p.get("file")
                    ))
                    if files_to_backup:
                        break

    if not files_to_backup:
        # 从诊断中获取文件路径
        for ckpt in reversed(checkpoints):
            state = ckpt.get("state", {})
            if isinstance(state, dict):
                results = state.get("results", {})
                if isinstance(results, dict):
                    diag_result = results.get("诊断", {})
                    if isinstance(diag_result, dict):
                        diag_data = diag_result.get("diag_data", {})
                        fp = diag_data.get("file_path", "")
                        if fp:
                            files_to_backup = [fp]
                            break

    # 读取文件内容作为快照
    file_snapshots: dict[str, str] = {}
    for fp in files_to_backup:
        full_path = SANDBOX_DIR / fp
        if full_path.is_file():
            try:
                file_snapshots[fp] = full_path.read_text(encoding="utf-8")
            except Exception:
                file_snapshots[fp] = f"[读取失败: {fp}]"

    # 创建检查点
    cp_id = cp.save(
        task_id=task_id,
        phase="pre_repair_backup",
        state={
            "files_to_backup": files_to_backup,
            "file_snapshots": file_snapshots,
            "backup_time": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    return {
        "status": "done",
        "phase": phase,
        "checkpoint_id": cp_id,
        "files_backed_up": list(file_snapshots.keys()),
        "snapshot_count": len(file_snapshots),
        "output": f"备份完成: {len(file_snapshots)} 个文件 → 检查点 {cp_id}",
    }


@register_executor("修复", description="应用修复补丁（规则引擎自动生成）")
def repair_fix(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    阶段 4: 修复
    从计划阶段获取补丁，应用实际的文件修改。
    如果 auto_apply=False 或 requires_human_review=True，则仅生成补丁不应用。
    """
    auto_apply = params.get("auto_apply", False)

    cp = CheckpointManager()
    checkpoints = cp.list(task_id=task_id)

    # 从计划阶段获取补丁
    patches: list[dict[str, Any]] = []
    requires_human_review = True
    for ckpt in reversed(checkpoints):
        state = ckpt.get("state", {})
        if isinstance(state, dict):
            results = state.get("results", {})
            if isinstance(results, dict):
                plan_result = results.get("计划", {})
                if isinstance(plan_result, dict):
                    patches = plan_result.get("fix_patches", [])
                    requires_human_review = plan_result.get("requires_human_review", True)
                    if patches:
                        break

    if not patches:
        return {
            "status": "done",
            "phase": phase,
            "applied": False,
            "reason": "没有可应用的补丁",
            "output": "ℹ️ 无需修复（没有生成补丁）",
        }

    if not auto_apply:
        return {
            "status": "done",
            "phase": phase,
            "applied": False,
            "patches_pending": patches,
            "reason": "auto_apply=False，补丁未应用",
            "output": (
                f"📝 已生成 {len(patches)} 个修复补丁但未应用（auto_apply=False）\n"
                f"补丁详情:\n" + "\n".join(
                    f"  - {p['file']}:{p['line']}: {p.get('type', '?')} "
                    f"(置信度: {p.get('confidence', 0):.0%})"
                    for p in patches
                )
            ),
        }

    if requires_human_review:
        return {
            "status": "done",
            "phase": phase,
            "applied": False,
            "patches_pending": patches,
            "reason": "requires_human_review=True",
            "output": (
                f"⚠️ 修复需要人工审核（置信度不足以自动应用）\n"
                f"已生成 {len(patches)} 个补丁，请人工确认后再应用"
            ),
        }

    # 应用补丁
    applied = []
    failed = []
    for patch in patches:
        file_path = patch.get("file", "")
        line_no = patch.get("line", 0)
        old_text = patch.get("old_text", "")
        new_text = patch.get("new_text", "")
        patch_type = patch.get("type", "replace_line")

        if not file_path or not line_no:
            failed.append({"patch": patch, "error": "缺少文件路径或行号"})
            continue

        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            failed.append({"patch": patch, "error": f"文件不存在: {file_path}"})
            continue

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            if line_no < 1 or line_no > len(lines):
                failed.append({"patch": patch, "error": f"行号 {line_no} 超出范围"})
                continue

            if patch_type == "replace_line":
                current_line = lines[line_no - 1]
                if current_line.strip() != old_text.strip():
                    # 行内容已变更，跳过
                    failed.append({
                        "patch": patch,
                        "error": f"行内容已变更，跳过 (expected: {old_text[:50]}...)",
                    })
                    continue
                lines[line_no - 1] = new_text
            elif patch_type == "insert_line":
                lines.insert(line_no - 1, new_text)
            elif patch_type == "replace_block":
                # 简化：替换单行
                lines[line_no - 1] = new_text

            full_path.write_text("\n".join(lines), encoding="utf-8")
            applied.append(patch)
        except Exception as exc:
            failed.append({"patch": patch, "error": str(exc)})

    result = {
        "status": "done",
        "phase": phase,
        "applied": len(applied) > 0,
        "patches_applied": len(applied),
        "patches_failed": len(failed),
        "applied_list": applied,
        "failed_list": failed,
    }

    if applied:
        result["output"] = (
            f"✅ 已应用 {len(applied)} 个修复补丁\n" +
            "\n".join(
                f"  ✅ {p['file']}:{p['line']} ({p.get('confidence', 0):.0%})"
                for p in applied
            )
        )
    if failed:
        fail_text = "\n".join(
            f"  ❌ {f['patch'].get('file', '?')}:{f['patch'].get('line', '?')} — {f['error']}"
            for f in failed
        )
        result["output"] = (result.get("output", "") + f"\n❌ {len(failed)} 个补丁失败:\n{fail_text}").strip()

    return result


@register_executor("验证", description="运行测试验证修复效果")
def repair_verify(task_id: str, phase: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    阶段 5: 验证
    运行相关测试和全量回归测试，验证修复是否成功。
    """
    cp = CheckpointManager()
    checkpoints = cp.list(task_id=task_id)

    # 获取修复涉及的文件
    fix_files: list[str] = []
    patches_applied = False
    for ckpt in reversed(checkpoints):
        state = ckpt.get("state", {})
        if isinstance(state, dict):
            results = state.get("results", {})
            if isinstance(results, dict):
                fix_result = results.get("修复", {})
                if isinstance(fix_result, dict):
                    applied = fix_result.get("applied_list", [])
                    if applied:
                        patches_applied = True
                        fix_files = list(set(
                            p.get("file", "") for p in applied if p.get("file")
                        ))
                        break

    # 也检查计划阶段
    if not fix_files:
        for ckpt in reversed(checkpoints):
            state = ckpt.get("state", {})
            if isinstance(state, dict):
                results = state.get("results", {})
                if isinstance(results, dict):
                    plan_result = results.get("计划", {})
                    if isinstance(plan_result, dict):
                        diag = plan_result.get("diag_data", {})
                        fp = diag.get("file_path", "")
                        if fp:
                            fix_files = [fp]
                            break

    # 运行验证
    try:
        from .test_runner import _runner as test_runner
    except ImportError:
        return {
            "status": "done",
            "phase": phase,
            "verification_passed": None,
            "output": "⚠️ 无法导入 test_runner，跳过自动验证。请手动运行测试。",
        }

    output_lines = [
        "🧪 修复验证报告",
        f"{'='*50}",
        f"修复文件: {', '.join(fix_files) if fix_files else '未指定'}",
        f"补丁已应用: {patches_applied}",
        "",
    ]

    all_passed = True
    test_results: dict[str, Any] = {}

    # 运行相关模块测试
    if fix_files:
        for f in fix_files:
            module_name = Path(f).stem
            test_file = SANDBOX_DIR / "tests" / f"test_{module_name}.py"
            if test_file.is_file():
                result = test_runner.run_single(module_name)
                test_results[module_name] = result
                output_lines.append(f"模块测试 [{module_name}]:")
                output_lines.append(result)
                if "失败" in result or "FAIL" in result:
                    all_passed = False
            else:
                output_lines.append(f"ℹ️ 模块 {module_name} 无对应测试文件")

    # 运行全量回归测试
    output_lines.append("\n📊 全量回归测试:")
    full_result = test_runner.run_all()
    test_results["_full_regression"] = full_result
    output_lines.append(full_result)
    if "失败" in full_result or "FAIL" in full_result:
        all_passed = False

    verification_passed = all_passed

    # 更新置信度评分
    diag_data: dict[str, Any] = {}
    for ckpt in reversed(checkpoints):
        state = ckpt.get("state", {})
        if isinstance(state, dict):
            results = state.get("results", {})
            if isinstance(results, dict):
                diag_result = results.get("诊断", {})
                if isinstance(diag_result, dict):
                    diag_data = diag_result.get("diag_data", {})
                    break

    confidence_text = ""
    if diag_data:
        category = diag_data.get("category", "unknown")
        fix_line_count = len(patches_applied) if isinstance(patches_applied, int) else 1
        confidence_text = _orchestrator.confidence(
            json.dumps(diag_data, ensure_ascii=False),
            json.dumps({
                "fix_line_count": fix_line_count,
                "test_coverage_ratio": 0.5,
                "verification_passed": verification_passed,
            }, ensure_ascii=False),
        )
        output_lines.append(f"\n{confidence_text}")

    output = "\n".join(output_lines)

    return {
        "status": "done",
        "phase": phase,
        "verification_passed": verification_passed,
        "test_results": str(test_results)[:500],
        "output": output,
    }


# ═══════════════════════════════════════════════════════════
# 公开 API — 供外部直接调用的便捷函数
# ═══════════════════════════════════════════════════════════

def create_repair_offline_task(
    traceback_text: str,
    auto_apply: bool = False,
    error_source: str = "manual",
    webhook_url: str = "",
) -> dict[str, Any]:
    """
    便捷函数：根据 traceback 创建离线修复任务。

    返回可用于 offline_runner.submit() 的参数。

    Args:
        traceback_text: Python traceback 字符串
        auto_apply: 是否自动应用修复
        error_source: 异常来源
        webhook_url: 完成时回调 URL

    Returns:
        {"title": ..., "phases": [...], "params": {...}}
    """
    return {
        "title": f"自动修复任务",
        "description": f"来源: {error_source} | 自动应用: {auto_apply}",
        "phases": ["诊断", "计划", "备份", "修复", "验证"],
        "params": {
            "traceback": traceback_text,
            "error_source": error_source,
            "auto_apply": auto_apply,
        },
        "webhook_url": webhook_url,
    }


def run_repair_pipeline(
    traceback_text: str,
    auto_apply: bool = False,
) -> str:
    """
    便捷函数：一键运行完整的自主修复流水线（同步模式）。

    直接执行诊断→计划→备份→修复→验证，无需经过 offline 任务管理。

    Args:
        traceback_text: Python traceback 字符串
        auto_apply: 是否自动应用修复

    Returns:
        格式化的修复报告
    """
    task_id = f"AR-SYNC-{__import__('datetime').datetime.now().strftime('%Y%m%d%H%M%S')}"
    params = {"traceback": traceback_text, "auto_apply": auto_apply, "error_source": "direct"}

    phases = [
        ("诊断", repair_diagnose),
        ("计划", repair_plan),
        ("备份", repair_backup),
        ("修复", repair_fix),
        ("验证", repair_verify),
    ]

    results: dict[str, dict[str, Any]] = {}
    final_status = "done"

    for phase_name, executor in phases:
        try:
            result = executor(task_id, phase_name, params)
            results[phase_name] = result
            if result.get("status") == "failed":
                final_status = "failed"
                break
        except Exception as exc:
            results[phase_name] = {"status": "failed", "error": str(exc)}
            final_status = "failed"
            break

    lines = [
        f"{'✅' if final_status == 'done' else '❌'} 自主修复流水线报告",
        f"{'='*60}",
        f"任务 ID: {task_id}",
        f"",
    ]

    for phase_name, result in results.items():
        icon = "✅" if result.get("status") == "done" else "❌"
        lines.append(f"{icon} 阶段: {phase_name}")
        output = result.get("output", "")
        if output:
            for ol in output.split("\n")[:5]:
                lines.append(f"   {ol}")
        lines.append("")

    return "\n".join(lines)
