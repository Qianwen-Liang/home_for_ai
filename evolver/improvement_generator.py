"""
improvement_generator — 改进创意生成引擎 v1.0

基于系统监控数据和自检结果，自动生成改进创意。
支持多种改进类型（L1~L5），对创意进行可行性评分和排序。

核心能力：
  1. 分析 monitor 数据 → 识别性能瓶颈 → 生成优化创意
  2. 分析 self_check 结果 → 识别缺陷 → 生成修复创意
  3. 分析 knowledge 趋势 → 识别模式 → 生成架构创意
  4. 对创意评分排序 → 输出优先级列表
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径 ──────────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
IDEAS_DIR = SANDBOX_DIR / "memory" / "improvement_ideas"
IDEAS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SANDBOX_DIR))


class ImprovementType(str, Enum):
    """改进类型（L1~L5）。"""
    L1_PARAM_TUNING = "L1"       # 参数调优：权重调整、阈值优化
    L2_PERF_OPT = "L2"            # 性能优化：算法替换、缓存引入
    L3_BUG_FIX = "L3"             # Bug修复：异常处理、边界条件
    L4_ARCH_REFACTOR = "L4"       # 架构改进：模块拆分、抽象层引入
    L5_NEW_CAPABILITY = "L5"      # 新能力：新工具、新action


@dataclass
class ImprovementIdea:
    """一条改进创意。"""
    idea_id: str
    title: str
    description: str
    improvement_type: ImprovementType
    source: str                      # 创意来源：monitor / self_check / knowledge / manual
    target_module: str               # 目标模块文件名
    estimated_effort: str            # 预估工作量: low / medium / high
    feasibility_score: float = 0.0   # 可行性评分 0-1
    impact_score: float = 0.0        # 影响评分 0-1
    risk_score: float = 0.0          # 风险评分 0-1 (越低越好)
    priority_score: float = 0.0      # 综合优先级评分
    confidence: float = 0.5          # 置信度 0-1
    implementation_hint: str = ""    # 实现提示
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "proposed"         # proposed / accepted / implemented / rejected
    precondition_verified: bool = False  # 前提是否经精确验证（True=可安全自动执行，False=需人工确认前提）
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["improvement_type"] = self.improvement_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ImprovementIdea":
        d = dict(d)
        d["improvement_type"] = ImprovementType(d.pop("improvement_type", "L1"))
        return cls(**d)


def _detect_json_preload(code: str) -> bool:
    """精确检测"每次调用都读取 JSON 文件"。

    用 AST 定位 json.load / json.loads，且参数必须是"文件读取"来源
    （open(...)、xxx.read()、xxx.read_text()），排除：
      1. 初始化/加载方法（__init__/_load/load/reload，只在启动时执行一次）；
      2. json.loads(字符串参数)（解析 JSON 字符串，非读文件）。

    Returns:
        True 表示确实存在"非初始化方法体内每次调用读取 JSON 文件"的模式。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    EXCLUDED_METHODS = {"__init__", "_load", "load", "reload", "_reload"}

    def _is_file_read(arg) -> bool:
        """判断调用参数是否为文件读取来源。"""
        if not isinstance(arg, ast.Call):
            return False
        # open(...).read() / open(...).read_text() / path.read_text()
        if isinstance(arg.func, ast.Attribute) and arg.func.attr in ("read", "read_text"):
            return True
        # open(...)
        if isinstance(arg.func, ast.Name) and arg.func.id == "open":
            return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in EXCLUDED_METHODS:
            continue
        for sub in ast.walk(node):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)):
                continue
            if not (isinstance(sub.func.value, ast.Name) and sub.func.value.id == "json"):
                continue
            if sub.func.attr in ("load", "loads"):
                if sub.args and _is_file_read(sub.args[0]):
                    return True
    return False


