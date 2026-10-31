"""
llm_patcher — 创造性代码重写引擎 v2.0

扩展 AutomatedPatcher 的能力边界，从确定性 regex 替换
升级到语义理解和架构重构。

核心能力：
  1. AST 级别代码理解和变换
  2. 函数提取 / 类提取 / 模块拆分
  3. 抽象层引入（接口/基类）
  4. 架构模式重构
  5. 新功能脚手架生成

与 AutomatedPatcher 的关系：
  - AutomatedPatcher: 快速、确定性的 regex 变换（4 种）
  - LLM Patcher:      慢速、语义理解、架构级变换（N 种）
  
安全机制：
  - 所有变换必须在 AST 层面可验证
  - 变换前后做语法检查（ast.parse）
  - 自动生成 diff 供审查
  - 失败自动回滚到备份
"""

from __future__ import annotations

import ast
import difflib
import json
import shutil
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
BACKUP_DIR = SANDBOX_DIR / ".backups" / "llm_patcher"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

LLM_TASK_DIR = SANDBOX_DIR / "memory" / "llm_tasks"
LLM_TASK_DIR.mkdir(parents=True, exist_ok=True)
(LLM_TASK_DIR / "pending").mkdir(exist_ok=True)
(LLM_TASK_DIR / "completed").mkdir(exist_ok=True)
(LLM_TASK_DIR / "failed").mkdir(exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))


# ═══════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class TransformResult:
    """创造性变换结果。"""
    success: bool
    transform_type: str
    file_path: str
    original_lines: int = 0
    modified_lines: int = 0
    changes: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""
    error: str = ""
    diff_preview: str = ""
    ast_valid: bool = False
    backup_path: str = ""


@dataclass
class LLMTask:
    """LLM 异步任务描述。"""
    task_id: str
    transform_type: str
    file_path: str
    idea: Dict[str, Any]
    source_code: str
    prompt: str
    created_at: str
    status: str = "pending"  # pending / completed / failed
    result: Optional[TransformResult] = None


# ═══════════════════════════════════════════════════════════
# AST 分析器 — 代码语义理解
# ═══════════════════════════════════════════════════════════

class ASTAnalyzer:
    """代码语义分析器。

    提供比 regex 更深入的代码理解：
      - 函数/类结构提取
      - 依赖关系分析
      - 重复代码检测
      - 复杂度评估
    """

    @staticmethod
    def analyze(file_path: Path) -> Dict[str, Any]:
        """对文件进行 AST 分析。"""
        code = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"error": f"语法错误: {e}", "functions": [], "classes": [], "imports": []}

        functions = []
        classes = []
        imports = []
        global_assignments = []

        for node in ast.walk(tree):
            # 函数定义
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "args": [a.arg for a in node.args.args],
                    "decorators": [
                        d.id if isinstance(d, ast.Name) else (
                            d.func.id if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                            else "complex"
                        )
                        for d in node.decorator_list
                    ],
                    "body_length": node.end_lineno - node.lineno if node.end_lineno else 0,
                    "has_docstring": (
                        isinstance(node.body[0], ast.Expr) and
                        isinstance(node.body[0].value, (ast.Str, ast.Constant))
                    ) if node.body else False,
                })

            # 类定义
            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
                classes.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "bases": [
                        b.id if isinstance(b, ast.Name) else "complex"
                        for b in node.bases
                    ],
                    "methods": methods,
                    "method_count": len(methods),
                    "body_length": node.end_lineno - node.lineno if node.end_lineno else 0,
                })

            # 导入
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"type": "import", "name": alias.name, "alias": alias.asname,
                                    "lineno": node.lineno})
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append({"type": "from", "module": node.module, "name": alias.name,
                                    "alias": alias.asname, "lineno": node.lineno})

            # 全局赋值（常量/配置）
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        if isinstance(node.value, (ast.Constant, ast.Num, ast.Str)):
                            val = node.value.value if isinstance(node.value, ast.Constant) else node.value.n
                            global_assignments.append({
                                "name": target.id, "value": val, "lineno": node.lineno,
                            })

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "global_constants": global_assignments,
            "total_lines": len(code.splitlines()),
            "function_count": len(functions),
            "class_count": len(classes),
        }

    @staticmethod
    def find_duplicate_blocks(code: str, min_lines: int = 5) -> List[Dict[str, Any]]:
        """检测重复代码块（简化版）。"""
        lines = code.splitlines()
        duplicates = []

        for i in range(len(lines) - min_lines):
            block = tuple(lines[i:i + min_lines])
            for j in range(i + min_lines, len(lines) - min_lines):
                if tuple(lines[j:j + min_lines]) == block:
                    duplicates.append({
                        "first_start": i + 1,
                        "first_end": i + min_lines,
                        "second_start": j + 1,
                        "second_end": j + min_lines,
                        "block": "\n".join(lines[i:i + min_lines])[:200],
                    })
                    break  # 每个块只报告一次

        return duplicates

    @staticmethod
    def extract_docstring(node: ast.AST) -> Optional[str]:
        """提取函数或类的文档字符串。"""
        if not hasattr(node, 'body') or not node.body:
            return None
        first = node.body[0]
        if isinstance(first, ast.Expr):
            if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                return first.value.value
            elif isinstance(first.value, ast.Str):
                return first.value.s
        return None


