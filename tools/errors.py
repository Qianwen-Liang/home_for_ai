"""errors — 统一错误契约（步骤 4）

设计依据（见步骤4调研）：
  1. gRPC 状态码的可重试性语义 —— 分层判据是「修复动作的代价」，不是「错误来自哪个模块」
       UNAVAILABLE        → RETRYABLE : 仅需重试本次调用
       FAILED_PRECONDITION→ REJECTED  : 需先修复输入或前置状态
       (其他不可恢复)      → FATAL     : 需人工介入环境/配置
  2. OTel GenAI 异常约定：事件名 gen_ai.client.operation.exception，严重级别 WARN
  3. arXiv 2602.02475 AgentRx：错误记录需携带**可审计证据**（类别+code+原始信息+触发约束）
  4. arXiv 2610.19342：除可重试性外，还应记录**失败阶段/位置**以支持归因

三层定义：
  RETRYABLE  可重试       —— 重试同一调用即可（网络抖动/超时/限流）
  REJECTED   业务拒绝     —— 需修复输入或前置状态（路径不存在/参数越界/前置未满足）
  FATAL      致命         —— 需人工介入（配置缺失/环境损坏/内部缺陷）

优先级规则（解决三层边界模糊）：
  同时具备多种特征时，按 FATAL > REJECTED > RETRYABLE 取最保守者。
  理由：宁可让人看到严重问题，也不要静默重试掩盖根因。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ErrorCategory(str, Enum):
    """错误三层（与 gRPC 可重试性语义对齐）。"""
    RETRYABLE = "RETRYABLE"
    REJECTED = "REJECTED"
    FATAL = "FATAL"


# 保守优先：数值越大越严重，用于多特征冲突时取最保守
_SEVERITY = {ErrorCategory.RETRYABLE: 1, ErrorCategory.REJECTED: 2, ErrorCategory.FATAL: 3}

# OTel 严重级别（WARN = 13），证据事件沿用此约定
OTEL_WARN_SEVERITY = 13
OTEL_EXCEPTION_EVENT = "gen_ai.client.operation.exception"


@dataclass(frozen=True)
class ErrorEvidence:
    """可审计的错误证据（AgentRx 风格）。"""
    error_class: str
    category: ErrorCategory
    error_code: str
    message: str
    phase: str = ""          # 失败阶段/位置（arXiv 2610.19342）
    retryable: bool = False
    constraint: str = ""     # 触发约束（AgentRx 的 constraint violation）

    def to_otel_event(self) -> dict:
        """导出为 OTel GenAI 兼容的异常事件。"""
        return {
            "event": OTEL_EXCEPTION_EVENT,
            "severity_number": OTEL_WARN_SEVERITY,
            "attributes": {
                "error.type": self.error_class,
                "error.category": self.category.value,
                "error.code": self.error_code,
                "error.message": self.message[:300],
                "error.phase": self.phase,
                "error.retryable": self.retryable,
            },
        }


# ── 错误分类规则表（35 种错误 → 三层）─────────────────────
# 键为错误类名；值为 (类别, 稳定错误码, 失败阶段)
# 依据：可重试性由「修复动作代价」决定
ERROR_MAP: dict[str, tuple[ErrorCategory, str, str]] = {
    # ── RETRYABLE：重试同一调用即可 ──
    "WebSearchError":        (ErrorCategory.RETRYABLE, "search.network", "execute"),
    "SourceError":           (ErrorCategory.RETRYABLE, "source.network", "execute"),
    "RetryExhaustedError":   (ErrorCategory.RETRYABLE, "retry.exhausted", "execute"),
    "DeepSeekAPIError":      (ErrorCategory.RETRYABLE, "llm.api", "inference"),

    # ── REJECTED：需先修复输入或前置状态 ──
    "ReadToolError":         (ErrorCategory.REJECTED, "io.read.rejected", "validate"),
    "WriteToolError":        (ErrorCategory.REJECTED, "io.write.rejected", "validate"),
    "RunnerError":           (ErrorCategory.REJECTED, "exec.command.rejected", "validate"),
    "CalculationError":      (ErrorCategory.REJECTED, "calc.expression.invalid", "validate"),
    "KnowledgeStoreError":   (ErrorCategory.REJECTED, "knowledge.rejected", "validate"),
    "TaskTrackerError":      (ErrorCategory.REJECTED, "task.rejected", "validate"),
    "ArtifactValidatorError":(ErrorCategory.REJECTED, "artifact.invalid", "validate"),
    "GuardrailsError":       (ErrorCategory.REJECTED, "guardrail.blocked", "validate"),
    "RegistryError":         (ErrorCategory.REJECTED, "registry.rejected", "validate"),
    "CapsuleError":          (ErrorCategory.REJECTED, "capsule.rejected", "validate"),

    # ── FATAL：需人工介入 ──
    "TestRunnerError":       (ErrorCategory.FATAL, "test.runner.broken", "execute"),
    "MonitorError":          (ErrorCategory.FATAL, "monitor.broken", "execute"),
    "SafetyNetError":        (ErrorCategory.FATAL, "safety.broken", "execute"),
    "DecisionError":         (ErrorCategory.FATAL, "decision.broken", "execute"),
    "OfflineError":          (ErrorCategory.FATAL, "offline.broken", "execute"),
    "CheckpointError":       (ErrorCategory.FATAL, "checkpoint.broken", "execute"),
    "SpecialistError":       (ErrorCategory.FATAL, "specialist.broken", "execute"),
    "AgentProfileError":     (ErrorCategory.FATAL, "profile.broken", "execute"),
    "DispatchError":         (ErrorCategory.FATAL, "dispatch.broken", "execute"),
    "OrchestratorError":     (ErrorCategory.FATAL, "orchestrator.broken", "execute"),
    "AutoRepairError":       (ErrorCategory.FATAL, "repair.broken", "execute"),
    "RepairConfidenceTooLowError": (ErrorCategory.FATAL, "repair.low_confidence", "execute"),
    "FileUtilsError":        (ErrorCategory.FATAL, "fileutils.broken", "execute"),
    "VillagerError":         (ErrorCategory.FATAL, "villager.broken", "execute"),
    "MessageBusError":       (ErrorCategory.FATAL, "bus.broken", "execute"),
    "WorkflowError":         (ErrorCategory.FATAL, "workflow.broken", "execute"),
    "AgentManagerError":     (ErrorCategory.FATAL, "manager.broken", "execute"),
    "ExecutorRegistryError": (ErrorCategory.FATAL, "executor.broken", "execute"),
    "ExperienceLearnerError":(ErrorCategory.FATAL, "learner.broken", "execute"),
    "RoleSystemError":       (ErrorCategory.FATAL, "role.broken", "execute"),
    "ChatError":             (ErrorCategory.FATAL, "chat.broken", "execute"),
    "BrokenToolError":       (ErrorCategory.FATAL, "tool.broken", "execute"),

    # ── Python 内置异常（★T2822 补全）──────────────────────
    # 原表 36 种全是项目自定义异常，内置异常只能落到启发式或 FATAL。
    # 实测 OSError 被判为 FATAL 就是这里缺项——文件/权限类问题
    # 明明属于「改输入或前置状态」即可修复，却报成需人工介入。
    "TimeoutError":          (ErrorCategory.RETRYABLE, "builtin.timeout", "execute"),
    "ConnectionError":       (ErrorCategory.RETRYABLE, "builtin.connection", "execute"),
    "ConnectionResetError":  (ErrorCategory.RETRYABLE, "builtin.connection.reset", "execute"),
    "FileNotFoundError":     (ErrorCategory.REJECTED, "builtin.notfound", "validate"),
    "PermissionError":       (ErrorCategory.REJECTED, "builtin.permission", "validate"),
    "IsADirectoryError":     (ErrorCategory.REJECTED, "builtin.isdir", "validate"),
    "NotADirectoryError":    (ErrorCategory.REJECTED, "builtin.notdir", "validate"),
    "FileExistsError":       (ErrorCategory.REJECTED, "builtin.exists", "validate"),
    "OSError":               (ErrorCategory.REJECTED, "builtin.os", "execute"),
    "ValueError":            (ErrorCategory.REJECTED, "builtin.value", "validate"),
    "UnicodeDecodeError":    (ErrorCategory.REJECTED, "builtin.unicode", "validate"),
    # 以下属调用方/实现缺陷，需人工修代码
    "TypeError":             (ErrorCategory.FATAL, "builtin.type", "validate"),
    "KeyError":              (ErrorCategory.FATAL, "builtin.key", "execute"),
    "AttributeError":        (ErrorCategory.FATAL, "builtin.attribute", "execute"),
    "IndexError":            (ErrorCategory.FATAL, "builtin.index", "execute"),
    "ZeroDivisionError":     (ErrorCategory.FATAL, "builtin.zerodiv", "execute"),
    "RuntimeError":          (ErrorCategory.FATAL, "builtin.runtime", "execute"),
}

_DEFAULT = (ErrorCategory.FATAL, "unknown.error", "execute")


def classify(exc: BaseException) -> tuple[ErrorCategory, str, str]:
    """按类名查表分类；未登记者归 FATAL（保守优先）。"""
    name = type(exc).__name__
    if name in ERROR_MAP:
        return ERROR_MAP[name]
    # 按名字启发式兜底（新增错误类型未登记时）
    low = name.lower()
    if any(k in low for k in ("timeout", "network", "connection", "rate", "limit")):
        return ErrorCategory.RETRYABLE, "heuristic.network", "execute"
    if any(k in low for k in ("path", "reject", "invalid", "argument", "notfound")):
        return ErrorCategory.REJECTED, "heuristic.rejected", "validate"
    return _DEFAULT


def classify_result(text: str) -> tuple[ErrorCategory, str, str]:
    """从工具**返回文本**推断错误类别（T2822 新增）。

    为什么需要它：
      agent1 把失败的工具返回包装成 `RuntimeError(result[:120])` 交给中间件，
      而 RuntimeError 不在 ERROR_MAP 中，启发式也匹配不到——于是**所有失败都被
      归为 FATAL**，"该重试"和"该改参数"的区分完全丢失。
      本函数直接从返回文本判断，恢复这层语义。

    外部依据：MCP SEP-1303 (Final) 要求工具参数校验失败必须作为
    Tool Execution Error 返回给模型。类别判断正确，模型才知道该重试还是该改输入。

    注意：只对**已判定失败**的返回调用。像 knowledge 搜索的"未找到结果"
    是合法空结果而非错误，故 "未找到" 不在 REJECTED 关键词里。
    """
    low = (text or "").lower()

    # RETRYABLE：重试同一调用可能成功
    for kw in ("超时", "timeout", "限流", "rate limit", "rate_limit",
               "连接失败", "连接被", "connection", "暂时不可用", "temporarily",
               "网络", "network"):
        if kw in low:
            return ErrorCategory.RETRYABLE, "result.retryable", "execute"

    # REJECTED：需先修复输入或前置状态
    for kw in ("路径不存在", "不存在", "不能为空", "参数", "越界",
               "拒绝", "rejected", "invalid", "缺少", "不支持", "非法",
               "未授权", "越权", "格式错误"):
        if kw in low:
            return ErrorCategory.REJECTED, "result.rejected", "validate"

    # FATAL：需人工介入
    return ErrorCategory.FATAL, "result.fatal", "execute"


def make_evidence(exc: BaseException, *, phase: str = "", constraint: str = "") -> ErrorEvidence:
    """构造可审计错误证据。"""
    cat, code, mapped_phase = classify(exc)
    return ErrorEvidence(
        error_class=type(exc).__name__,
        category=cat,
        error_code=code,
        message=str(exc),
        phase=phase or mapped_phase,
        retryable=(cat is ErrorCategory.RETRYABLE),
        constraint=constraint,
    )


def category_of(exc: BaseException) -> str:
    """便捷：返回类别字符串（供中间件/主循环使用）。"""
    return classify(exc)[0].value


def coverage_report() -> str:
    """分类覆盖率报告（供审计）。"""
    from collections import Counter
    c = Counter(v[0].value for v in ERROR_MAP.values())
    lines = [f"错误映射表：{len(ERROR_MAP)} 种",
             f"  RETRYABLE {c.get('RETRYABLE', 0)} 种",
             f"  REJECTED  {c.get('REJECTED', 0)} 种",
             f"  FATAL     {c.get('FATAL', 0)} 种"]
    return "\n".join(lines)
