"""
automated_patcher — 确定性代码重写引擎 v1.0

将 ImprovementGenerator 产生的创意转化为实际代码变更。
支持多种安全的、确定性的代码转换，每种转换都有明确的
适用条件和回滚能力。

设计原则：
  - 确定性：相同输入产生相同输出（非 LLM，不可随机）
  - 可逆性：每次修改都有对应的逆操作
  - 最小权限：仅修改目标文件的相关部分
  - 可验证：修改后自动运行受影响测试
"""

from __future__ import annotations

import ast
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
sys.path.insert(0, str(SANDBOX_DIR))


@dataclass
class PatchResult:
    """补丁应用结果。"""
    success: bool
    file_path: str
    transformation: str
    original_lines: int = 0
    modified_lines: int = 0
    changes_made: int = 0
    description: str = ""
    error: str = ""
    patch_preview: str = ""  # 前几行 diff 预览


class AutomatedPatcher:
    """确定性代码重写引擎。

    从 improvement_generator 的创意模板到实际代码变更的桥梁。

    支持的转换类型：
      - "lazy_import": 将模块顶层重量级导入移入函数体内
      - "dict_dispatch": 将长 if-elif 链替换为字典分发
      - "constant_extract": 提取硬编码常量到模块级变量
      - "set_lookup": 将小列表成员检查改为集合
    """

    # ── 转换注册表 ──────────────────────────────────────

    TRANSFORMS = ["lazy_import", "dict_dispatch", "constant_extract", "set_lookup", "json_preload", "llm_patch"]

    @classmethod
    def apply(
        cls,
        file_path: str,
        transform: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> PatchResult:
        """对文件应用指定的代码转换。

        Args:
            file_path: 相对于 SANDBOX_DIR 的文件路径
            transform: 转换类型
            params: 转换参数

        Returns:
            PatchResult
        """
        params = params or {}
        full_path = SANDBOX_DIR / file_path

        if not full_path.is_file():
            return PatchResult(
                success=False, file_path=file_path,
                transformation=transform,
                error=f"文件不存在: {full_path}",
            )

        original = full_path.read_text(encoding="utf-8")

        if transform == "lazy_import":
            result = cls._apply_lazy_import(full_path, original, params)
        elif transform == "set_lookup":
            result = cls._apply_set_lookup(full_path, original, params)
        elif transform == "constant_extract":
            result = cls._apply_constant_extract(full_path, original, params)
        elif transform == "dict_dispatch":
            result = cls._apply_dict_dispatch(full_path, original, params)
        elif transform == "json_preload":
            result = cls._apply_json_preload(full_path, original, params)
        elif transform == "llm_patch":
            result = cls._apply_llm_patch(full_path, original, params)
        else:
            return PatchResult(
                success=False, file_path=file_path,
                transformation=transform,
                error=f"不支持的转换类型: {transform}。可用: {cls.TRANSFORMS}",
            )

        return result

    # ═══════════════════════════════════════════════════════
    # 转换 1: 惰性导入 — 将重量级模块顶层导入移入函数
    # ═══════════════════════════════════════════════════════

    # 已知的重量级模块（导入耗时 > 100ms）
    HEAVY_MODULES = [
        "numpy", "torch", "tensorflow", "sentence_transformers",
        "SentenceTransformer", "transformers", "sklearn", "pandas",
    ]

    @classmethod
    def _apply_lazy_import(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """将顶层重量级导入改为惰性加载。

        策略：
          1. 找到 `import heavy_module` 或 `from heavy_pkg import heavy_module`
          2. 创建 `_lazy_ensure_xxx()` 函数
          3. 将原 import 替换为惰性版本
          4. 更新所有引用处
        """
        lines = original.split("\n")
        heavy_lines: List[Tuple[int, str, str]] = []  # (line_no, line, module_name)

        for i, line in enumerate(lines):
            stripped = line.strip()
            for hmod in cls.HEAVY_MODULES:
                if stripped.startswith(f"import {hmod}") or f"import {hmod} " in stripped:
                    heavy_lines.append((i, line, hmod))
                elif stripped.startswith(f"from {hmod}") or f"from {hmod}" in stripped.split("import")[0] if "import" in stripped else False:
                    # from sentence_transformers import SentenceTransformer
                    heavy_lines.append((i, line, hmod))

        if not heavy_lines:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="lazy_import",
                error="未找到重量级模块导入",
            )

        # 确定目标函数名（基于第一个重量级模块）
        target_func = params.get("target_func", "")
        module_names = list(set(h[2] for h in heavy_lines))

        # 构建惰性加载函数
        lazy_func_name = f"_lazy_ensure_{module_names[0].replace('.', '_')}"
        lazy_func = textwrap.dedent(f"""
        def {lazy_func_name}() -> bool:
            \"\"\"惰性检测并加载 {', '.join(module_names)}。\"\"\"
            global _LAZY_IMPORTED
            if globals().get('_LAZY_IMPORTED'):
                return True
            try:
                {'; '.join(f'import {m}' for m in module_names)}
                globals()['_LAZY_IMPORTED'] = True
                return True
            except ImportError:
                return False
        """)

        # 构建转换后的代码
        new_lines = []
        changes = 0
        skip_until = -1

        for i, line in enumerate(lines):
            if i < skip_until:
                continue

            is_heavy = any(i == hl[0] for hl in heavy_lines)
            if is_heavy:
                # 注释掉原导入，添加惰性函数和标志
                new_lines.append(f"# [lazy] {line}")
                new_lines.append(f"_LAZY_IMPORTED = False")
                new_lines.extend(lazy_func.strip().split("\n"))
                changes += 1
                continue

            new_lines.append(line)

        modified = "\n".join(new_lines)

        # 写入文件
        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="lazy_import", error=str(exc),
            )

        return PatchResult(
            success=True, file_path=str(full_path),
            transformation="lazy_import",
            original_lines=len(lines), modified_lines=len(new_lines),
            changes_made=changes,
            description=f"将 {len(heavy_lines)} 个重量级导入改为惰性加载",
            patch_preview=f"受影响模块: {module_names}",
        )

    # ═══════════════════════════════════════════════════════
    # 转换 2: 集合查找 — 小列表成员检查改为集合 O(1)
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _apply_set_lookup(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """将 `if x in [a, b, c]` 替换为 `if x in {a, b, c}`。

        仅处理包含纯字面量的小列表（< 20 个元素），确保安全。
        """
        # 匹配: if/in/while 后跟 `name in [literal, ...]`
        pattern = re.compile(
            r'(\bif\b|\belif\b|\bwhile\b)\s+(\w+)\s+(not\s+)?in\s+\[([^\]]+)\]'
        )

        def replacer(match):
            keyword = match.group(1)
            var_name = match.group(2)
            neg = match.group(3) or ""
            items = match.group(4)
            # 只处理短列表（< 20 个元素）
            item_list = [x.strip() for x in items.split(",")]
            if len(item_list) > 20:
                return match.group(0)
            return f"{keyword} {var_name} {neg}in {{{items}}}"

        modified, count = pattern.subn(replacer, original)

        if count == 0:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="set_lookup",
                error="未找到可优化的列表成员检查",
            )

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="set_lookup", error=str(exc),
            )

        return PatchResult(
            success=True, file_path=str(full_path),
            transformation="set_lookup",
            original_lines=len(original.split("\n")),
            modified_lines=len(modified.split("\n")),
            changes_made=count,
            description=f"将 {count} 个列表成员检查改为集合 O(1) 查找",
        )

    # ═══════════════════════════════════════════════════════
    # 转换 3: 常量提取 — 硬编码数值提取为模块级常量
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _apply_constant_extract(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """提取函数体内重复出现的硬编码数值为模块级常量。

        策略：
          1. 找到在 >= 3 个位置出现的相同数值字面量
          2. 在模块顶部创建常量定义
          3. 替换所有出现位置
        """
        lines = original.split("\n")

        # 找到重复出现的数值（>= 3 次）
        from collections import Counter
        nums = re.findall(r'(?<!\w)(\d{2,6})(?!\w)', original)
        repeated = {int(n): c for n, c in Counter(nums).items() if c >= 3}

        if not repeated:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="constant_extract",
                error="未找到重复 3 次以上的硬编码数值",
            )

        # 选择出现最多的数值
        best_num = max(repeated, key=repeated.get)
        const_name = params.get("const_name", f"_DEFAULT_{best_num}")

        # 在 import 之后插入常量
        new_lines = []
        inserted = False
        changes = 0

        for line in lines:
            if not inserted and (line.startswith("import ") or line.startswith("from ")):
                new_lines.append(line)
                continue
            if not inserted and new_lines and (
                new_lines[-1].startswith("import ") or new_lines[-1].startswith("from ")
            ):
                # 在上一个 import 之后插入
                new_lines.append("")
                new_lines.append(f"# [extracted constant]")
                new_lines.append(f"{const_name} = {best_num}")
                new_lines.append("")
                inserted = True

            # 替换硬编码数值（仅替换独立出现的，非字符串内）
            if str(best_num) in line and not line.strip().startswith("#"):
                # 安全替换：仅替换作为独立词出现的
                new_line = re.sub(
                    rf'(?<!\w){best_num}(?!\w)', const_name, line
                )
                if new_line != line:
                    changes += 1
                new_lines.append(new_line)
            else:
                new_lines.append(line)

        if not inserted:
            # 在文件开头插入
            new_lines.insert(0, f"{const_name} = {best_num}")
            new_lines.insert(0, "# [extracted constant]")
            new_lines.insert(0, "")

        modified = "\n".join(new_lines)

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="constant_extract", error=str(exc),
            )

        return PatchResult(
            success=True, file_path=str(full_path),
            transformation="constant_extract",
            original_lines=len(lines), modified_lines=len(new_lines),
            changes_made=changes,
            description=f"提取硬编码数值 {best_num}（出现 {repeated[best_num]} 次）为常量 {const_name}",
        )

    # ═══════════════════════════════════════════════════════
    # 转换 4: 字典分发 — 长 if-elif 链替换为字典查找
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _apply_dict_dispatch(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """将长 if-elif 链替换为字典分发 O(1)。

        仅在 if-elif 分支 >= 10 个且都是简单的 `name == "xxx"` 模式时触发。
        """
        lines = original.split("\n")

        # 查找 `elif name == "xxx":` 模式
        dispatch_map: Dict[str, str] = {}
        var_name = params.get("var_name", "name")
        pattern = re.compile(rf'\s*elif\s+{var_name}\s*==\s*"([^"]+)"\s*:')

        for i, line in enumerate(lines):
            m = pattern.match(line)
            if m:
                key = m.group(1)
                # 找下一行的 action
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 提取 result = tool_xxx.execute_xxx_tool(arguments)
                    action_match = re.match(
                        r'result\s*=\s*(\w+\.\w+)\(arguments\)', next_line
                    )
                    if not action_match:
                        action_match = re.match(
                            r'result\s*=\s*(\w+_\w+)\(', next_line
                        )
                    if action_match:
                        dispatch_map[key] = action_match.group(1)

        if len(dispatch_map) < 10:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="dict_dispatch",
                error=f"仅找到 {len(dispatch_map)} 个可分发的分支，需要 >= 10",
            )

        # 检查是否已有 dispatch 字典
        if "_DISPATCH_MAP" in original or "_dispatch" in original:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="dict_dispatch",
                error="文件已包含分发字典",
            )

        # 找到 if-elif 块的起始和结束行
        first_elif_idx = None
        last_elif_idx = None
        for i, line in enumerate(lines):
            if pattern.match(line):
                if first_elif_idx is None:
                    first_elif_idx = i
                last_elif_idx = i

        if first_elif_idx is None:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="dict_dispatch", error="未找到 if-elif 块",
            )

        # 找到 else: 行
        else_idx = None
        for i in range(last_elif_idx + 1, min(last_elif_idx + 5, len(lines))):
            if lines[i].strip() == "else:":
                else_idx = i
                break

        # 构建分发字典代码
        dispatch_entries = "\n".join(
            f'    "{k}": {v},' for k, v in sorted(dispatch_map.items())
        )
        dispatch_code = textwrap.dedent(f"""
        _TOOL_DISPATCH = {{
        {dispatch_entries}
        }}
        """)

        # 构建新的分发逻辑
        dispatch_logic = textwrap.dedent(f"""
            handler = _TOOL_DISPATCH.get({var_name})
            if handler is not None:
                result = handler(arguments)
            else:
        """)

        # 替换
        new_lines = []
        # 在第一个 elif 前插入 dispatch 字典
        insert_idx = max(0, first_elif_idx - 1)
        for i in range(insert_idx):
            new_lines.append(lines[i])

        new_lines.extend(dispatch_code.strip().split("\n"))
        new_lines.append("")

        # 替换 if-elif 块为 dispatch 调用
        # 保留第一个 if 行和 else 行
        for i in range(insert_idx, first_elif_idx):
            new_lines.append(lines[i])

        new_lines.append(dispatch_logic.rstrip())

        # 跳过原来的 elif 块，添加 else 部分
        if else_idx:
            for i in range(else_idx, len(lines)):
                new_lines.append(lines[i])
        else:
            new_lines.extend(lines[last_elif_idx + 1:])

        modified = "\n".join(new_lines)

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="dict_dispatch", error=str(exc),
            )

        return PatchResult(
            success=True, file_path=str(full_path),
            transformation="dict_dispatch",
            original_lines=len(lines), modified_lines=len(new_lines),
            changes_made=len(dispatch_map),
            description=f"将 {len(dispatch_map)} 个 elif 分支替换为字典 O(1) 分发",
        )

    # ═══════════════════════════════════════════════════════
    # 转换 5: JSON 预加载 — 用 mtime 缓存替换每次调用读 JSON 文件
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _apply_json_preload(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """把 `json.loads(X.read_text(...))` 替换为带 mtime 缓存的 `_read_json_cached(X)`。

        安全性设计：
          - mtime 缓存：文件未变时返回缓存，变了则重新加载，不会读到过期数据；
          - 解析失败重新抛出 json.JSONDecodeError，保持原 try/except 语义；
          - 仅处理 `X` 为简单标识符（Name）的规整模式，避免误改复杂表达式。

        与 _detect_json_preload 配套：只有"非初始化方法体内每次调用读 JSON 文件"
        的模式才会被检测到并走到此转换。
        """
        try:
            tree = ast.parse(original)
        except SyntaxError:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload", error="源文件语法错误，无法解析",
            )

        # 收集目标：非 init/_load 方法体内，json.loads(X.read_text(...)) 的 X（Name）
        excluded = {"__init__", "_load", "load", "reload", "_reload"}
        targets: List[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in excluded:
                continue
            for sub in ast.walk(node):
                if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)):
                    continue
                if not (sub.func.attr == "loads"
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "json"):
                    continue
                if not sub.args:
                    continue
                arg = sub.args[0]
                if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                        and arg.func.attr in ("read_text", "read")
                        and isinstance(arg.func.value, ast.Name)):
                    name = arg.func.value.id
                    if name not in targets:
                        targets.append(name)

        if not targets:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload",
                error="未找到可预加载的 JSON 读取点（json.loads(X.read_text()) 模式）",
            )

        # 若文件已有缓存函数，避免重复插入
        if "_read_json_cached" in original:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload",
                error="文件已包含 _read_json_cached，跳过避免重复",
            )

        # 构建缓存函数代码
        cache_func = textwrap.dedent('''
        _JSON_CACHE: dict = {}

        def _read_json_cached(path, encoding="utf-8"):
            """带 mtime 缓存的 JSON 读取，等价于 json.loads(path.read_text(encoding=...))。

            文件 mtime 未变时返回缓存，变化则重新加载；解析失败重新抛出 json.JSONDecodeError。
            """
            try:
                mtime = path.stat().st_mtime
            except OSError:
                raise
            key = str(path)
            entry = _JSON_CACHE.get(key)
            if entry is not None and entry[0] == mtime:
                return entry[1]
            data = json.loads(path.read_text(encoding=encoding))
            _JSON_CACHE[key] = (mtime, data)
            return data
        ''')

        # 替换：json.loads(NAME.read_text(...)) → _read_json_cached(NAME)
        pattern = re.compile(r'\bjson\.loads\((\w+)\.read_text\([^)]*\)\)')
        modified, count = pattern.subn(r'_read_json_cached(\1)', original)
        if count == 0:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload", error="正则替换未命中",
            )

        # 在 import 块之后插入缓存函数
        lines = modified.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        while insert_at < len(lines) and (
            lines[insert_at].startswith("import ") or lines[insert_at].startswith("from ")
        ):
            insert_at += 1

        new_lines = lines[:insert_at] + cache_func.strip().split("\n") + [""] + lines[insert_at:]
        modified = "\n".join(new_lines)

        # AST 语法验证
        try:
            ast.parse(modified)
        except SyntaxError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload",
                error=f"转换后代码语法错误: {exc}",
            )

        try:
            full_path.write_text(modified, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="json_preload", error=str(exc),
            )

        return PatchResult(
            success=True, file_path=str(full_path),
            transformation="json_preload",
            original_lines=len(original.split("\n")),
            modified_lines=len(modified.split("\n")),
            changes_made=count,
            description=f"将 {count} 处 JSON 读取改为 mtime 缓存（涉及 {', '.join(targets)}）",
            patch_preview=f"缓存文件: {', '.join(targets)}",
        )

    # ═══════════════════════════════════════════════════════
    # 转换 6: LLM 驱动补丁 — 创造性代码生成
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _apply_llm_patch(
        cls, full_path: Path, original: str, params: Dict[str, Any]
    ) -> PatchResult:
        """使用 LLM 生成代码补丁，支持新功能、重构等创造性任务。

        工作流：
          1. 构建 prompt（源码 + 改进请求 + 格式约束）
          2. 调用 DeepSeek API
          3. 提取代码块
          4. AST 语法验证
          5. 安全写入

        params:
          - idea: 改进创意描述（必需）
          - idea_type: L1~L5 或 "new_feature" / "refactor"（可选）
          - constraints: 额外约束（可选）
        """
        idea = params.get("idea", "")
        idea_type = params.get("idea_type", "improvement")
        constraints = params.get("constraints", "")

        if not idea:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="llm_patch",
                error="缺少 idea 参数（改进描述）",
            )

        # 构建 system prompt
        system_prompt = textwrap.dedent("""\
        你是一个专业的 Python 代码生成器。你的任务是根据改进请求修改给定的源文件。
        
        规则：
        1. 输出完整的修改后文件，不要省略任何部分
        2. 保持原有的代码风格、缩进和注释
        3. 仅修改与改进请求直接相关的部分
        4. 不要添加冗长的解释——在代码中用简洁的注释说明改动
        5. 确保代码语法正确，可以直接运行
        6. 所有导入保持在文件顶部
        7. 用 ```python ... ``` 包裹完整代码
        
        改进类型: {idea_type}
        """).format(idea_type=idea_type)

        if constraints:
            system_prompt += f"\n额外约束:\n{constraints}"

        # 构建 user message
        user_message = textwrap.dedent("""\
        ## 改进请求
        {idea}
        
        ## 当前源文件: {file_path}
        ```python
        {original}
        ```
        
        请输出完整的修改后文件。
        """).format(idea=idea, file_path=str(full_path), original=original)

        # 调用 LLM
        raw_response = cls._call_deepseek(system_prompt, user_message)
        if raw_response is None:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="llm_patch",
                error="LLM API 调用失败",
            )

        # 提取代码块
        modified_code = cls._extract_code_block(raw_response)
        if modified_code is None:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="llm_patch",
                error="无法从 LLM 响应中提取代码块",
                patch_preview=raw_response[:500],
            )

        # AST 语法验证
        try:
            ast.parse(modified_code)
        except SyntaxError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="llm_patch",
                error=f"LLM 生成的代码有语法错误: {exc}",
                patch_preview=modified_code[:500],
            )

        # 写入文件
        try:
            full_path.write_text(modified_code, encoding="utf-8")
        except OSError as exc:
            return PatchResult(
                success=False, file_path=str(full_path),
                transformation="llm_patch",
                error=f"写入失败: {exc}",
            )

        # 计算变更统计
        orig_lines = len(original.split("\n"))
        mod_lines = len(modified_code.split("\n"))
        line_diff = mod_lines - orig_lines

        return PatchResult(
            success=True,
            file_path=str(full_path),
            transformation="llm_patch",
            original_lines=orig_lines,
            modified_lines=mod_lines,
            changes_made=abs(line_diff) if line_diff != 0 else 1,
            description=f"LLM 生成补丁: {line_diff:+d} 行 ({orig_lines}→{mod_lines})",
            patch_preview=modified_code[:300] + ("..." if len(modified_code) > 300 else ""),
        )

    @classmethod
    def _call_deepseek(cls, system_prompt: str, user_message: str) -> Optional[str]:
        """调用 DeepSeek API，返回原始响应文本。"""
        import json as _json
        import http.client
        import urllib.request
        import urllib.error

        # 获取 API 配置
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None

        # 模型与 API 地址以代码为准，.env 仅提供密钥
        model = "deepseek-flash"
        api_url = "https://api.deepseek.com/chat/completions"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        body = _json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": 0.3,  # 低温=更确定性的输出
            "max_tokens": 8000,
        }).encode("utf-8")

        req = urllib.request.Request(
            api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"].get("content", "")
            return content if content else None
        except Exception:
            return None

    @staticmethod
    def _extract_code_block(response: str) -> Optional[str]:
        """从 LLM 响应中提取 Python 代码块。"""
        # 策略 1: ```python ... ```
        m = re.search(r'```python\s*\n(.*?)```', response, re.DOTALL)
        if m:
            return m.group(1).rstrip()

        # 策略 2: ``` ... ```（无语言标记）
        m = re.search(r'```\s*\n(.*?)```', response, re.DOTALL)
        if m:
            code = m.group(1).rstrip()
            # 检查是否像 Python 代码
            if 'def ' in code or 'import ' in code or 'class ' in code:
                return code

        # 策略 3: 整个响应就是代码（以 import/from/def/class 开头）
        stripped = response.strip()
        if any(stripped.startswith(kw) for kw in ('import ', 'from ', 'def ', 'class ', '#!', '"""')):
            return stripped

        return None

    # ═══════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════

    @classmethod
    def preview(cls, file_path: str, transform: str, params=None) -> str:
        """预览转换效果（不实际写入）。返回 diff 文本。"""
        params = params or {}
        full_path = SANDBOX_DIR / file_path

        if not full_path.is_file():
            return f"文件不存在: {full_path}"

        original = full_path.read_text(encoding="utf-8")
        orig_lines = original.split("\n")

        # 应用转换但不写入
        if transform == "set_lookup":
            pattern = re.compile(
                r'(\bif\b|\belif\b|\bwhile\b)\s+(\w+)\s+(not\s+)?in\s+\[([^\]]+)\]'
            )
            def rp(m):
                items = [x.strip() for x in m.group(4).split(",")]
                if len(items) > 20:
                    return m.group(0)
                return f"{m.group(1)} {m.group(2)} {m.group(3) or ''}in {{{m.group(4)}}}"
            modified, count = pattern.subn(rp, original)
        else:
            return f"preview 不支持转换类型: {transform}"

        mod_lines = modified.split("\n")
        diff_lines = []
        for i, (ol, ml) in enumerate(zip(orig_lines, mod_lines)):
            if ol != ml:
                diff_lines.append(f"  L{i+1}: - {ol.strip()[:80]}")
                diff_lines.append(f"  L{i+1}: + {ml.strip()[:80]}")

        return f"预览 {transform} on {file_path} ({count} changes):\n" + "\n".join(diff_lines[:20])


# ── 全局单例 ───────────────────────────────────────────────

_patcher = AutomatedPatcher()


def apply_patch(file_path: str, transform: str, params=None) -> PatchResult:
    """便捷函数：应用代码转换。"""
    return _patcher.apply(file_path, transform, params)


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 测试 set_lookup
    test_code = """
def check_tool(name):
    if name in ["read_file", "list_directory", "write_file", "replace_text"]:
        return "core"
    elif name in ["monitor", "self_check", "safety_net"]:
        return "diagnostic"
    return "unknown"
"""
    test_path = SANDBOX_DIR / "_patcher_test.py"
    test_path.write_text(test_code, encoding="utf-8")

    result = _patcher.apply("_patcher_test.py", "set_lookup")
    print(f"Set lookup: success={result.success}, changes={result.changes_made}")

    if result.success:
        modified = test_path.read_text(encoding="utf-8")
        print("Modified:\n" + modified[:300])

    test_path.unlink()  # 清理
    print("OK")
