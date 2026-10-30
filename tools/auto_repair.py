"""
auto_repair — 自主修复闭环引擎 (v1.0)
======================================
为 Agent 1 提供自动化的异常→诊断→修复→验证→回滚 闭环能力。

设计理念：
  - 结构化修复流水线：8 阶段从检测到经验沉淀
  - 安全优先：每次修复前强制创建检查点，失败自动回滚
  - 置信度评分：多因子模型，低分标记"待人工审核"
  - 与现有模块深度集成：safety_net / decision_engine / checkpoint /
    test_runner / knowledge / offline_runner

使用方式：
  # 完整流水线
  auto_repair action=repair traceback="Traceback..." error_source="safety_net"

  # 单步操作
  auto_repair action=diagnose traceback="..."
  auto_repair action=verify task_id="..." fix_files='["tools/foo.py"]'
  auto_repair action=rollback task_id="..."
  auto_repair action=history
  auto_repair action=confidence diagnosis='{...}' fix_info='{...}'
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
import traceback as tb_module
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .checkpoint_manager import CheckpointManager
from .decision_engine import DecisionEngine
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


SANDBOX_DIR = Path(__file__).resolve().parent.parent
REPAIR_HISTORY_FILE = SANDBOX_DIR / "memory" / "repair_history.json"


# ── 错误类型 ──────────────────────────────────────────────


class AutoRepairError(RuntimeError):
    """自主修复错误。"""


class RepairConfidenceTooLowError(AutoRepairError):
    """修复置信度过低，拒绝自动应用。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ParsedError:
    """解析后的错误信息。"""
    error_type: str                     # 异常类型，如 "ImportError"
    error_message: str                  # 异常消息
    file_path: str = ""                 # 出错文件路径
    line_number: int = 0                # 出错行号
    function_name: str = ""             # 出错函数名
    code_context: str = ""              # 出错代码行内容
    full_traceback: str = ""            # 完整 traceback
    category: str = "unknown"           # 分类: import/syntax/attribute/runtime/type/other
    severity: str = "medium"            # low / medium / high / critical


@dataclass
class DiagnosisReport:
    """诊断报告。"""
    parsed_error: ParsedError
    root_cause_file: str = ""
    root_cause_line: int = 0
    surrounding_code: str = ""          # 出错行前后各 10 行
    possible_causes: list[str] = field(default_factory=list)
    suggested_fixes: list[str] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)


@dataclass
class RepairPlan:
    """修复计划。"""
    task_id: str
    diagnosis: DiagnosisReport
    strategy: str = ""                  # 修复策略描述
    files_to_modify: list[str] = field(default_factory=list)
    pre_fix_checkpoint_id: str = ""
    confidence_score: float = 0.0
    confidence_level: str = "unknown"   # red / yellow / green
    requires_human_review: bool = True


