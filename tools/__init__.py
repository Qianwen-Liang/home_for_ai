"""
Agent 1 工具系统
===============
可扩展的工具模块集合，用于增强智能体的能力。

v4.0 新增（从先进智能体学习）：
  - workflow_engine: 有状态工作流引擎（← LangGraph）
  - role_system: 多角色思维系统（← MetaGPT）
  - experience_learner: 自适应学习机制（← AutoGPT）
"""

from .calculator import Calculator, CalculationError
from .knowledge_store import KnowledgeStore, KnowledgeStoreError
from .task_tracker import TaskTracker, TaskStatus, TaskTrackerError, TaskPriority
from .file_utils import FileUtilsError
from .runner import RunnerError
from .self_check import HealthCheck
from .test_runner import TestRunner, TestRunnerError
from .monitor import Monitor, MonitorError
from .decision_engine import DecisionEngine, DecisionError
from .safety_net import SafetyNet, SafetyNetError
from .guardrails import (
    validate_params,
    with_retry,
    get_param,
    safe_execute,
    GuardrailsError,
)
from .workflow_engine import WorkflowEngine, WorkflowError
from .role_system import RoleSystem, RoleType, RoleSystemError
from .experience_learner import ExperienceLearner, ExperienceLearnerError
from .executor_registry import ExecutorRegistry, ExecutorRegistryError, get_registry, register_executor
from .retry_policy import RetryPolicy, RetryConfig, RetryExhaustedError, with_retry_policy, compute_backoff
from .checkpoint_backend import (
    StorageBackend,
    FileBackend,
    SQLiteBackend,
    create_backend,
)

__all__ = [
    "Calculator",
    "CalculationError",
    "KnowledgeStore",
    "KnowledgeStoreError",
    "TaskTracker",
    "TaskStatus",
    "TaskPriority",
    "TaskTrackerError",
    "FileUtilsError",
    "RunnerError",
    "HealthCheck",
    "TestRunner",
    "TestRunnerError",
    "Monitor",
    "MonitorError",
    "DecisionEngine",
    "DecisionError",
    "SafetyNet",
    "SafetyNetError",
    "validate_params",
    "with_retry",
    "get_param",
    "safe_execute",
    "GuardrailsError",
    "WorkflowEngine",
    "WorkflowError",
    "RoleSystem",
    "RoleType",
    "RoleSystemError",
    "ExperienceLearner",
    "ExperienceLearnerError",
    "ExecutorRegistry",
    "ExecutorRegistryError",
    "get_registry",
    "register_executor",
    "RetryPolicy",
    "RetryConfig",
    "RetryExhaustedError",
    "with_retry_policy",
    "compute_backoff",
    "StorageBackend",
    "FileBackend",
    "SQLiteBackend",
    "create_backend",
]
