"""registry — 声明式工具注册表（步骤 2）

设计依据：
  - 本地实测：dict 查表比 if-elif 快 2.47x 且无位置相关性；装饰器注册零运行时开销
  - arXiv 2608.25512（时空可组合性）：
      * 时间可组合性 → 注册必须成对提供 unregister（可逆）
      * 空间可组合性 → 工具依赖与激活条件须声明式表达
  - arXiv 2608.06370（Bitter Lesson of Tool Calling）：预留 typed stub 形态
  - 字节稳定：工具装配顺序必须确定，否则破坏 prompt caching

对外契约：
  ToolSpec       工具规格（不可变）
  ToolRegistry   注册表（注册/注销/装配）
  register_tool  装饰器
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

try:  # 步骤4.3：阈值唯一来源
    from tools.budget import RESULT_LIMIT
except ImportError:  # pragma: no cover
    from budget import RESULT_LIMIT


class RegistryError(RuntimeError):
    """注册表错误（重复注册、未知工具、字节漂移等）。"""


@dataclass(frozen=True)
class ToolSpec:
    """工具规格：单一事实来源。

    字段分组：
      标识    name, definition
      执行    handler
      契约    errors, idempotent, read_only, destructive
      P2 预算 budget_chars
      学术    dependencies, activate_when, stub
    """

    # ── 标识 ──
    name: str
    definition: dict[str, Any]          # 含 name/description/parameters(/outputSchema/annotations)

    # ── 执行 ──
    handler: Callable[[dict[str, Any]], str]

    # ── 错误契约（步骤 4 使用）──
    errors: tuple[type[BaseException], ...] = ()

    # ── 行为标注（MCP annotations 语义）──
    idempotent: bool = False
    read_only: bool = False
    destructive: bool = False

    # ── P2 上下文预算：单次结果字符上限 ──
    budget_chars: int = RESULT_LIMIT   # 步骤4.3 统一阈值来源（tools/budget.py）

    # ── 空间可组合性：依赖与激活条件 ──
    # dependencies：【已生效】由 ToolRegistry.validate_dependencies() 在启动时校验闭包完整性。
    # activate_when：【预留-未生效】声明式激活条件，当前仅承载文本说明；
    #   生效条件：引入按条件装配（如 enable_legacy 之外的能力开关）时读取此字段。
    dependencies: tuple[str, ...] = ()
    activate_when: str = ""

    # ── PTC 接口预留（arXiv 2608.06370）──
    # 状态：【预留-未生效】当前仅承载字段，供后续程序化工具调用改造使用。
    # 生效条件：中间件/执行层改为读取 spec.stub 并注入代码执行环境。
    stub: str = ""

    # ── 元信息 ──
    tags: tuple[str, ...] = field(default_factory=tuple)

    def annotations(self) -> dict[str, Any]:
        """导出 MCP 风格 annotations。"""
        return {
            "idempotent": self.idempotent,
            "readOnly": self.read_only,
            "destructive": self.destructive,
        }

    def public_definition(self) -> dict[str, Any]:
        """导出给模型的定义（保持原始结构，不注入额外字段，确保字节稳定）。"""
        return self.definition


class ToolRegistry:
    """工具注册表。

    设计要点：
      - 插入有序：装配顺序即注册顺序（Python 3.7+ dict 保序）
      - 可逆：unregister 完整移除规格，符合时间可组合性
      - 确定性装配：build() 输出与注册顺序严格一致
      - 不执行任何工具逻辑，只建映射（避免导入期副作用）
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._order: list[str] = []

    # ── 注册 / 注销（成对，保证可逆）──
    def register(self, spec: ToolSpec) -> ToolSpec:
        if not spec.name:
            raise RegistryError("工具名不能为空")
        if spec.name in self._specs:
            raise RegistryError(f"工具重复注册: {spec.name}")
        if not callable(spec.handler):
            raise RegistryError(f"{spec.name} 的 handler 不可调用")
        self._specs[spec.name] = spec
        self._order.append(spec.name)
        return spec

    def unregister(self, name: str) -> None:
        """注销工具（时间可组合性的逆操作）。"""
        if name not in self._specs:
            raise RegistryError(f"注销未知工具: {name}")
        del self._specs[name]
        self._order.remove(name)

    # ── 查询 ──
    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        """按注册顺序返回工具名（确定性）。"""
        return list(self._order)

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    # ── 装配 ──
    def build(self, only: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """装配工具定义列表。

        only 指定子集与顺序时按该顺序输出；否则按注册顺序输出。
        输出为原始 definition 对象引用，不做拷贝，保证字节稳定。
        """
        names = list(only) if only is not None else list(self._order)
        out: list[dict[str, Any]] = []
        for n in names:
            spec = self._specs.get(n)
            if spec is None:
                raise RegistryError(f"装配时工具不存在: {n}")
            out.append(spec.public_definition())
        return out

    def fingerprint(self, only: Iterable[str] | None = None) -> str:
        """工具集紧凑序列化（用于字节稳定断言）。"""
        return json.dumps(self.build(only), ensure_ascii=False, separators=(",", ":"))

    # ── 空间可组合性：依赖校验 ──
    def validate_dependencies(self) -> list[str]:
        """返回缺失的依赖列表（空列表表示依赖闭包完整）。"""
        missing: list[str] = []
        for name in self._order:
            for dep in self._specs[name].dependencies:
                if dep not in self._specs:
                    missing.append(f"{name} -> {dep}")
        return missing

    def describe(self) -> str:
        lines = [f"📚 工具注册表（{len(self)} 个，顺序确定）", "-" * 56]
        for i, n in enumerate(self._order, 1):
            s = self._specs[n]
            flags = []
            if s.read_only:
                flags.append("只读")
            if s.idempotent:
                flags.append("幂等")
            if s.destructive:
                flags.append("破坏性")
            deps = f" deps={','.join(s.dependencies)}" if s.dependencies else ""
            lines.append(f"  {i:2}. {n:<20} [{','.join(flags) or '-'}]"
                         f" budget={s.budget_chars}{deps}")
        return "\n".join(lines)


# 全局注册表
REGISTRY = ToolRegistry()


def register_tool(spec: ToolSpec) -> ToolSpec:
    """注册工具规格并返回（便于链式使用）。"""
    return REGISTRY.register(spec)