@dataclass
class RepairResult:
    """修复结果。"""
    task_id: str
    success: bool
    diagnosis: DiagnosisReport | None = None
    plan: RepairPlan | None = None
    verification_result: str = ""
    applied: bool = False
    rolled_back: bool = False
    error_message: str = ""
    confidence_score: float = 0.0
    timestamp: str = ""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "auto_repair",
        "description": (
            "自主修复闭环引擎。自动检测异常、诊断根因、生成修复计划、"
            "沙箱验证、提交或回滚。支持完整流水线和单步操作。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "diagnose",
                        "plan",
                        "verify",
                        "rollback",
                        "repair",
                        "history",
                        "confidence",
                    ],
                    "description": (
                        "操作类型："
                        "diagnose — 解析 traceback 生成诊断报告；"
                        "plan — 基于诊断生成修复计划；"
                        "verify — 在沙箱中验证修复（运行测试）；"
                        "rollback — 回滚到修复前状态；"
                        "repair — 运行完整修复流水线（diagnose→plan→verify→apply/rollback）；"
                        "history — 查看修复历史；"
                        "confidence — 评估修复置信度。"
                    ),
                },
                "traceback": {
                    "type": "string",
                    "description": (
                        "Python traceback 字符串（diagnose/repair 操作需要）。"
                        "可以从错误日志或终端输出中获取。"
                    ),
                    "default": "",
                },
                "error_source": {
                    "type": "string",
                    "description": (
                        "异常来源: safety_net / self_check / test_runner / manual"
                    ),
                    "default": "manual",
                },
                "task_id": {
                    "type": "string",
                    "description": "修复任务 ID（verify/rollback 操作需要）",
                    "default": "",
                },
                "fix_files": {
                    "type": "string",
                    "description": (
                        "修复涉及的文件列表 JSON 数组（verify 操作需要）。"
                        "例如: '[\"tools/foo.py\", \"tools/bar.py\"]'"
                    ),
                    "default": "[]",
                },
                "diagnosis": {
                    "type": "string",
                    "description": "诊断报告 JSON（plan/confidence 操作需要）",
                    "default": "{}",
                },
                "fix_info": {
                    "type": "string",
                    "description": "修复信息 JSON（confidence 操作需要）",
                    "default": "{}",
                },
                "auto_apply": {
                    "type": "boolean",
                    "description": "是否自动应用修复（repair 操作，默认 False 需要人工确认）",
                    "default": False,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── Traceback 解析器 ──────────────────────────────────────


class TracebackParser:
    """
    Python traceback 解析器。

    从文本 traceback 中提取结构化的错误信息：
    - 异常类型 (ImportError, SyntaxError, ...)
    - 出错文件路径
    - 出错行号
    - 出错函数名
    - 出错代码行内容
    - 完整上下文

    支持的格式：
      - 标准 Python 3 traceback（File "...", line N, in func）
      - 简化 traceback（只有最后一行异常信息）
      - 多层嵌套 traceback
    """

    # traceback 行正则：File "path", line N, in func
    _TB_FILE_RE = re.compile(
        r'^\s*File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+(.+))?'
    )

    # 异常行正则：ExceptionType: message
    _TB_ERROR_RE = re.compile(
        r'^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Error|Interrupt|Exit)):\s*(.*)'
    )

    # 备选：仅匹配 "Error" 结尾的类型
    _TB_ERROR_FALLBACK = re.compile(
        r'^([A-Za-z_][\w.]*Error):\s*(.*)'
    )

    # 异常分类映射
    CATEGORY_MAP: dict[str, str] = {
        "ImportError": "import",
        "ModuleNotFoundError": "import",
        "SyntaxError": "syntax",
        "IndentationError": "syntax",
        "TabError": "syntax",
        "AttributeError": "attribute",
        "NameError": "name",
        "TypeError": "type",
        "ValueError": "value",
        "KeyError": "key",
        "IndexError": "index",
        "FileNotFoundError": "file_io",
        "PermissionError": "file_io",
        "IsADirectoryError": "file_io",
        "NotADirectoryError": "file_io",
        "OSError": "file_io",
        "RuntimeError": "runtime",
        "RecursionError": "runtime",
        "StopIteration": "runtime",
        "AssertionError": "assertion",
        "ZeroDivisionError": "math",
        "OverflowError": "math",
        "MemoryError": "resource",
        "ConnectionError": "network",
        "TimeoutError": "network",
    }

    def parse(self, traceback_text: str) -> ParsedError:
        """
        解析 traceback 文本。

        Args:
            traceback_text: Python traceback 字符串

        Returns:
            ParsedError 结构
        """
        if not traceback_text or not traceback_text.strip():
            raise AutoRepairError("traceback 文本不能为空")

        lines = traceback_text.strip().split("\n")

        # 提取 File 行信息
        file_path = ""
        line_number = 0
        function_name = ""
        code_lines: list[str] = []

        for i, line in enumerate(lines):
            file_match = self._TB_FILE_RE.match(line)
            if file_match:
                file_path = file_match.group(1)
                line_number = int(file_match.group(2))
                if file_match.group(3):
                    function_name = file_match.group(3).strip()

                # 尝试提取出错的代码行（File 行之后的下一行）
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("File ") and not self._TB_ERROR_RE.match(next_line):
                        code_lines.append(next_line)

                continue

            # 也检查是否有在 File 行之前的代码行（某些 traceback 格式）
            if file_path and line_number and not code_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("File ") and not stripped.startswith("Traceback"):
                    code_lines.append(stripped)

        # 提取异常类型和消息
        error_type = "Exception"
        error_message = ""

        # 从最后一行开始查找异常
        for line in reversed(lines):
            line = line.strip()
            # 跳过 "During handling of..." 和空行
            if not line or line.startswith("During handling"):
                continue

            error_match = self._TB_ERROR_RE.match(line)
            if error_match:
                error_type = error_match.group(1)
                error_message = error_match.group(2)
                break

            fallback_match = self._TB_ERROR_FALLBACK.match(line)
            if fallback_match:
                error_type = fallback_match.group(1)
                error_message = fallback_match.group(2)
                break

        # 如果没有找到 File 信息，尝试从错误消息中提取路径
        if not file_path and error_message:
            # SyntaxError 有时包含 (file, line, ...) 元组信息
            file_in_msg = re.search(r"\((['\"])(.+?\.py)\1", error_message)
            if file_in_msg:
                file_path = file_in_msg.group(2)

        # 清理文件路径：将绝对路径转为相对于 SANDBOX_DIR 的路径
        if file_path:
            try:
                file_path = str(Path(file_path).resolve())
                sandbox_str = str(SANDBOX_DIR.resolve())
                if file_path.startswith(sandbox_str):
                    file_path = file_path[len(sandbox_str) + 1:]  # +1 for /
            except (OSError, ValueError):
                pass  # 保留原始路径

        # 分类
        category = self._classify(error_type)
        severity = self._assess_severity(error_type, error_message)

        code_context = code_lines[0] if code_lines else ""

        return ParsedError(
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            line_number=line_number,
            function_name=function_name,
            code_context=code_context,
            full_traceback=traceback_text,
            category=category,
            severity=severity,
        )

    def _classify(self, error_type: str) -> str:
        """根据异常类型分类。"""
        if error_type in self.CATEGORY_MAP:
            return self.CATEGORY_MAP[error_type]
        # 前缀匹配
        for key, cat in self.CATEGORY_MAP.items():
            if error_type.endswith(key) or key.endswith(error_type):
                return cat
        return "unknown"

    def _assess_severity(self, error_type: str, error_message: str) -> str:
        """评估错误严重程度。"""
        critical_types = {"SystemExit", "MemoryError", "KeyboardInterrupt"}
        high_types = {"ImportError", "ModuleNotFoundError", "SyntaxError", "IndentationError"}
        low_types = {"DeprecationWarning", "PendingDeprecationWarning", "UserWarning"}

        if error_type in critical_types:
            return "critical"
        if error_type in high_types:
            return "high"
        if error_type in low_types:
            return "low"
        return "medium"


# ── 置信度评分器 ──────────────────────────────────────────


class ConfidenceScorer:
    """
    修复置信度多因子评分器。

    评分因子（权重可调）：
      - error_category_score (0.30): 该异常类型的历史修复成功率
      - test_coverage_score (0.25): 修复代码是否有对应测试
      - fix_size_score     (0.20): 修改行数越少越好
      - verification_score (0.25): 测试全部通过 = 1.0

    置信度等级：
      score < 0.3  → RED:   标记"待人工审核"
      0.3 ≤ score < 0.7 → YELLOW: 应用但额外记录
      score ≥ 0.7  → GREEN:  自动提交
    """

    # 因子权重
    WEIGHTS = {
        "error_category": 0.30,
        "test_coverage": 0.25,
        "fix_size": 0.20,
        "verification": 0.25,
    }

    # 阈值
    GREEN_THRESHOLD = 0.7
    YELLOW_THRESHOLD = 0.3

    def __init__(self) -> None:
        self._history: dict[str, dict[str, int]] = self._load_history()

    def _load_history(self) -> dict[str, dict[str, int]]:
        """加载修复历史统计。"""
        if REPAIR_HISTORY_FILE.is_file():
            try:
                data = _read_json_cached(REPAIR_HISTORY_FILE)
                # 提取分类统计
                stats: dict[str, dict[str, int]] = {}
                for entry in data:
                    cat = entry.get("category", "unknown")
                    if cat not in stats:
                        stats[cat] = {"success": 0, "total": 0}
                    stats[cat]["total"] += 1
                    if entry.get("success"):
                        stats[cat]["success"] += 1
                return stats
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def score(
        self,
        error_category: str,
        test_coverage_ratio: float = 0.5,
        fix_line_count: int = 1,
        verification_passed: bool = False,
    ) -> tuple[float, str]:
        """
        计算修复置信度。

        Args:
            error_category: 异常分类 (import/syntax/attribute/runtime/...)
            test_coverage_ratio: 测试覆盖度 (0.0-1.0)
            fix_line_count: 修改行数
            verification_passed: 验证是否通过

        Returns:
            (confidence_score, level)
        """
        # 因子 1: 异常类型历史成功率
        cat_stats = self._history.get(error_category, {"success": 0, "total": 0})
        if cat_stats["total"] > 0:
            error_category_score = cat_stats["success"] / cat_stats["total"]
        else:
            # 无历史数据，根据异常类型给出先验估计
            error_category_score = self._prior_category_score(error_category)

        # 因子 2: 测试覆盖度
        test_coverage_score = min(test_coverage_ratio, 1.0)

        # 因子 3: 修改行数（越少越好，超过 50 行接近 0）
        if fix_line_count <= 1:
            fix_size_score = 1.0
        elif fix_line_count >= 50:
            fix_size_score = 0.0
        else:
            fix_size_score = 1.0 - (fix_line_count - 1) / 49.0

        # 因子 4: 验证结果
        verification_score = 1.0 if verification_passed else 0.0

        # 加权求和
        confidence = (
            self.WEIGHTS["error_category"] * error_category_score
            + self.WEIGHTS["test_coverage"] * test_coverage_score
            + self.WEIGHTS["fix_size"] * fix_size_score
            + self.WEIGHTS["verification"] * verification_score
        )

        # 确定等级
        if confidence >= self.GREEN_THRESHOLD:
            level = "green"
        elif confidence >= self.YELLOW_THRESHOLD:
            level = "yellow"
        else:
            level = "red"

        return confidence, level

    @staticmethod
    def _prior_category_score(category: str) -> float:
        """无历史数据时的先验估计。"""
        priors = {
            "import": 0.7,    # 导入错误通常容易修复
            "syntax": 0.8,    # 语法错误通常容易修复
            "attribute": 0.5, # 属性错误中等难度
            "name": 0.6,      # 名称错误中等
            "type": 0.5,      # 类型错误中等
            "value": 0.4,     # 值错误较难
            "key": 0.6,       # 键错误中等
            "index": 0.6,     # 索引错误中等
            "file_io": 0.5,   # 文件IO中等
            "runtime": 0.3,   # 运行时错误通常较难
            "assertion": 0.5, # 断言错误中等
            "math": 0.6,      # 数学错误较简单
            "resource": 0.2,  # 资源错误难以自动修复
            "network": 0.3,   # 网络错误难以自动修复
        }
        return priors.get(category, 0.4)


# ── 修复编排器 ────────────────────────────────────────────


class RepairOrchestrator:
    """
    自主修复编排器。

    管理完整的修复流水线：
      DETECT → DIAGNOSE → PLAN → BACKUP → GENERATE → VERIFY → APPLY/ROLLBACK → LEARN

    与现有模块集成：
      - CheckpointManager: 修复前后快照
      - DecisionEngine: 策略建议和决策记录
    """

    def __init__(self) -> None:
        self._checkpoint = CheckpointManager()
        self._decision = DecisionEngine()
        self._parser = TracebackParser()
        self._scorer = ConfidenceScorer()
        self._active_repairs: dict[str, RepairPlan] = {}
        self._ensure_history_file()

    def _ensure_history_file(self) -> None:
        """确保修复历史文件存在。"""
        if not REPAIR_HISTORY_FILE.is_file():
            REPAIR_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            REPAIR_HISTORY_FILE.write_text("[]", encoding="utf-8")

    # ── Phase 2: 诊断 ────────────────────────────────────

    def diagnose(self, traceback_text: str, error_source: str = "manual") -> str:
        """
        解析 traceback 并生成诊断报告。

        Args:
            traceback_text: Python traceback 字符串
            error_source: 异常来源

        Returns:
            格式化的诊断报告
        """
        try:
            parsed = self._parser.parse(traceback_text)
        except AutoRepairError as exc:
            return f"❌ 解析失败: {exc}"

        # 读取相关代码上下文
        surrounding_code = ""
        affected_modules: list[str] = []
        if parsed.file_path:
            affected_modules.append(parsed.file_path.replace("/", ".").replace(".py", ""))
            surrounding_code = self._read_surrounding_code(
                parsed.file_path, parsed.line_number
            )

        # 查找相关测试
        affected_tests = self._find_related_tests(parsed.file_path)

        # 生成可能原因和修复建议
        possible_causes = self._generate_possible_causes(parsed)
        suggested_fixes = self._generate_suggested_fixes(parsed)

        lines = [
            "🔍 异常诊断报告",
            f"{'='*60}",
            f"",
            f"📋 基本信息",
            f"  异常类型: {parsed.error_type}",
            f"  异常分类: {parsed.category}",
            f"  严重程度: {parsed.severity}",
            f"  异常消息: {parsed.error_message}",
            f"  异常来源: {error_source}",
            f"",
            f"📍 错误位置",
        ]

        if parsed.file_path:
            lines.append(f"  文件:     {parsed.file_path}")
            lines.append(f"  行号:     {parsed.line_number}")
            lines.append(f"  函数:     {parsed.function_name or '<module>'}")
        else:
            lines.append(f"  ⚠️ 无法从 traceback 中提取文件位置")

        if parsed.code_context:
            lines.append(f"  代码:     {parsed.code_context}")

        if surrounding_code:
            lines.append(f"")
            lines.append(f"📄 上下文代码（前后各 10 行）:")
            lines.append(f"{'─'*40}")
            lines.append(surrounding_code)

        if possible_causes:
            lines.append(f"")
            lines.append(f"🤔 可能原因:")
            for i, cause in enumerate(possible_causes, 1):
                lines.append(f"  {i}. {cause}")

        if suggested_fixes:
            lines.append(f"")
            lines.append(f"💡 修复建议:")
            for i, fix in enumerate(suggested_fixes, 1):
                lines.append(f"  {i}. {fix}")

        if affected_modules:
            lines.append(f"")
            lines.append(f"📦 受影响模块: {', '.join(affected_modules)}")

        if affected_tests:
            lines.append(f"🧪 相关测试: {', '.join(affected_tests[:5])}")
            if len(affected_tests) > 5:
                lines.append(f"   ...及其他 {len(affected_tests) - 5} 个测试")

        return "\n".join(lines)

    # ── Phase 3: 计划 ────────────────────────────────────

    def plan(self, diagnosis_json: str) -> str:
        """
        基于诊断报告生成修复计划。

        Args:
            diagnosis_json: 诊断报告 JSON 字符串

        Returns:
            格式化的修复计划
        """
        try:
            diag_data = json.loads(diagnosis_json)
        except json.JSONDecodeError as exc:
            return f"❌ JSON 解析错误: {exc}"

        task_id = f"AR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        error_category = diag_data.get("category", "unknown")
        file_path = diag_data.get("file_path", "")

        # 计算初始置信度
        confidence, level = self._scorer.score(
            error_category=error_category,
            test_coverage_ratio=0.5,
            fix_line_count=diag_data.get("fix_line_count", 10),
            verification_passed=False,
        )

        plan_obj = RepairPlan(
            task_id=task_id,
            diagnosis=DiagnosisReport(
                parsed_error=ParsedError(
                    error_type=diag_data.get("error_type", "Exception"),
                    error_message=diag_data.get("error_message", ""),
                    file_path=file_path,
                    line_number=diag_data.get("line_number", 0),
                    category=error_category,
                ),
                root_cause_file=file_path,
                root_cause_line=diag_data.get("line_number", 0),
            ),
            strategy=diag_data.get("strategy", f"修复 {error_category} 类型异常"),
            files_to_modify=[file_path] if file_path else [],
            confidence_score=confidence,
            confidence_level=level,
            requires_human_review=(level == "red"),
        )

        self._active_repairs[task_id] = plan_obj

        level_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(level, "⚪")

        lines = [
            f"📋 修复计划",
            f"{'='*60}",
            f"",
            f"任务 ID:   {task_id}",
            f"异常分类: {error_category}",
            f"目标文件: {file_path or '未知'}",
            f"修复策略: {plan_obj.strategy}",
            f"",
            f"{level_emoji} 置信度: {confidence:.2f} ({level.upper()})",
        ]

        if level == "red":
            lines.append(f"   ⚠️ 置信度过低，建议人工审核后再执行修复")
        elif level == "yellow":
            lines.append(f"   💡 中等置信度，修复后建议额外验证")
        else:
            lines.append(f"   ✅ 高置信度，可自动应用修复")

        lines.append(f"")
        lines.append(f"📝 后续步骤:")
        lines.append(f"  1. 备份当前状态: checkpoint save")
        lines.append(f"  2. 应用修复代码: write_file / replace_text")
        lines.append(f"  3. 验证修复: auto_repair action=verify task_id={task_id}")
        lines.append(f"  4. 提交或回滚: 验证通过则保留，失败则 rollback")

        return "\n".join(lines)

    # ── Phase 4+5: 备份 ──────────────────────────────────

    def backup(self, task_id: str) -> str:
        """
        创建预修复检查点。

        Args:
            task_id: 修复任务 ID

        Returns:
            检查点 ID
        """
        plan = self._active_repairs.get(task_id)
        if not plan:
            # 尝试从已有修复计划中查找
            return self._checkpoint.save(
                task_id=task_id,
                phase="pre_repair",
                state={"task_id": task_id, "phase": "pre_repair"},
            )

        cp_id = self._checkpoint.save(
            task_id=task_id,
            phase="pre_repair",
            state={
                "task_id": task_id,
                "files_to_modify": plan.files_to_modify,
                "diagnosis": {
                    "error_type": plan.diagnosis.parsed_error.error_type,
                    "file_path": plan.diagnosis.root_cause_file,
                    "line_number": plan.diagnosis.root_cause_line,
                },
            },
        )
        plan.pre_fix_checkpoint_id = cp_id
        return cp_id

    # ── Phase 6: 验证 ────────────────────────────────────

    def verify(self, task_id: str, fix_files_json: str = "[]") -> str:
        """
        验证修复是否通过测试。

        运行受影响的测试和全量回归测试。

        Args:
            task_id: 修复任务 ID
            fix_files_json: 修复涉及的文件列表 JSON

        Returns:
            验证结果
        """
        try:
            fix_files: list[str] = json.loads(fix_files_json)
        except json.JSONDecodeError:
            fix_files = []

        # 导入 test_runner
        try:
            from .test_runner import _runner as test_runner
        except ImportError:
            return (
                "⚠️ 无法导入 test_runner\n"
                "请手动运行: test_runner action=run_all\n"
                "然后根据测试结果判断修复是否成功。"
            )

        lines = [
            f"🧪 修复验证",
            f"{'='*60}",
            f"任务 ID: {task_id}",
            f"涉及文件: {', '.join(fix_files) if fix_files else '未指定'}",
            f"",
        ]

        if fix_files:
            # 运行相关模块的测试
            for f in fix_files:
                module_name = Path(f).stem
                # 检查是否有对应的测试文件
                test_file = SANDBOX_DIR / "tests" / f"test_{module_name}.py"
                if test_file.is_file():
                    lines.append(f"运行测试: test_{module_name}")
                    result = test_runner.run_single(module_name)
                    lines.append(result)
                else:
                    lines.append(f"ℹ️ 模块 {module_name} 无对应测试文件，跳过")

        # 运行全量回归测试
        lines.append(f"\n📊 全量回归测试:")
        full_result = test_runner.run_all()
        lines.append(full_result)

        return "\n".join(lines)

    # ── Phase 7: 回滚 ────────────────────────────────────

    def rollback(self, task_id: str) -> str:
        """
        回滚到修复前状态。

        Args:
            task_id: 修复任务 ID

        Returns:
            回滚结果
        """
        # 查找预修复检查点
        checkpoints = self._checkpoint.list(task_id=task_id)
        pre_repair_cps = [cp for cp in checkpoints if cp.get("phase") == "pre_repair"]

        if not pre_repair_cps:
            return (
                f"⚠️ 未找到任务 '{task_id}' 的预修复检查点\n"
                f"可用的检查点阶段: {[cp.get('phase') for cp in checkpoints]}"
            )

        latest_cp = pre_repair_cps[0]
        cp_id = latest_cp.get("checkpoint_id", "")

        try:
            state = self._checkpoint.rollback(task_id, "pre_repair")
        except Exception as exc:
            return f"❌ 回滚失败: {exc}"

        # 记录回滚
        self._record_repair(
            task_id=task_id,
            success=False,
            category="unknown",
            confidence=0.0,
            notes=f"已回滚到检查点 {cp_id}",
        )

        return (
            f"⏪ 回滚成功\n"
            f"{'='*40}\n"
            f"任务 ID:   {task_id}\n"
            f"检查点:    {cp_id}\n"
            f"恢复状态:  pre_repair\n"
            f"\n💡 修复已撤销，系统已恢复到修复前状态。"
        )

    # ── 完整流水线 ───────────────────────────────────────

    def repair(
        self,
        traceback_text: str,
        error_source: str = "manual",
        auto_apply: bool = False,
    ) -> str:
        """
        运行完整修复流水线。

        diagnose → plan → backup → [agent generates fix] → verify → apply/rollback

        注意: "生成修复代码"这一步需要 LLM Agent 在两次工具调用之间完成。
        本方法执行 diagnose + plan + backup，返回修复计划供 Agent 使用。

        Args:
            traceback_text: Python traceback 字符串
            error_source: 异常来源
            auto_apply: 是否自动应用（暂由 Agent 决策）

        Returns:
            完整修复流程结果
        """
        # Phase 2: 诊断
        diagnosis = self.diagnose(traceback_text, error_source)

        # 提取诊断数据用于 plan
        try:
            parsed = self._parser.parse(traceback_text)
        except AutoRepairError:
            return f"{diagnosis}\n\n❌ 无法继续: traceback 解析失败"

        diag_json = json.dumps({
            "error_type": parsed.error_type,
            "error_message": parsed.error_message,
            "file_path": parsed.file_path,
            "line_number": parsed.line_number,
            "function_name": parsed.function_name,
            "category": parsed.category,
            "severity": parsed.severity,
            "strategy": f"修复 {parsed.file_path}:{parsed.line_number} 的 {parsed.error_type}",
            "fix_line_count": 5,  # 初始估计
        }, ensure_ascii=False)

        # Phase 3: 计划
        plan_result = self.plan(diag_json)

        # Phase 4: 备份
        task_id = ""
        for tid, p in self._active_repairs.items():
            if p.diagnosis.root_cause_file == parsed.file_path:
                task_id = tid
                break

        if task_id:
            cp_id = self.backup(task_id)
            plan_result += f"\n\n📸 预修复检查点: {cp_id}"

        return (
            f"{diagnosis}\n\n"
            f"{'='*60}\n"
            f"{plan_result}\n"
            f"\n{'='*60}\n"
            f"📌 下一步:\n"
            f"  1. 根据修复建议编写修复代码（write_file / replace_text）\n"
            f"  2. 运行验证: auto_repair action=verify fix_files='[\"目标文件\"]'\n"
            f"  3. 验证通过 → 保留修复\n"
            f"  4. 验证失败 → auto_repair action=rollback task_id={task_id or '<TASK_ID>'}"
        )

    # ── 辅助方法 ──────────────────────────────────────────

    def _read_surrounding_code(self, file_path: str, line_number: int, context: int = 10) -> str:
        """读取出错行周围的代码上下文。"""
        full_path = SANDBOX_DIR / file_path
        if not full_path.is_file():
            return ""

        try:
            all_lines = full_path.read_text(encoding="utf-8").split("\n")
        except (OSError, UnicodeDecodeError):
            return ""

        start = max(0, line_number - context - 1)
        end = min(len(all_lines), line_number + context)

        result_lines: list[str] = []
        for i in range(start, end):
            actual_line = i + 1
            marker = ">>>" if actual_line == line_number else "   "
            result_lines.append(f"{marker} {actual_line:4d} | {all_lines[i]}")

        return "\n".join(result_lines)

    def _find_related_tests(self, file_path: str) -> list[str]:
        """查找与目标文件相关的测试文件。"""
        if not file_path:
            return []

        module_name = Path(file_path).stem
        tests_dir = SANDBOX_DIR / "tests"
        if not tests_dir.is_dir():
            return []

        related: list[str] = []
        # 精确匹配: test_<module>.py
        exact = tests_dir / f"test_{module_name}.py"
        if exact.is_file():
            related.append(f"test_{module_name}.py")

        # 模糊匹配: 包含 module name 的测试文件
        for test_file in sorted(tests_dir.glob("test_*.py")):
            if test_file.name == f"test_{module_name}.py":
                continue  # 已添加
            if module_name in test_file.stem:
                related.append(test_file.name)

        return related

    def _generate_possible_causes(self, parsed: ParsedError) -> list[str]:
        """根据异常类型生成可能原因。"""
        causes: dict[str, list[str]] = {
            "import": [
                "模块未安装或路径不正确",
                "循环导入",
                f"模块名拼写错误: '{parsed.error_message}'",
                "PYTHONPATH 配置问题",
            ],
            "syntax": [
                "代码语法错误（括号不匹配、冒号缺失等）",
                "缩进混用（Tab 和空格）",
                "字符串引号不匹配",
            ],
            "attribute": [
                "对象没有该属性或方法",
                f"可能是拼写错误: '{parsed.error_message}'",
                "对象类型与预期不符",
                "导入的模块版本不正确",
            ],
            "name": [
                "变量或函数未定义",
                "变量作用域问题",
                "导入语句缺失",
            ],
            "type": [
                "参数类型不匹配",
                "对 None 执行了操作",
                "操作符不支持该数据类型",
            ],
            "runtime": [
                "逻辑错误导致异常状态",
                "递归过深或无终止条件",
                "资源已被释放或关闭",
            ],
        }

        cat = parsed.category
        return causes.get(cat, [f"未知原因的 {parsed.error_type}", "需要进一步分析代码逻辑"])

    def _generate_suggested_fixes(self, parsed: ParsedError) -> list[str]:
        """根据异常类型生成修复建议。"""
        fixes: dict[str, list[str]] = {
            "import": [
                f"检查 '{parsed.file_path}' 中的 import 语句",
                "确认目标模块已安装（pip install ...）",
                "检查是否存在循环导入",
            ],
            "syntax": [
                f"检查 {parsed.file_path}:{parsed.line_number} 附近的语法",
                "使用 python -m py_compile 验证语法",
            ],
            "attribute": [
                f"检查 '{parsed.file_path}' 第 {parsed.line_number} 行的对象类型",
                "添加 hasattr() 检查或 try/except 保护",
            ],
            "name": [
                f"确认变量/函数在 '{parsed.file_path}' 中已正确定义",
                "检查变量拼写是否正确",
            ],
            "type": [
                "添加类型检查或类型转换",
                "使用 isinstance() 验证类型",
            ],
            "runtime": [
                "添加边界检查和防御性编程",
                "检查递归终止条件",
            ],
        }

        cat = parsed.category
        return fixes.get(cat, ["手动分析代码逻辑", "添加更多日志来定位问题"])

    def _record_repair(
        self,
        task_id: str,
        success: bool,
        category: str,
        confidence: float,
        notes: str = "",
    ) -> None:
        """记录修复历史。"""
        try:
            if REPAIR_HISTORY_FILE.is_file():
                history = _read_json_cached(REPAIR_HISTORY_FILE)
            else:
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

        history.append({
            "task_id": task_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "category": category,
            "confidence": confidence,
            "notes": notes,
        })

        # 最多保留 100 条
        if len(history) > 100:
            history = history[-100:]

        REPAIR_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPAIR_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 更新置信度评分器的历史
        self._scorer = ConfidenceScorer()

    # ── 查看历史 ──────────────────────────────────────────

    def history(self) -> str:
        """查看修复历史。"""
        try:
            if REPAIR_HISTORY_FILE.is_file():
                history = _read_json_cached(REPAIR_HISTORY_FILE)
            else:
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

        if not history:
            return "📋 暂无修复历史记录。"

        total = len(history)
        successful = sum(1 for h in history if h.get("success"))
        failed = total - successful

        lines = [
            f"📋 修复历史",
            f"{'='*50}",
            f"总计: {total} | ✅ 成功: {successful} | ❌ 失败: {failed}",
            f"成功率: {successful/total*100:.1f}%" if total > 0 else "",
            f"",
        ]

        for entry in reversed(history[-20:]):
            icon = "✅" if entry.get("success") else "❌"
            lines.append(
                f"  {icon} [{entry.get('task_id', '?')}] "
                f"{entry.get('timestamp', '?')} "
                f"({entry.get('category', '?')}, 置信度: {entry.get('confidence', 0):.2f})"
            )
            if entry.get("notes"):
                lines.append(f"     {entry['notes'][:100]}")

        return "\n".join(lines)

    # ── 置信度评估 ────────────────────────────────────────

    def confidence(self, diagnosis_json: str, fix_info_json: str) -> str:
        """
        评估修复置信度。

        Args:
            diagnosis_json: 诊断报告 JSON
            fix_info_json: 修复信息 JSON

        Returns:
            置信度评估结果
        """
        try:
            diag = json.loads(diagnosis_json) if isinstance(diagnosis_json, str) else diagnosis_json
        except json.JSONDecodeError:
            diag = {}

        try:
            fix = json.loads(fix_info_json) if isinstance(fix_info_json, str) else fix_info_json
        except json.JSONDecodeError:
            fix = {}

        category = diag.get("category", "unknown")
        fix_line_count = fix.get("fix_line_count", 1)
        test_coverage = fix.get("test_coverage_ratio", 0.5)
        verification_passed = fix.get("verification_passed", False)

        score, level = self._scorer.score(
            error_category=category,
            test_coverage_ratio=test_coverage,
            fix_line_count=fix_line_count,
            verification_passed=verification_passed,
        )

        level_info = {
            "green": ("🟢 GREEN", "可自动应用，置信度高"),
            "yellow": ("🟡 YELLOW", "建议应用但需额外验证"),
            "red": ("🔴 RED", "置信度过低，需要人工审核"),
        }.get(level, ("⚪ UNKNOWN", "无法分类"))

        return (
            f"📊 修复置信度评估\n"
            f"{'='*50}\n"
            f"置信度分数: {score:.2f}\n"
            f"置信度等级: {level_info[0]}\n"
            f"建议操作:   {level_info[1]}\n"
            f"\n"
            f"评分明细:\n"
            f"  异常类型 ({category}):     权重 {self._scorer.WEIGHTS['error_category']:.0%}\n"
            f"  测试覆盖度:               权重 {self._scorer.WEIGHTS['test_coverage']:.0%}\n"
            f"  修改行数 ({fix_line_count} 行):        权重 {self._scorer.WEIGHTS['fix_size']:.0%}\n"
            f"  验证结果:                 权重 {self._scorer.WEIGHTS['verification']:.0%}"
        )


# ── 全局实例 ──────────────────────────────────────────────

_orchestrator = RepairOrchestrator()
_parser = TracebackParser()


def execute_auto_repair_tool(arguments: dict[str, Any]) -> str:
    """执行 auto_repair 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "diagnose":
            traceback_text = arguments.get("traceback", "")
            error_source = arguments.get("error_source", "manual")
            if not traceback_text:
                return "❌ 请提供 traceback 文本（参数: traceback）"
            return _orchestrator.diagnose(traceback_text, error_source)

        elif action == "plan":
            diagnosis = arguments.get("diagnosis", "{}")
            if not diagnosis or diagnosis == "{}":
                return "❌ 请提供诊断报告 JSON（参数: diagnosis）"
            return _orchestrator.plan(diagnosis)

        elif action == "verify":
            task_id = arguments.get("task_id", "")
            fix_files = arguments.get("fix_files", "[]")
            if not task_id:
                return "❌ 请提供任务 ID（参数: task_id）"
            return _orchestrator.verify(task_id, fix_files)

        elif action == "rollback":
            task_id = arguments.get("task_id", "")
            if not task_id:
                return "❌ 请提供任务 ID（参数: task_id）"
            return _orchestrator.rollback(task_id)

        elif action == "repair":
            traceback_text = arguments.get("traceback", "")
            error_source = arguments.get("error_source", "manual")
            auto_apply = arguments.get("auto_apply", False)
            if not traceback_text:
                return "❌ 请提供 traceback 文本（参数: traceback）"
            return _orchestrator.repair(traceback_text, error_source, auto_apply)

        elif action == "history":
            return _orchestrator.history()

        elif action == "confidence":
            diagnosis = arguments.get("diagnosis", "{}")
            fix_info = arguments.get("fix_info", "{}")
            return _orchestrator.confidence(diagnosis, fix_info)

        else:
            return f"❌ 未知操作: {action}\n可用: diagnose, plan, verify, rollback, repair, history, confidence"

    except AutoRepairError as exc:
        return f"❌ 自主修复错误: {exc}"