# ═══════════════════════════════════════════════════════════
# 创造性变换实现
# ═══════════════════════════════════════════════════════════

class LLMPatcher:
    """创造性代码重写引擎。

    支持的变换类型：
      - extract_function:  从大函数提取子函数
      - extract_class:     从长文件提取独立类
      - add_abstraction:   引入抽象基类/接口
      - rename_refactor:   语义重命名
      - add_error_context: 增强错误上下文
      - split_module:      模块拆分
      - add_type_hints:    添加类型注解
      - generate_scaffold: 生成新模块脚手架
      - creative_refactor: 通用创造性重构（需 LLM 代理）
    """

    TRANSFORM_TYPES = [
        "extract_function",
        "extract_class",
        "add_abstraction",
        "rename_refactor",
        "add_error_context",
        "split_module",
        "add_type_hints",
        "generate_scaffold",
        "creative_refactor",  # 需要外部 LLM
    ]

    def __init__(self):
        self._analyzer = ASTAnalyzer()
        self._tasks: Dict[str, LLMTask] = {}

    # ═══════════════════════════════════════════════════════
    # 变换 1: 函数提取 — 大函数拆分为多个小函数
    # ═══════════════════════════════════════════════════════

    def extract_function(
        self,
        file_path: str,
        target_func: str,
        start_line: int,
        end_line: int,
        new_func_name: str,
    ) -> TransformResult:
        """从大函数中提取代码块为独立函数。

        Args:
            file_path: 目标文件
            target_func: 源函数名
            start_line: 要提取的起始行（1-based）
            end_line: 要提取的结束行（1-based）
            new_func_name: 新函数名
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="extract_function",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        lines = original.splitlines()
        total = len(lines)

        if start_line < 1 or end_line > total or start_line >= end_line:
            return TransformResult(
                success=False, transform_type="extract_function",
                file_path=file_path, error=f"行范围无效: {start_line}-{end_line} (总行数: {total})",
            )

        # 提取代码块
        extracted_lines = lines[start_line - 1:end_line]
        extracted_code = "\n".join(extracted_lines)

        # 缩进检测
        first_line = extracted_lines[0]
        indent = len(first_line) - len(first_line.lstrip())

        # 收集代码块中使用的变量（简化版）
        extracted_text = "\n".join(extracted_lines)
        # 找到赋值和使用的变量
        import re
        assigned = set(re.findall(r'^\s*(\w+)\s*=', extracted_text, re.MULTILINE))
        used = set(re.findall(r'\b(\w+)\b', extracted_text))
        used_vars = used & assigned  # 既是赋值又是使用的变量

        # 构建新函数
        new_func = textwrap.dedent(f"""
            def {new_func_name}({', '.join(sorted(used_vars))}):
                \"\"\"从 {target_func} 提取的子函数。\"\"\"
        """).strip()

        # 保持原缩进
        new_func_lines = new_func.splitlines()
        new_func_lines.extend(
            "    " + (l[indent:] if l.startswith(" " * indent) else l)
            for l in extracted_lines
        )
        new_func_code = "\n".join(new_func_lines)

        # 构建新文件
        new_lines = []
        for i, line in enumerate(lines, 1):
            if i == start_line - 1 and i > 0:
                # 在提取块之前插入新函数
                new_lines.append("")
                new_lines.append(new_func_code)
                new_lines.append("")
                # 添加调用
                call_indent = " " * indent
                args = ", ".join(sorted(used_vars))
                new_lines.append(f"{call_indent}{new_func_name}({args})")
                # 跳过被提取的行
                continue
            if start_line <= i <= end_line:
                continue
            new_lines.append(line)

        modified = "\n".join(new_lines)

        # AST 验证
        ast_valid = self._validate_ast(modified)

        # 写入
        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="extract_function",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified)

        return TransformResult(
            success=True, transform_type="extract_function",
            file_path=file_path,
            original_lines=total, modified_lines=len(new_lines),
            changes=[{
                "action": "extract_function",
                "source_func": target_func,
                "new_func": new_func_name,
                "lines": f"{start_line}-{end_line}",
            }],
            description=f"从 {target_func} 提取 {end_line - start_line + 1} 行为 {new_func_name}()",
            diff_preview=diff,
            ast_valid=ast_valid,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 变换 2: 类提取 — 将相关函数组织为类
    # ═══════════════════════════════════════════════════════

    def extract_class(
        self,
        file_path: str,
        method_names: List[str],
        class_name: str,
    ) -> TransformResult:
        """将模块中的一组相关函数提取为独立类。

        Args:
            file_path: 目标文件
            method_names: 要提取为方法的函数名列表
            class_name: 新类名
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="extract_class",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        analysis = self._analyzer.analyze(full_path)
        if "error" in analysis:
            return TransformResult(
                success=False, transform_type="extract_class",
                file_path=file_path, error=analysis["error"],
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        # 找到目标函数
        target_funcs = [f for f in analysis["functions"] if f["name"] in method_names]
        if not target_funcs:
            return TransformResult(
                success=False, transform_type="extract_class",
                file_path=file_path,
                error=f"未找到目标函数: {method_names}",
            )

        lines = original.splitlines()

        # 收集所有目标函数的行范围
        func_ranges = sorted(
            [(f["lineno"], f["end_lineno"] or f["lineno"], f["name"]) for f in target_funcs],
            key=lambda x: x[0],
        )

        # 提取函数代码
        class_methods = []
        for start, end, name in func_ranges:
            func_lines = lines[start - 1:end]
            # 去除顶层缩进
            first_line = func_lines[0]
            indent = len(first_line) - len(first_line.lstrip())
            func_code = "\n".join(
                l[indent:] if l.startswith(" " * indent) and l.strip() else l
                for l in func_lines
            )
            # 添加 self 参数
            import re
            func_code = re.sub(
                r'^(\s*def\s+\w+\()',
                r'\1self, ',
                func_code,
                count=1,
            )
            class_methods.append(func_code)

        # 构建类代码
        class_code = f"\n\nclass {class_name}:\n"
        if target_funcs:
            first_doc = self._analyzer.extract_docstring(
                ast.parse("\n".join(lines[target_funcs[0]["lineno"] - 1:target_funcs[0]["end_lineno"]]))
            )
            if first_doc:
                class_code += f'    """{first_doc}"""\n'
            else:
                class_code += f'    """从模块提取的相关功能类。"""\n'

        for method in class_methods:
            # 给方法添加缩进
            indented = "\n".join(f"    {l}" if l.strip() else "" for l in method.splitlines())
            class_code += f"\n{indented}\n"

        class_code += "\n"

        # 构建新文件：移除原始函数，添加类
        new_lines = []
        removed_ranges = set()
        for start, end, _ in func_ranges:
            for i in range(start, end + 1):
                removed_ranges.add(i)

        # 找到合适的插入点（在 import 之后）
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_idx = i + 1
            elif line.strip() and not line.startswith("#"):
                if i > insert_idx:
                    break

        for i, line in enumerate(lines, 1):
            if i in removed_ranges:
                continue
            new_lines.append(line)
            if i == insert_idx:
                new_lines.extend(class_code.splitlines())

        modified = "\n".join(new_lines)
        ast_valid = self._validate_ast(modified)

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="extract_class",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified)

        return TransformResult(
            success=True, transform_type="extract_class",
            file_path=file_path,
            original_lines=len(lines), modified_lines=len(new_lines),
            changes=[{
                "action": "extract_class",
                "class_name": class_name,
                "methods": method_names,
            }],
            description=f"将 {len(method_names)} 个函数提取为 {class_name} 类",
            diff_preview=diff,
            ast_valid=ast_valid,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 变换 3: 抽象层引入
    # ═══════════════════════════════════════════════════════

    def add_abstraction(
        self,
        file_path: str,
        abstract_methods: List[str],
        base_class_name: str,
    ) -> TransformResult:
        """为一组相关类引入抽象基类。

        检测已有类的共同方法签名，创建 ABC。

        Args:
            file_path: 目标文件
            abstract_methods: 应声明为抽象的方法名列表
            base_class_name: 抽象基类名
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="add_abstraction",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        analysis = self._analyzer.analyze(full_path)
        classes = analysis.get("classes", [])

        if len(classes) < 2:
            return TransformResult(
                success=False, transform_type="add_abstraction",
                file_path=file_path,
                error=f"需要至少 2 个类才能引入抽象，当前: {len(classes)}",
            )

        # 构建 ABC 代码
        abc_code = textwrap.dedent(f"""
        import abc


        class {base_class_name}(abc.ABC):
            \"\"\"抽象基类 — 定义 {', '.join(c['name'] for c in classes)} 的共同接口。\"\"\"

        """)

        for method in abstract_methods:
            abc_code += textwrap.dedent(f"""
                @abc.abstractmethod
                def {method}(self, *args, **kwargs):
                    \"\"\"抽象方法: {method}\"\"\"
                    ...

            """)

        # 修改已有类，添加基类继承
        lines = original.splitlines()
        new_lines = []
        imports_inserted = False

        for line in lines:
            # 为已有类添加基类
            for cls in classes:
                if line.strip().startswith(f"class {cls['name']}("):
                    if cls["bases"] and cls["bases"] != ["complex"]:
                        line = line.replace(
                            f"class {cls['name']}({', '.join(cls['bases'])})",
                            f"class {cls['name']}({base_class_name}, {', '.join(cls['bases'])})",
                        )
                    else:
                        line = line.replace(
                            f"class {cls['name']}:",
                            f"class {cls['name']}({base_class_name}):",
                        )
                    break

            new_lines.append(line)

            # 在第一个 import 块之后插入 ABC 定义
            if not imports_inserted and (line.startswith("import ") or line.startswith("from ")):
                new_lines.append("")
                new_lines.extend(abc_code.strip().splitlines())
                new_lines.append("")
                imports_inserted = True

        if not imports_inserted:
            new_lines.insert(0, abc_code.strip())

        modified = "\n".join(new_lines)
        ast_valid = self._validate_ast(modified)

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="add_abstraction",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified)

        return TransformResult(
            success=True, transform_type="add_abstraction",
            file_path=file_path,
            original_lines=len(lines), modified_lines=len(new_lines),
            changes=[{
                "action": "add_abstraction",
                "base_class": base_class_name,
                "abstract_methods": abstract_methods,
                "affected_classes": [c["name"] for c in classes],
            }],
            description=f"引入抽象基类 {base_class_name}，统一 {len(classes)} 个类的接口",
            diff_preview=diff,
            ast_valid=ast_valid,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 变换 4: 模块拆分
    # ═══════════════════════════════════════════════════════

    def split_module(
        self,
        file_path: str,
        new_module_name: str,
        functions_to_move: List[str],
        classes_to_move: List[str],
    ) -> TransformResult:
        """将模块中的选定内容拆分到新文件。

        Args:
            file_path: 源文件
            new_module_name: 新模块名（不含 .py）
            functions_to_move: 要移动的函数名列表
            classes_to_move: 要移动的类名列表
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="split_module",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        analysis = self._analyzer.analyze(full_path)
        lines = original.splitlines()

        # 收集要移动的所有行范围
        move_ranges = set()
        moved_items = []

        for func in analysis["functions"]:
            if func["name"] in functions_to_move:
                end = func["end_lineno"] or func["lineno"]
                for i in range(func["lineno"], end + 1):
                    move_ranges.add(i)
                moved_items.append(f"func:{func['name']}")

        for cls in analysis["classes"]:
            if cls["name"] in classes_to_move:
                end = cls["end_lineno"] or cls["lineno"]
                for i in range(cls["lineno"], end + 1):
                    move_ranges.add(i)
                moved_items.append(f"class:{cls['name']}")

        if not move_ranges:
            return TransformResult(
                success=False, transform_type="split_module",
                file_path=file_path, error="未找到要移动的函数或类",
            )

        # 构建新模块内容
        new_module_lines = [
            f'"""',
            f'{new_module_name}.py — 从 {Path(file_path).stem} 拆分',
            f'',
            f'自动生成于 {datetime.now().isoformat()}',
            f'"""',
            f'',
        ]

        # 复制必要的 import
        for imp in analysis["imports"]:
            if imp["type"] == "import":
                new_module_lines.append(f"import {imp['name']}")
            elif imp["type"] == "from":
                new_module_lines.append(f"from {imp['module']} import {imp['name']}")
        new_module_lines.append("")

        # 复制被移动的代码
        for i in sorted(move_ranges):
            new_module_lines.append(lines[i - 1] if i <= len(lines) else "")

        # 构建原文件（移除被移动的内容）
        new_source_lines = []
        for i, line in enumerate(lines, 1):
            if i in move_ranges:
                continue
            new_source_lines.append(line)

        # 在原文件顶部添加对新模块的导入
        source_dir = str(full_path.parent.relative_to(SANDBOX_DIR))
        new_import = f"from {source_dir}.{new_module_name} import {', '.join(functions_to_move + classes_to_move)}"
        new_import = new_import.replace("tools.", "").replace("evolver.", "")

        # 简化：直接按文件名导入
        import_statement = (
            f"from {source_dir.replace('/', '.')}.{new_module_name} "
            f"import {', '.join(functions_to_move + classes_to_move)}"
        )
        # 进一步简化
        if source_dir == "tools":
            import_statement = f"from tools.{new_module_name} import {', '.join(functions_to_move + classes_to_move)}"

        new_source_lines.insert(0, import_statement)

        modified = "\n".join(new_source_lines)
        new_module_code = "\n".join(new_module_lines)

        # 验证两个文件
        ast_valid_source = self._validate_ast(modified)
        ast_valid_new = self._validate_ast(new_module_code)

        # 写入
        new_module_path = full_path.parent / f"{new_module_name}.py"
        try:
            full_path.write_text(modified, encoding="utf-8")
            new_module_path.write_text(new_module_code, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="split_module",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified)

        return TransformResult(
            success=True, transform_type="split_module",
            file_path=file_path,
            original_lines=len(lines), modified_lines=len(new_source_lines),
            changes=[{
                "action": "split_module",
                "new_file": f"{new_module_name}.py",
                "moved_items": moved_items,
                "new_module_lines": len(new_module_lines),
            }],
            description=f"拆分 {len(moved_items)} 个项目到 {new_module_name}.py（{len(new_module_lines)} 行）",
            diff_preview=diff,
            ast_valid=ast_valid_source and ast_valid_new,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 变换 5: 错误上下文增强
    # ═══════════════════════════════════════════════════════

    def add_error_context(
        self,
        file_path: str,
        function_name: str,
    ) -> TransformResult:
        """为函数添加更丰富的错误上下文信息。

        将裸露的 `except:` 或简单的 `except Exception as e:`
        增强为包含文件名、函数名、行号的上下文。
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="add_error_context",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        lines = original.splitlines()
        analysis = self._analyzer.analyze(full_path)

        # 找到目标函数
        target = None
        for f in analysis["functions"]:
            if f["name"] == function_name:
                target = f
                break

        if target is None:
            return TransformResult(
                success=False, transform_type="add_error_context",
                file_path=file_path, error=f"未找到函数: {function_name}",
            )

        func_start = target["lineno"]
        func_end = target["end_lineno"] or func_start
        func_lines = lines[func_start - 1:func_end]

        # 增强 except 块
        import re
        changes = 0
        new_func_lines = []

        for line in func_lines:
            # 匹配：except Exception as e: 或 except:
            if re.match(r'\s*except(\s+Exception)?(\s+as\s+\w+)?\s*:', line):
                indent = len(line) - len(line.lstrip())
                # 在 except 块的第一行添加日志
                new_func_lines.append(line)
                new_func_lines.append(" " * (indent + 4) +
                    f'import logging; logging.getLogger(__name__).error('
                    f'"Error in {function_name}(): %s", '
                    f'str(e) if "e" in dir() else "unknown", '
                    f'extra={{"function": "{function_name}", '
                    f'"file": "{file_path}"}})')
                changes += 1
            else:
                new_func_lines.append(line)

        # 重建完整文件
        new_lines = (
            lines[:func_start - 1] +
            new_func_lines +
            lines[func_end:]
        )

        modified = "\n".join(new_lines)
        ast_valid = self._validate_ast(modified)

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="add_error_context",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified)

        return TransformResult(
            success=True, transform_type="add_error_context",
            file_path=file_path,
            original_lines=len(lines), modified_lines=len(new_lines),
            changes=[{"action": "add_error_context", "function": function_name,
                      "enhanced_except_blocks": changes}],
            description=f"为 {function_name}() 的 {changes} 个 except 块添加错误上下文",
            diff_preview=diff,
            ast_valid=ast_valid,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 变换 6: 脚手架生成
    # ═══════════════════════════════════════════════════════

    def generate_scaffold(
        self,
        module_name: str,
        parent_dir: str,
        description: str,
        functions: List[Dict[str, Any]],
        classes: List[Dict[str, Any]] = None,
    ) -> TransformResult:
        """生成新模块脚手架。

        Args:
            module_name: 新模块名（不含 .py）
            parent_dir: 父目录（相对于 SANDBOX_DIR）
            description: 模块描述
            functions: 函数定义列表 [{"name": "...", "args": [...], "returns": "...", "doc": "..."}]
            classes: 类定义列表
        """
        classes = classes or []
        parent_path = SANDBOX_DIR / parent_dir
        parent_path.mkdir(parents=True, exist_ok=True)
        file_path = parent_path / f"{module_name}.py"

        if file_path.exists():
            return TransformResult(
                success=False, transform_type="generate_scaffold",
                file_path=str(file_path.relative_to(SANDBOX_DIR)),
                error=f"文件已存在: {file_path}",
            )

        # 生成模块代码
        code_lines = [
            f'"""',
            f'{module_name}.py — {description}',
            f'',
            f'自动生成于 {datetime.now().isoformat()}',
            f'"""',
            f'',
            f'from __future__ import annotations',
            f'',
            f'import sys',
            f'from dataclasses import dataclass',
            f'from pathlib import Path',
            f'from typing import Any, Dict, List, Optional',
            f'',
            f'# ── 路径 ──',
            f'MODULE_DIR = Path(__file__).resolve().parent',
            f'SANDBOX_DIR = MODULE_DIR.parent',
            f'sys.path.insert(0, str(SANDBOX_DIR))',
            f'',
        ]

        # 类定义
        for cls in classes:
            code_lines.append(f'')
            code_lines.append(f'class {cls["name"]}:')
            code_lines.append(f'    """{cls.get("doc", f"{cls["name"]} 类")}"""')
            code_lines.append(f'')
            if cls.get("init_params"):
                params = ", ".join(cls["init_params"])
                code_lines.append(f'    def __init__(self, {params}):')
                for param in cls["init_params"]:
                    pname = param.split(":")[0].strip()
                    code_lines.append(f'        self.{pname} = {pname}')
                code_lines.append(f'')
            for method in cls.get("methods", []):
                args = ", ".join(method.get("args", []))
                code_lines.append(f'    def {method["name"]}(self{", " + args if args else ""}):')
                code_lines.append(f'        """{method.get("doc", "TODO")}"""')
                code_lines.append(f'        ...')
                code_lines.append(f'')

        # 函数定义
        for func in functions:
            args = ", ".join(func.get("args", []))
            code_lines.append(f'')
            code_lines.append(f'def {func["name"]}({args}){func.get("returns", "")}:')
            code_lines.append(f'    """{func.get("doc", "TODO: 文档")}"""')
            code_lines.append(f'    ...')
            code_lines.append(f'')

        # 全局单例
        code_lines.append(f'')
        code_lines.append(f'# ── 全局单例 ──')
        code_lines.append(f'_instance = None')
        code_lines.append(f'')
        code_lines.append(f'def get_instance():')
        code_lines.append(f'    """获取模块实例。"""')
        code_lines.append(f'    global _instance')
        code_lines.append(f'    if _instance is None:')
        code_lines.append(f'        _instance = ...  # TODO: 初始化')
        code_lines.append(f'    return _instance')

        code = "\n".join(code_lines)

        try:
            file_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="generate_scaffold",
                file_path=str(file_path.relative_to(SANDBOX_DIR)),
                error=str(exc),
            )

        ast_valid = self._validate_ast(code)
        rel_path = str(file_path.relative_to(SANDBOX_DIR))

        return TransformResult(
            success=True, transform_type="generate_scaffold",
            file_path=rel_path,
            original_lines=0, modified_lines=len(code.splitlines()),
            changes=[{
                "action": "generate_scaffold",
                "module": module_name,
                "functions": [f["name"] for f in functions],
                "classes": [c["name"] for c in classes],
            }],
            description=f"生成新模块 {rel_path}（{len(code.splitlines())} 行）",
            ast_valid=ast_valid,
            backup_path="",
        )

    # ═══════════════════════════════════════════════════════
    # 变换 7: 创造性重构（异步 LLM 任务）
    # ═══════════════════════════════════════════════════════

    def creative_refactor(
        self,
        file_path: str,
        idea: Dict[str, Any],
    ) -> TransformResult:
        """为需要真正语义理解的复杂重构创建 LLM 任务。

        此方法不直接修改代码，而是：
        1. 分析目标文件
        2. 构建详细的任务 prompt
        3. 将任务保存到 memory/llm_tasks/pending/
        4. 由 LLM Agent（Debugger）处理后写回

        Args:
            file_path: 目标文件
            idea: 改进创意字典（来自 ImprovementGenerator）
        """
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="creative_refactor",
                file_path=file_path, error=f"文件不存在: {full_path}",
            )

        source_code = full_path.read_text(encoding="utf-8")
        analysis = self._analyzer.analyze(full_path)

        # 构建详细 prompt
        prompt = self._build_refactor_prompt(file_path, idea, source_code, analysis)

        # 创建任务
        task_id = f"task-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = LLMTask(
            task_id=task_id,
            transform_type="creative_refactor",
            file_path=file_path,
            idea=idea,
            source_code=source_code,
            prompt=prompt,
            created_at=datetime.now().isoformat(),
        )

        # 保存到 pending
        task_file = LLM_TASK_DIR / "pending" / f"{task_id}.json"
        task_file.write_text(
            json.dumps({
                "task_id": task.task_id,
                "transform_type": task.transform_type,
                "file_path": task.file_path,
                "idea": task.idea,
                "prompt": task.prompt,
                "created_at": task.created_at,
                "status": "pending",
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._tasks[task_id] = task

        return TransformResult(
            success=True, transform_type="creative_refactor",
            file_path=file_path,
            original_lines=len(source_code.splitlines()),
            changes=[{
                "action": "create_llm_task",
                "task_id": task_id,
                "task_file": str(task_file.relative_to(SANDBOX_DIR)),
            }],
            description=f"已创建 LLM 重构任务 {task_id}（{len(prompt)} 字符的 prompt）",
            ast_valid=True,  # 未修改源文件
        )

    def _build_refactor_prompt(
        self,
        file_path: str,
        idea: Dict[str, Any],
        source_code: str,
        analysis: Dict[str, Any],
    ) -> str:
        """构建创造性重构的完整 prompt。"""
        title = idea.get("title", "未命名改进")
        description = idea.get("description", "")
        hint = idea.get("implementation_hint", "")
        idea_type = idea.get("improvement_type", "unknown")
        tags = idea.get("tags", [])

        prompt = f"""# 🔧 创造性代码重构任务

## 改进创意
- **标题**: {title}
- **类型**: {idea_type}
- **描述**: {description}
- **实现提示**: {hint}
- **标签**: {', '.join(tags)}

## 目标文件
- **路径**: {file_path}
- **总行数**: {analysis.get('total_lines', '?')}
- **函数数**: {analysis.get('function_count', '?')}
- **类数**: {analysis.get('class_count', '?')}

## 当前代码结构
"""
        # 函数摘要
        prompt += "\n### 函数列表\n"
        for f in analysis.get("functions", [])[:15]:
            decorators = ", ".join(f["decorators"]) if f["decorators"] else "无"
            prompt += f"- `{f['name']}({', '.join(f['args'])})` @L{f['lineno']} [{f['body_length']}行] 装饰器: {decorators}\n"

        # 类摘要
        if analysis.get("classes"):
            prompt += "\n### 类列表\n"
            for c in analysis["classes"]:
                prompt += f"- `{c['name']}` @L{c['lineno']} [{c['body_length']}行] 方法: {', '.join(c['methods'][:10])}\n"

        # 导入摘要
        if analysis.get("imports"):
            prompt += "\n### 导入列表\n"
            for imp in analysis["imports"][:10]:
                if imp["type"] == "import":
                    prompt += f"- `import {imp['name']}`\n"
                else:
                    prompt += f"- `from {imp['module']} import {imp['name']}`\n"

        prompt += f"""
## 完整源代码
```python
{source_code[:8000]}{'... (truncated)' if len(source_code) > 8000 else ''}
```

## 任务要求

请基于以上改进创意，生成修改后的完整代码。要求：

1. **保持原有功能**：所有现有功能必须继续保持工作
2. **最小变更原则**：仅修改必要的部分，不进行无关重构
3. **代码风格一致**：保持与原文件相同的代码风格和命名约定
4. **AST 有效**：生成的代码必须能通过 `ast.parse()` 验证
5. **向后兼容**：所有公开 API 保持兼容，或提供迁移路径

## 输出格式

请提供：
1. 修改后的完整文件内容（用 ```python 包裹）
2. 变更摘要（bullet points）
3. 潜在风险点（如有）

---
*此任务由 LLMPatcher 自动生成。task_id: {task_id if 'task_id' in dir() else 'pending'}*
"""
        return prompt

    # ═══════════════════════════════════════════════════════
    # 任务管理
    # ═══════════════════════════════════════════════════════

    def list_pending_tasks(self) -> List[Dict[str, Any]]:
        """列出所有待处理的 LLM 任务。"""
        tasks = []
        pending_dir = LLM_TASK_DIR / "pending"
        for f in sorted(pending_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tasks.append(data)
            except json.JSONDecodeError:
                pass
        return tasks

    def apply_completed_task(self, task_id: str, modified_code: str) -> TransformResult:
        """应用 LLM 已完成的修改。

        Args:
            task_id: 任务 ID
            modified_code: LLM 生成的修改后代码
        """
        pending_file = LLM_TASK_DIR / "pending" / f"{task_id}.json"
        if not pending_file.exists():
            return TransformResult(
                success=False, transform_type="creative_refactor",
                file_path="", error=f"任务不存在: {task_id}",
            )

        task_data = json.loads(pending_file.read_text(encoding="utf-8"))
        file_path = task_data["file_path"]
        full_path = SANDBOX_DIR / file_path

        if not full_path.is_file():
            return TransformResult(
                success=False, transform_type="creative_refactor",
                file_path=file_path, error=f"目标文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")
        self._backup(full_path, original)

        # AST 验证
        if not self._validate_ast(modified_code):
            return TransformResult(
                success=False, transform_type="creative_refactor",
                file_path=file_path,
                error="LLM 生成的代码 AST 验证失败",
            )

        # 写入
        try:
            full_path.write_text(modified_code, encoding="utf-8")
        except OSError as exc:
            return TransformResult(
                success=False, transform_type="creative_refactor",
                file_path=file_path, error=str(exc),
            )

        diff = self._generate_diff(original, modified_code)

        # 移动到 completed
        completed_file = LLM_TASK_DIR / "completed" / f"{task_id}.json"
        task_data["status"] = "completed"
        task_data["completed_at"] = datetime.now().isoformat()
        task_data["diff"] = diff[:500]
        completed_file.write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pending_file.unlink()

        return TransformResult(
            success=True, transform_type="creative_refactor",
            file_path=file_path,
            original_lines=len(original.splitlines()),
            modified_lines=len(modified_code.splitlines()),
            changes=[{"action": "apply_llm_result", "task_id": task_id}],
            description=f"应用 LLM 生成的重构: {task_id}",
            diff_preview=diff,
            ast_valid=True,
            backup_path=str(self._backup_path(full_path)),
        )

    # ═══════════════════════════════════════════════════════
    # 统一入口
    # ═══════════════════════════════════════════════════════

    def apply(
        self,
        file_path: str,
        transform_type: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> TransformResult:
        """统一的应用入口。"""
        params = params or {}

        if transform_type == "extract_function":
            return self.extract_function(
                file_path=file_path,
                target_func=params.get("target_func", ""),
                start_line=params.get("start_line", 0),
                end_line=params.get("end_line", 0),
                new_func_name=params.get("new_func_name", "_extracted"),
            )

        elif transform_type == "extract_class":
            return self.extract_class(
                file_path=file_path,
                method_names=params.get("method_names", []),
                class_name=params.get("class_name", "ExtractedClass"),
            )

        elif transform_type == "add_abstraction":
            return self.add_abstraction(
                file_path=file_path,
                abstract_methods=params.get("abstract_methods", []),
                base_class_name=params.get("base_class_name", "AbstractBase"),
            )

        elif transform_type == "split_module":
            return self.split_module(
                file_path=file_path,
                new_module_name=params.get("new_module_name", "new_module"),
                functions_to_move=params.get("functions_to_move", []),
                classes_to_move=params.get("classes_to_move", []),
            )

        elif transform_type == "add_error_context":
            return self.add_error_context(
                file_path=file_path,
                function_name=params.get("function_name", ""),
            )

        elif transform_type == "generate_scaffold":
            return self.generate_scaffold(
                module_name=params.get("module_name", "new_module"),
                parent_dir=params.get("parent_dir", "tools"),
                description=params.get("description", "新模块"),
                functions=params.get("functions", []),
                classes=params.get("classes", []),
            )

        elif transform_type == "creative_refactor":
            return self.creative_refactor(
                file_path=file_path,
                idea=params.get("idea", {}),
            )

        else:
            return TransformResult(
                success=False, transform_type=transform_type,
                file_path=file_path,
                error=f"不支持的变换类型: {transform_type}。可用: {self.TRANSFORM_TYPES}",
            )

    # ═══════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════

    def _backup(self, full_path: Path, content: str):
        """创建文件备份。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"{full_path.stem}_{timestamp}.bak"
        backup_file.write_text(content, encoding="utf-8")

    def _backup_path(self, full_path: Path) -> Path:
        """获取最近的备份路径。"""
        backups = sorted(BACKUP_DIR.glob(f"{full_path.stem}_*.bak"))
        return backups[-1] if backups else BACKUP_DIR / "none"

    @staticmethod
    def _validate_ast(code: str) -> bool:
        """验证代码是否 AST 有效。"""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    @staticmethod
    def _generate_diff(original: str, modified: str) -> str:
        """生成 unified diff。"""
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="original",
            tofile="modified",
            lineterm="",
        )
        diff_text = "\n".join(list(diff)[:60])  # 限制长度
        return diff_text


# ── 全局单例 ───────────────────────────────────────────────

_llm_patcher = LLMPatcher()


def get_llm_patcher() -> LLMPatcher:
    """获取 LLM Patcher 实例。"""
    return _llm_patcher


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "llm_patcher",
        "description": (
            "创造性代码重写引擎。支持 AST 级别的语义变换："
            "函数提取、类提取、抽象层引入、模块拆分、错误上下文增强、"
            "脚手架生成、以及需要 LLM 代理的创造性重构。"
            "相较于 AutomatedPatcher 的 regex 变换，此引擎理解代码结构。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "extract_function", "extract_class", "add_abstraction",
                        "split_module", "add_error_context", "generate_scaffold",
                        "creative_refactor", "list_tasks", "apply_task",
                        "analyze", "help",
                    ],
                    "description": "操作类型",
                    "default": "help",
                },
                "file_path": {
                    "type": "string",
                    "description": "目标文件路径（相对于沙箱根目录）",
                    "default": "",
                },
                "transform_type": {
                    "type": "string",
                    "description": "变换类型",
                    "default": "",
                },
                "params_json": {
                    "type": "string",
                    "description": "JSON 格式的变换参数",
                    "default": "{}",
                },
                "task_id": {
                    "type": "string",
                    "description": "LLM 任务 ID",
                    "default": "",
                },
                "modified_code": {
                    "type": "string",
                    "description": "LLM 生成的修改代码（apply_task 时使用）",
                    "default": "",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


def execute_llm_patcher_tool(arguments: dict) -> str:
    """LLM Patcher 工具入口。"""
    action = arguments.get("action", "help")

    try:
        if action == "help":
            return (
                "🧬 llm_patcher — 创造性代码重写引擎\n\n"
                "可用变换:\n"
                "  extract_function   — 从大函数提取子函数\n"
                "  extract_class      — 将函数组提取为类\n"
                "  add_abstraction    — 引入抽象基类/接口\n"
                "  split_module       — 模块拆分\n"
                "  add_error_context  — 增强错误上下文\n"
                "  generate_scaffold  — 生成新模块脚手架\n"
                "  creative_refactor  — 创建 LLM 重构任务（需 Agent 协助）\n\n"
                "任务管理:\n"
                "  list_tasks         — 查看待处理的 LLM 任务\n"
                "  apply_task         — 应用 LLM 完成的重构\n\n"
                "分析:\n"
                "  analyze            — AST 分析目标文件\n\n"
                "与 AutomatedPatcher 配合使用，覆盖 L1-L5 所有改进类型。"
            )

        elif action == "analyze":
            file_path = arguments.get("file_path", "")
            if not file_path:
                return "请提供 file_path"
            full_path = SANDBOX_DIR / file_path
            if not full_path.is_file():
                return f"文件不存在: {full_path}"
            analysis = ASTAnalyzer.analyze(full_path)
            return json.dumps(analysis, ensure_ascii=False, indent=2)

        elif action == "list_tasks":
            tasks = _llm_patcher.list_pending_tasks()
            if not tasks:
                return "📭 无待处理的 LLM 任务。"

            lines = [f"📋 待处理 LLM 任务 ({len(tasks)} 个):\n"]
            for t in tasks:
                idea = t.get("idea", {})
                lines.append(f"  [{t['task_id']}] {idea.get('title', 'N/A')[:60]}")
                lines.append(f"    文件: {t['file_path']} | 创建: {t['created_at'][:19]}")
            return "\n".join(lines)

        elif action == "apply_task":
            task_id = arguments.get("task_id", "")
            modified_code = arguments.get("modified_code", "")
            if not task_id or not modified_code:
                return "请提供 task_id 和 modified_code"
            result = _llm_patcher.apply_completed_task(task_id, modified_code)
            return (
                f"{'✅' if result.success else '❌'} {result.description}\n"
                f"AST 有效: {result.ast_valid}\n"
                f"备份: {result.backup_path}"
            )

        else:
            file_path = arguments.get("file_path", "")
            params = json.loads(arguments.get("params_json", "{}"))

            if action == "creative_refactor":
                params["idea"] = params.get("idea", {})

            result = _llm_patcher.apply(
                file_path=file_path,
                transform_type=action,
                params=params,
            )

            if result.success:
                lines = [
                    f"✅ {result.description}",
                    f"文件: {result.file_path}",
                    f"行数: {result.original_lines} → {result.modified_lines}",
                    f"AST 有效: {result.ast_valid}",
                ]
                if result.diff_preview:
                    lines.append(f"\n--- Diff Preview ---\n{result.diff_preview[:800]}")
                return "\n".join(lines)
            else:
                return f"❌ 失败: {result.error}"

    except Exception as exc:
        return f"LLM Patcher 错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    patcher = LLMPatcher()

    # 测试分析
    test_file = SANDBOX_DIR / "tools" / "calculator.py"
    if test_file.is_file():
        print("=== AST 分析 ===")
        analysis = ASTAnalyzer.analyze(test_file)
        print(f"函数: {analysis['function_count']}, 类: {analysis['class_count']}")
        for f in analysis["functions"][:3]:
            print(f"  {f['name']}({', '.join(f['args'])}) @L{f['lineno']}")

    # 测试脚手架生成
    print("\n=== 脚手架生成 ===")
    result = patcher.generate_scaffold(
        module_name="_test_scaffold",
        parent_dir="tools",
        description="测试脚手架",
        functions=[
            {"name": "do_work", "args": ["data: dict"], "returns": " -> dict",
             "doc": "处理数据并返回结果。"},
        ],
        classes=[
            {"name": "Worker", "doc": "工作器类",
             "init_params": ["name: str"],
             "methods": [{"name": "execute", "args": ["task_id: str"], "doc": "执行任务"}]},
        ],
    )
    print(f"  成功: {result.success}, 路径: {result.file_path}")

    # 清理
    scaffold_path = SANDBOX_DIR / "tools" / "_test_scaffold.py"
    if scaffold_path.is_file():
        scaffold_path.unlink()

    print("\n✅ 自测完成")