class ImprovementGenerator:
    """改进创意生成引擎。

    用法：
        gen = ImprovementGenerator()

        # 从监控数据生成创意
        ideas = gen.from_monitor()

        # 从自检结果生成创意
        ideas += gen.from_self_check()

        # 生成所有创意并排序
        all_ideas = gen.generate_all()
    """

    # ── 性能模式库 ──────────────────────────────────────
    PERF_PATTERNS = [
        {
            "pattern": "slow_import",
            "regex": r"导入.*耗时.*(\d+\.?\d*)s",
            "template": {
                "title": "【{module}】惰性加载优化",
                "description": "模块 {module} 导入耗时 {value}s，建议改为惰性加载（延迟到首次调用时导入）。",
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "low",
                "impact": 0.7,
                "risk": 0.1,
                "hint": "将 import 语句移入函数体内，或使用 importlib.import_module 按需加载。"
            }
        },
        {
            "pattern": "slow_tool",
            "regex": r"工具.*(\w+).*平均响应.*(\d+\.?\d*)ms",
            "template": {
                "title": "【{module}】响应速度优化",
                "description": "工具 {module} 平均响应 {value}ms，超过 500ms 阈值，建议添加缓存或优化算法。",
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "medium",
                "impact": 0.6,
                "risk": 0.2,
                "hint": "检查是否有重复计算、不必要的 I/O 操作，考虑添加 LRU 缓存。"
            }
        },
        {
            "pattern": "high_error_rate",
            "regex": r"错误率.*(\d+\.?\d*)%",
            "template": {
                "title": "错误率过高 — 需排查根因",
                "description": "系统错误率达到 {value}%，需排查高频错误源并修复。",
                "type": ImprovementType.L3_BUG_FIX,
                "effort": "medium",
                "impact": 0.8,
                "risk": 0.1,
                "hint": "使用 monitor.errors() 查看错误详情，关注重复出现的异常类型。"
            }
        },
        {
            "pattern": "large_file",
            "regex": r"文件.*(\w+\.py).*大小.*(\d+\.?\d*)KB",
            "template": {
                "title": "【{module}】大文件拆分",
                "description": "模块 {module} 大小 {value}KB，建议拆分为多个职责单一的子模块。",
                "type": ImprovementType.L4_ARCH_REFACTOR,
                "effort": "high",
                "impact": 0.5,
                "risk": 0.4,
                "hint": "按职责拆分：核心逻辑、工具函数、数据模型各自独立文件。"
            }
        },
        {
            "pattern": "consecutive_errors",
            "regex": r"连续错误.*(\d+)\s*次",
            "template": {
                "title": "连续错误检测 — 触发修复",
                "description": "检测到连续 {value} 次错误，safety_net 可能已触发。需排查根因。",
                "type": ImprovementType.L3_BUG_FIX,
                "effort": "medium",
                "impact": 0.9,
                "risk": 0.05,
                "hint": "使用 auto_repair.diagnose(traceback) 自动诊断最近错误。"
            }
        },
    ]

    # ── 自检模式库 ──────────────────────────────────────
    SELF_CHECK_PATTERNS = [
        {
            "pattern": "import_error",
            "regex": r"❌.*导入失败.*\n.*模块\s+(\w+)",
            "template": {
                "title": "修复导入错误: {module}",
                "description": "模块 {module} 导入失败，可能是路径问题或缺少依赖。",
                "type": ImprovementType.L3_BUG_FIX,
                "effort": "low",
                "impact": 0.9,
                "risk": 0.05,
                "hint": "检查 sys.path 配置、pip install 缺失包、或修正 ImportError。"
            }
        },
        {
            "pattern": "missing_test",
            "regex": r"模块\s+(\w+\.py)\s+缺少测试",
            "template": {
                "title": "补充测试覆盖: {module}",
                "description": "模块 {module} 缺少测试覆盖，建议创建 test_{module}。",
                "type": ImprovementType.L5_NEW_CAPABILITY,
                "effort": "medium",
                "impact": 0.5,
                "risk": 0.05,
                "hint": "参考 tests/test_calculator.py 模板创建新测试文件。"
            }
        },
        {
            "pattern": "deprecated_api",
            "regex": r"⚠️.*废弃.*(\w+)",
            "template": {
                "title": "更新废弃 API: {module}",
                "description": "模块 {module} 使用了废弃的 API，建议迁移到新接口。",
                "type": ImprovementType.L3_BUG_FIX,
                "effort": "low",
                "impact": 0.3,
                "risk": 0.1,
                "hint": "查阅对应库的最新文档，替换为推荐的新 API。"
            }
        },
    ]

    # ══════════════════════════════════════════════════════════
    # Phase 2 新增：优化模板库 ─ 算法/缓存/惰性加载/数据结构
    # ══════════════════════════════════════════════════════════

    OPTIMIZATION_TEMPLATES = [
        {
            "name": "lru_cache",
            "category": "缓存引入",
            "pattern_desc": "函数被重复调用且输入相同 → 添加 @lru_cache",
            "detect": lambda self, code: "def " in code and "lru_cache" not in code
                     and ("return " in code) and code.count("def ") >= 3,
            "template": {
                "title": "【{module}】添加 LRU 缓存加速",
                "description": (
                    "模块 {module} 中有多个纯函数（相同输入→相同输出），"
                    "添加 @functools.lru_cache 可避免重复计算，显著提升性能。"
                ),
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "low",
                "impact": 0.45,
                "risk": 0.08,
                "hint": (
                    "在函数定义上添加 @functools.lru_cache(maxsize=128)。"
                    "注意：仅适用于纯函数（无副作用，返回值仅依赖输入参数）。"
                ),
            }
        },
        {
            "name": "lazy_import",
            "category": "惰性加载",
            "pattern_desc": "模块顶层导入重量级库 → 改为函数内按需导入",
            "detect": lambda self, code: (
                "import numpy" in code or "import torch" in code
                or "import tensorflow" in code or "from sentence_transformers" in code
                or "import sentence_transformers" in code
            ) and code.strip().split("\n")[0].startswith(("import", "from")),
            "template": {
                "title": "【{module}】重量级库惰性加载",
                "description": (
                    "模块 {module} 在顶层导入了重量级库（numpy/torch/sentence-transformers），"
                    "导致首次导入耗时过长。建议改为函数内按需导入。"
                ),
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "low",
                "impact": 0.6,
                "risk": 0.1,
                "hint": (
                    "将重量级 import 语句移入使用该库的函数体内。"
                    "工具模块在 self_check 扫描时会被导入，顶层重量级导入会拖慢所有检查。"
                ),
            }
        },
        {
            "name": "json_preload",
            "category": "数据结构优化",
            "pattern_desc": "每次调用都读取完整 JSON 文件 → 预加载+增量更新",
            "detect": lambda self, code: _detect_json_preload(code),
            "template": {
                "title": "【{module}】JSON 数据预加载优化",
                "description": (
                    "模块 {module} 每次工具调用都完整读取 JSON 文件，"
                    "高频调用下 I/O 开销累积显著。建议改为启动时预加载+内存缓存+增量写入。"
                ),
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "medium",
                "impact": 0.5,
                "risk": 0.15,
                "hint": (
                    "在模块初始化时一次性 load JSON 到内存，每次工具调用从内存读取。"
                    "仅在数据变更时增量写入磁盘。使用 _dirty 标志避免无效写入。"
                ),
            }
        },
        {
            "name": "batch_io",
            "category": "算法替换",
            "pattern_desc": "循环内逐条读写文件 → 批量操作",
            "detect": lambda self, code: (
                "for " in code and ("write" in code or "read" in code)
                and "open(" in code
            ),
            "template": {
                "title": "【{module}】批量 I/O 优化",
                "description": (
                    "模块 {module} 在循环内逐条执行文件 I/O，"
                    "改为批量读写可大幅减少系统调用次数。"
                ),
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "medium",
                "impact": 0.55,
                "risk": 0.2,
                "hint": (
                    "将循环内的单条 write 累积到列表，循环结束后一次性 join+write。"
                    "或将多次 read 合并为一次完整读取后内存处理。"
                ),
            }
        },
        {
            "name": "set_lookup",
            "category": "算法替换",
            "pattern_desc": "列表 O(n) 查找 → 集合 O(1) 查找",
            "detect": lambda self, code: (
                "if " in code and " in " in code
                and ("list" in code or "[" in code)
                and " not in " not in code
            ),
            "template": {
                "title": "【{module}】集合查找优化",
                "description": (
                    "模块 {module} 使用列表进行成员检查（O(n)），"
                    "在数据量较大时性能退化明显。建议改用 set 或 dict（O(1) 查找）。"
                ),
                "type": ImprovementType.L2_PERF_OPT,
                "effort": "low",
                "impact": 0.35,
                "risk": 0.05,
                "hint": (
                    "将用于成员检查的 list 改为 set：seen = set() 替代 seen = []。"
                    "Python 中 set 的 in 操作是 O(1)，list 是 O(n)。"
                ),
            }
        },
        {
            "name": "error_handling",
            "category": "健壮性增强",
            "pattern_desc": "缺少 try-except 保护的 I/O 或网络操作",
            "detect": lambda self, code: (
                ("open(" in code or "request" in code or "urlopen" in code)
                and "try:" not in code
            ),
            "template": {
                "title": "【{module}】添加异常处理保护",
                "description": (
                    "模块 {module} 中的 I/O 或网络操作缺少 try-except 保护，"
                    "异常会直接传播导致工具调用失败。"
                ),
                "type": ImprovementType.L3_BUG_FIX,
                "effort": "low",
                "impact": 0.4,
                "risk": 0.05,
                "hint": (
                    "为文件/网络操作添加 try-except，捕获常见异常（FileNotFoundError, "
                    "TimeoutError, ConnectionError）并返回友好错误消息。"
                ),
            }
        },
        {
            "name": "thread_safety",
            "category": "架构改进",
            "pattern_desc": "共享可变全局状态 → 添加线程安全保护",
            "detect": lambda self, code: (
                "_data" in code and "=" in code
                and code.count("_data") >= 5
                and "threading" not in code
            ),
            "template": {
                "title": "【{module}】线程安全加固",
                "description": (
                    "模块 {module} 大量使用共享可变全局状态（_data），"
                    "多线程环境下可能出现竞态条件。建议添加 threading.Lock 保护。"
                ),
                "type": ImprovementType.L4_ARCH_REFACTOR,
                "effort": "medium",
                "impact": 0.3,
                "risk": 0.25,
                "hint": (
                    "为 _data 的读写操作添加 threading.Lock。"
                    "或改用 queue.Queue 实现线程安全的数据传递。"
                ),
            }
        },
        {
            "name": "config_externalize",
            "category": "架构改进",
            "pattern_desc": "硬编码配置 → 提取为可配置参数",
            "detect": lambda self, code: (
                any(str(n) in code for n in [5, 10, 20, 30, 50, 100])
                and code.count("=") >= 10
                and "class " in code
            ),
            "template": {
                "title": "【{module}】硬编码配置外部化",
                "description": (
                    "模块 {module} 包含多个硬编码的阈值和常量，"
                    "修改需要更改源码。建议提取为类属性或配置文件，便于调优。"
                ),
                "type": ImprovementType.L1_PARAM_TUNING,
                "effort": "low",
                "impact": 0.2,
                "risk": 0.05,
                "hint": (
                    "将硬编码数字提取为类属性：MAX_RETRIES = 3。"
                    "或在模块顶部定义配置常量块，集中管理所有可调参数。"
                ),
            }
        },
    ]

    def __init__(self):
        self._ideas: Dict[str, ImprovementIdea] = {}
        self._counter = 0
        self._load()

    # ── 创意生成入口 ────────────────────────────────────

    def generate_all(self, limit: int = 20) -> List[ImprovementIdea]:
        """从所有数据源生成改进创意，按优先级排序。"""
        ideas = []

        try:
            ideas.extend(self.from_monitor())
        except Exception as exc:
            pass  # 静默失败，不影响其他数据源

        try:
            ideas.extend(self.from_self_check())
        except Exception:
            pass

        try:
            ideas.extend(self.from_knowledge())
        except Exception:
            pass

        try:
            ideas.extend(self.from_static_analysis())
        except Exception:
            pass

        try:
            ideas.extend(self.from_code_analysis(max_ideas=limit))
        except Exception:
            pass

        # 去重
        seen = set()
        unique_ideas = []
        for idea in ideas:
            if idea.title not in seen:
                seen.add(idea.title)
                unique_ideas.append(idea)

        # 排除已尝试过（accepted/implemented/rejected）的创意，避免死循环重复选同一项
        tried_titles = {
            i.title for i in self._ideas.values()
            if getattr(i, "status", "proposed") in ("accepted", "implemented", "rejected")
        }
        unique_ideas = [i for i in unique_ideas if i.title not in tried_titles]

        # 按优先级排序
        unique_ideas.sort(key=lambda i: i.priority_score, reverse=True)

        return unique_ideas[:limit]

    # ── 从 monitor 生成 ────────────────────────────────

    def from_monitor(self) -> List[ImprovementIdea]:
        """分析 monitor 数据，生成性能优化创意。"""
        ideas = []

        try:
            from tools.monitor import _monitor
            data = _monitor._data
            tools_data = data.get("tools", {})

            # 1. 检测慢工具
            for tool_name, stats in tools_data.items():
                total_calls = stats.get("total_calls", 0)
                total_dur = stats.get("total_duration", 0)
                if total_calls > 0:
                    avg_ms = total_dur / total_calls * 1000
                    if avg_ms > 500:
                        idea = self._create_idea(
                            title=f"【{tool_name}】响应速度优化",
                            description=f"工具 {tool_name} 平均响应 {avg_ms:.0f}ms，超过 500ms 阈值。"
                                         f"（调用 {total_calls} 次）。建议添加缓存或优化内部算法。",
                            itype=ImprovementType.L2_PERF_OPT,
                            source="monitor",
                            target=tool_name,
                            effort="medium",
                            impact=min(0.9, avg_ms / 2000),
                            risk=0.2,
                            hint=f"检查 tools/{tool_name}.py 中是否有重复计算、不必要的 I/O 操作。考虑添加 @lru_cache。",
                            tags=["performance", "slow-tool", tool_name],
                        )
                        ideas.append(idea)

            # 2. 检测错误率
            total_calls = data.get("total_calls", 0)
            total_errors = data.get("total_errors", 0)
            if total_calls > 10:
                error_rate = total_errors / total_calls * 100
                if error_rate > 5:
                    idea = self._create_idea(
                        title="错误率过高 — 需排查根因",
                        description=f"系统错误率 {error_rate:.1f}%（{total_errors}/{total_calls}），"
                                     f"建议排查高频错误源。",
                        itype=ImprovementType.L3_BUG_FIX,
                        source="monitor",
                        target="monitor",
                        effort="medium",
                        impact=0.8,
                        risk=0.1,
                        hint="使用 monitor.errors() 查看错误详情，使用 auto_repair.diagnose() 自动诊断。",
                        tags=["bug", "error-rate"],
                    )
                    ideas.append(idea)

            # 3. 检测冷门工具
            for tool_name, stats in tools_data.items():
                total_calls = stats.get("total_calls", 0)
                if total_calls == 0 and tool_name not in ("monitor", "self_check", "safety_net"):
                    idea = self._create_idea(
                        title=f"冷门工具评估: {tool_name}",
                        description=f"工具 {tool_name} 近期零调用。建议评估是否可废弃或合并到其他工具中。",
                        itype=ImprovementType.L4_ARCH_REFACTOR,
                        source="monitor",
                        target=tool_name,
                        effort="low",
                        impact=0.2,
                        risk=0.1,
                        hint="检查该工具是否仍然有用，或已被子工具覆盖。废弃可减少维护负担。",
                        tags=["cleanup", "cold-tool", tool_name],
                    )
                    ideas.append(idea)

        except Exception:
            pass

        return ideas

    # ── 从 self_check 生成 ──────────────────────────────

    def from_self_check(self) -> List[ImprovementIdea]:
        """分析 self_check 结果，生成修复创意。"""
        ideas = []

        try:
            from tools.self_check import _checker
            result = _checker.check_all(verbose=False)
            lines = result.split("\n")

            for i, line in enumerate(lines):
                # 检测导入失败
                if "❌" in line and ("导入失败" in line or "import" in line.lower()):
                    # 尝试提取模块名
                    match = re.search(r'模块\s+["\']?(\w+)', line)
                    module = match.group(1) if match else "unknown"

                    idea = self._create_idea(
                        title=f"修复导入失败: {module}",
                        description=f"自检发现模块 {module} 导入失败: {line.strip()}",
                        itype=ImprovementType.L3_BUG_FIX,
                        source="self_check",
                        target=module,
                        effort="low",
                        impact=0.9,
                        risk=0.05,
                        hint=f"检查 tools/{module}.py 的依赖和 sys.path。"
                             f"如有 traceback，使用 auto_repair.diagnose() 分析。",
                        tags=["bug", "import-error", module],
                    )
                    ideas.append(idea)

                # 检测缺少测试
                if "缺少测试" in line or "无测试覆盖" in line:
                    match = re.search(r'(\w+\.py)', line)
                    module = match.group(1) if match else "unknown"

                    idea = self._create_idea(
                        title=f"补充测试覆盖: {module}",
                        description=f"自检发现 {module} 缺少测试覆盖。",
                        itype=ImprovementType.L5_NEW_CAPABILITY,
                        source="self_check",
                        target=module,
                        effort="medium",
                        impact=0.5,
                        risk=0.05,
                        hint=f"参考 tests/test_calculator.py 创建 tests/test_{module.replace('.py', '')}.py",
                        tags=["testing", "coverage", module],
                    )
                    ideas.append(idea)

        except Exception:
            pass

        return ideas

    # ── 从 knowledge 生成 ───────────────────────────────

    def from_knowledge(self) -> List[ImprovementIdea]:
        """分析知识库模式，生成改进创意。"""
        ideas = []

        try:
            from tools.knowledge_store import _store

            # 检查是否有未解决的错误模式
            error_entries = _store.search("错误 失败 bug 修复", max_results=10, mode="keyword")
            error_tags = set()
            for entry in error_entries:
                for tag in entry.get("tags", []):
                    error_tags.add(tag)

            # 如果频繁出现同类错误，建议系统化修复
            if len(error_entries) >= 3:
                common_tags = [t for t in error_tags if t in ["bug", "error", "修复", "失败"]]
                if common_tags:
                    idea = self._create_idea(
                        title="知识库错误模式聚合分析",
                        description=f"知识库中有 {len(error_entries)} 条与错误相关的记录。"
                                     f"建议聚合分析，找出高频根因并系统化修复。",
                        itype=ImprovementType.L3_BUG_FIX,
                        source="knowledge",
                        target="knowledge_store",
                        effort="medium",
                        impact=0.6,
                        risk=0.1,
                        hint="使用 knowledge.search('错误模式 根因分析') 汇总所有错误记录。",
                        tags=["bug", "knowledge", "pattern-analysis"],
                    )
                    ideas.append(idea)

        except Exception:
            pass

        return ideas

    # ── 静态分析 ────────────────────────────────────────

    def from_static_analysis(self) -> List[ImprovementIdea]:
        """对代码进行静态分析，生成改进创意。"""
        ideas = []

        try:
            tools_dir = SANDBOX_DIR / "tools"
            evolver_dir = SANDBOX_DIR / "evolver"

            # 检查大文件
            for directory in [tools_dir, evolver_dir]:
                if not directory.is_dir():
                    continue
                for py_file in directory.glob("*.py"):
                    try:
                        lines = len(py_file.read_text(encoding="utf-8").splitlines())
                        if lines > 800:
                            idea = self._create_idea(
                                title=f"大文件拆分: {py_file.name}",
                                description=f"{py_file.name} 有 {lines} 行代码，建议拆分为多模块。",
                                itype=ImprovementType.L4_ARCH_REFACTOR,
                                source="static_analysis",
                                target=py_file.name,
                                effort="high",
                                impact=0.4,
                                risk=0.35,
                                hint=f"按职责拆分：核心逻辑、工具函数、数据模型各自独立文件。",
                                tags=["refactor", "large-file", py_file.stem],
                            )
                            ideas.append(idea)
                    except Exception:
                        pass

        except Exception:
            pass

        return ideas

    # ══════════════════════════════════════════════════════════
    # Phase 2 新增：代码模式分析（优化模板匹配）
    # ══════════════════════════════════════════════════════════

    def from_code_analysis(self, max_ideas: int = 10) -> List[ImprovementIdea]:
        """扫描代码库，用优化模板库匹配改进机会。

        逐个检查 tools/ 和 evolver/ 下的 Python 文件，
        用 OPTIMIZATION_TEMPLATES 中的 detect 函数匹配模式。
        """
        ideas = []
        analyzed = 0

        for directory_name in ["tools", "evolver"]:
            directory = SANDBOX_DIR / directory_name
            if not directory.is_dir():
                continue

            for py_file in sorted(directory.glob("*.py")):
                if analyzed >= max_ideas * 2:  # 每个文件可能匹配多个模板
                    break

                try:
                    code = py_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                module_name = py_file.stem
                analyzed += 1

                for tmpl in self.OPTIMIZATION_TEMPLATES:
                    if len(ideas) >= max_ideas:
                        break

                    try:
                        if tmpl["detect"](self, code):
                            t = tmpl["template"]
                            idea = self._create_idea(
                                title=t["title"].format(module=module_name),
                                description=t["description"].format(module=module_name),
                                itype=t["type"],
                                source=f"code_analysis:{tmpl['name']}",
                                target=f"{directory_name}/{py_file.name}",
                                effort=t["effort"],
                                impact=t["impact"],
                                risk=t["risk"],
                                hint=t["hint"],
                                # 仅 json_preload 经 AST 精确验证前提，可安全自动执行；
                                # 其余模板（如 lru_cache）为粗粒度启发式，需人工确认前提
                                precondition_verified=(tmpl["name"] == "json_preload"),
                                tags=[
                                    "optimization", tmpl["name"],
                                    tmpl["category"], module_name,
                                ],
                            )
                            ideas.append(idea)
                    except Exception:
                        continue

        ideas.sort(key=lambda i: i.priority_score, reverse=True)
        return ideas[:max_ideas]

    def from_verified_optimizations(self, max_ideas: int = 20) -> List[ImprovementIdea]:
        """只返回前提已精确验证（precondition_verified=True）的优化创意。

        用于主动优化触发：只有 AST 精确验证前提的创意才允许自动执行，
        避免粗粒度启发式（如 lru_cache）误判导致的"无用功"。
        """
        ideas = self.from_code_analysis(max_ideas=max_ideas)
        return [i for i in ideas if i.precondition_verified]

    # ══════════════════════════════════════════════════════════
    # Phase 2 增强：创意评分器（收益预估 vs 风险量化）
    # ══════════════════════════════════════════════════════════

    def score_idea_advanced(
        self,
        idea: ImprovementIdea,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """对创意进行多维度高级评分。

        在基础优先级评分之上，额外考虑：
          - 历史成功率（同类型改进的成功率）
          - 模块稳定性（该模块的历史回滚率）
          - 当前系统健康度（健康低时降低风险偏好）
          - 改进紧迫度（monitor 数据中的严重程度）
        """
        context = context or {}

        # 基础分（已有）
        base_priority = idea.priority_score

        # 1. 历史成功率调整
        history_bonus = 0.0
        try:
            from evolver.cycle_tracker import _tracker
            patterns = _tracker.analyze_patterns()
            for p in patterns:
                if p.pattern_type == "what_works" and idea.improvement_type.value in p.description:
                    history_bonus = 0.1
                    break
                elif p.pattern_type == "what_fails" and idea.improvement_type.value in p.description:
                    history_bonus = -0.15
                    break
        except Exception:
            pass

        # 2. 系统健康度调整
        health_bonus = 0.0
        try:
            health = context.get("health_score", 80)
            if health < 60:
                health_bonus = -0.2  # 系统不稳定时降低所有自动改进的优先级
            elif health > 85:
                health_bonus = 0.1   # 系统健康时更愿意尝试
        except Exception:
            pass

        # 3. 紧迫度调整
        urgency_bonus = 0.0
        if idea.improvement_type == ImprovementType.L3_BUG_FIX:
            urgency_bonus = 0.15  # Bug 修复永远有较高紧迫度
        elif idea.source and "slow" in idea.source:
            urgency_bonus = 0.1

        # 综合调整
        adjusted_priority = max(0, min(1, base_priority + history_bonus + health_bonus + urgency_bonus))
        adjusted_confidence = max(0, min(1, idea.confidence + history_bonus * 0.5))

        return {
            "idea_id": idea.idea_id,
            "base_priority": round(base_priority, 3),
            "adjusted_priority": round(adjusted_priority, 3),
            "history_bonus": round(history_bonus, 3),
            "health_bonus": round(health_bonus, 3),
            "urgency_bonus": round(urgency_bonus, 3),
            "adjusted_confidence": round(adjusted_confidence, 3),
            "should_proceed": adjusted_priority > 0.15,
            "risk_level": "low" if idea.risk_score < 0.15 else (
                "medium" if idea.risk_score < 0.3 else "high"
            ),
        }

    # ── 创意辅助方法 ────────────────────────────────────

    def _create_idea(
        self,
        title: str,
        description: str,
        itype: ImprovementType,
        source: str,
        target: str,
        effort: str,
        impact: float,
        risk: float,
        hint: str = "",
        tags: List[str] | None = None,
        precondition_verified: bool = False,
    ) -> ImprovementIdea:
        """创建并评分一条改进创意。"""
        # 去重：相同 title 的创意已存在则复用，避免创意列表无限膨胀
        for _existing in self._ideas.values():
            if getattr(_existing, "title", "") == title:
                return _existing
        self._counter += 1
        idea_id = f"idea-{datetime.now().strftime('%Y%m%d')}-{self._counter:03d}"

        # 可行性评分
        effort_map = {"low": 0.9, "medium": 0.7, "high": 0.4}
        feasibility = effort_map.get(effort, 0.5)

        # 综合优先级 = 影响 * 可行性 * (1 - 风险)
        priority = impact * feasibility * (1 - risk)
        confidence = feasibility * 0.7 + (1 - risk) * 0.3

        idea = ImprovementIdea(
            idea_id=idea_id,
            title=title,
            description=description,
            improvement_type=itype,
            source=source,
            target_module=target,
            estimated_effort=effort,
            feasibility_score=round(feasibility, 2),
            impact_score=round(impact, 2),
            risk_score=round(risk, 2),
            priority_score=round(priority, 3),
            confidence=round(confidence, 2),
            implementation_hint=hint,
            precondition_verified=precondition_verified,
            tags=tags or [],
        )

        self._ideas[idea_id] = idea
        self._save()
        return idea

    # ── 创意管理 ────────────────────────────────────────

    def list_ideas(
        self,
        status: str = "",
        min_priority: float = 0,
        limit: int = 20,
    ) -> List[ImprovementIdea]:
        """列出已生成的创意。"""
        ideas = list(self._ideas.values())
        if status:
            ideas = [i for i in ideas if i.status == status]
        if min_priority > 0:
            ideas = [i for i in ideas if i.priority_score >= min_priority]
        ideas.sort(key=lambda i: i.priority_score, reverse=True)
        return ideas[:limit]

    def update_status(self, idea_id: str, status: str) -> bool:
        """更新创意状态。"""
        idea = self._ideas.get(idea_id)
        if not idea:
            return False
        idea.status = status
        self._save()
        return True

    def top_ideas(self, n: int = 5) -> List[ImprovementIdea]:
        """获取 Top-N 最高优先级创意。"""
        return self.list_ideas(status="proposed", min_priority=0.1, limit=n)

    # ── 持久化 ──────────────────────────────────────────

    def _save(self):
        filepath = IDEAS_DIR / "improvement_ideas.json"
        data = {iid: idea.to_dict() for iid, idea in self._ideas.items()}
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        filepath = IDEAS_DIR / "improvement_ideas.json"
        if not filepath.is_file():
            return
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            self._ideas = {iid: ImprovementIdea.from_dict(d) for iid, d in data.items()}
            if self._ideas:
                # 恢复 counter
                ids = [int(iid.split("-")[-1]) for iid in self._ideas.keys()
                       if iid.startswith("idea-") and iid.split("-")[-1].isdigit()]
                self._counter = max(ids) if ids else 0
        except (json.JSONDecodeError, KeyError, TypeError):
            self._ideas = {}


# ── 全局单例 ───────────────────────────────────────────────

_generator = ImprovementGenerator()


def get_generator() -> ImprovementGenerator:
    """获取改进创意生成器实例。"""
    return _generator


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "improvement_generator",
        "description": (
            "改进创意自动生成引擎。分析系统监控数据、自检结果和知识库，"
            "自动生成改进创意并按优先级排序。支持多种改进类型（L1参数调优~L5新能力）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["generate", "list", "top", "update_status", "from_monitor", "from_self_check", "from_code", "score_advanced"],
                    "description": (
                        "操作类型：generate — 全源生成创意并按优先级排序；"
                        "list — 列出已有创意；"
                        "top — Top-N 最高优先级创意；"
                        "update_status — 更新创意状态；"
                        "from_monitor — 仅从监控数据生成；"
                        "from_self_check — 仅从自检结果生成"
                    ),
                    "default": "generate",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制",
                    "default": 10,
                },
                "status": {
                    "type": "string",
                    "description": "按状态筛选: proposed / accepted / implemented / rejected",
                    "default": "",
                },
                "min_priority": {
                    "type": "number",
                    "description": "最低优先级阈值（0-1）",
                    "default": 0,
                },
                "idea_id": {
                    "type": "string",
                    "description": "创意 ID（update_status 时需要）",
                    "default": "",
                },
                "new_status": {
                    "type": "string",
                    "description": "新状态（update_status 时需要）",
                    "default": "",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


def execute_improvement_generator_tool(arguments: dict) -> str:
    """改进创意生成器工具入口。"""
    action = arguments.get("action", "generate")

    try:
        if action == "generate":
            limit = int(arguments.get("limit", 10))
            ideas = _generator.generate_all(limit=limit)
            if not ideas:
                return "🎉 系统运行良好，未发现需改进项。"

            lines = [f"💡 生成 {len(ideas)} 个改进创意（按优先级排序）:\n"]
            for i, idea in enumerate(ideas, 1):
                lines.append(
                    f"{i}. [{idea.priority_score:.3f}] [{idea.improvement_type.value}] {idea.title}"
                )
                lines.append(f"   置信度: {idea.confidence:.0%} | 影响: {idea.impact_score:.0%} | "
                            f"风险: {idea.risk_score:.0%} | 工作量: {idea.estimated_effort}")
                lines.append(f"   来源: {idea.source} | 目标: {idea.target_module}")
                if idea.implementation_hint:
                    lines.append(f"   💡 {idea.implementation_hint[:120]}")
                lines.append("")
            return "\n".join(lines)

        elif action == "list":
            limit = int(arguments.get("limit", 20))
            status = arguments.get("status", "")
            min_p = float(arguments.get("min_priority", 0))
            ideas = _generator.list_ideas(status=status, min_priority=min_p, limit=limit)
            if not ideas:
                return "📭 无匹配创意。"
            lines = [f"📋 创意列表 ({len(ideas)} 个):"]
            for idea in ideas:
                lines.append(
                    f"  [{idea.priority_score:.3f}] [{idea.improvement_type.value}] "
                    f"{idea.title} ({idea.status})"
                )
            return "\n".join(lines)

        elif action == "top":
            n = int(arguments.get("limit", 5))
            ideas = _generator.top_ideas(n)
            if not ideas:
                return "暂无建议创意。"
            lines = [f"🏆 Top-{len(ideas)} 改进建议:\n"]
            for i, idea in enumerate(ideas, 1):
                lines.append(f"{i}. [{idea.priority_score:.3f}] {idea.title}")
                lines.append(f"   {idea.description[:150]}")
            return "\n".join(lines)

        elif action == "update_status":
            idea_id = arguments.get("idea_id", "")
            new_status = arguments.get("new_status", "")
            if not idea_id or not new_status:
                return "请提供 idea_id 和 new_status"
            if _generator.update_status(idea_id, new_status):
                return f"✅ 创意 {idea_id} 状态已更新为: {new_status}"
            return f"❌ 未找到创意: {idea_id}"

        elif action == "from_monitor":
            ideas = _generator.from_monitor()
            lines = [f"📊 从监控数据生成 {len(ideas)} 个创意:"]
            for idea in ideas:
                lines.append(f"  • [{idea.priority_score:.3f}] {idea.title}")
            return "\n".join(lines)

        elif action == "from_self_check":
            ideas = _generator.from_self_check()
            lines = [f"🔧 从自检结果生成 {len(ideas)} 个创意:"]
            for idea in ideas:
                lines.append(f"  • [{idea.priority_score:.3f}] {idea.title}")
            return "\n".join(lines)

        elif action == "from_code":
            limit = int(arguments.get("limit", 10))
            ideas = _generator.from_code_analysis(max_ideas=limit)
            if not ideas:
                return "📭 代码分析未发现优化机会。"
            lines = [f"🔬 代码模式分析发现 {len(ideas)} 个优化机会:"]
            for idea in ideas:
                lines.append(
                    f"  [{idea.priority_score:.3f}] [{idea.improvement_type.value}] {idea.title}"
                )
                lines.append(f"    {idea.description[:120]}")
            return "\n".join(lines)

        elif action == "score_advanced":
            idea_id = arguments.get("idea_id", "")
            if not idea_id:
                # 对 top-5 评分
                ideas = _generator.top_ideas(5)
                if not ideas:
                    return "暂无创意可供评分。"
                lines = ["📊 高级评分（Top-5 创意）:\n"]
                for idea in ideas:
                    score = _generator.score_idea_advanced(idea)
                    lines.append(
                        f"  [{idea.title[:50]}] "
                        f"基础={score['base_priority']:.3f} → "
                        f"调整后={score['adjusted_priority']:.3f} "
                        f"({'✅ 推荐' if score['should_proceed'] else '⚠️ 不推荐'})"
                    )
                return "\n".join(lines)
            else:
                idea = _generator._ideas.get(idea_id)
                if not idea:
                    return f"未找到创意: {idea_id}"
                score = _generator.score_idea_advanced(idea)
                import json as _json
                return _json.dumps(score, ensure_ascii=False, indent=2)

        else:
            return f"未知操作: {action}。可用: generate, list, top, update_status, from_monitor, from_self_check"

    except Exception as exc:
        return f"改进创意生成器错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    gen = ImprovementGenerator()

    print("=== 从 monitor 生成创意 ===")
    monitor_ideas = gen.from_monitor()
    for idea in monitor_ideas:
        print(f"  [{idea.priority_score:.3f}] {idea.title} (confidence: {idea.confidence})")

    print("\n=== Top-5 综合创意 ===")
    all_ideas = gen.generate_all(limit=5)
    for idea in all_ideas:
        print(f"  [{idea.priority_score:.3f}] [{idea.improvement_type.value}] {idea.title}")
        print(f"    impact={idea.impact_score}, risk={idea.risk_score}, effort={idea.estimated_effort}")
        if idea.implementation_hint:
            print(f"    hint: {idea.implementation_hint[:80]}")
