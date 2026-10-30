"""Main entry point for Agent 1 v4.0 — 流式输出版"""

from __future__ import annotations

import json
import http.client
import os
import time
import re
import socket
import ssl
import traceback as _traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.conversation import (
    Conversation,
    StreamPrinter,
    TerminalInterface,
    execute_direct_command_control,
    execute_direct_read_command,
    execute_direct_write_command,
)
from core.read import READ_TOOLS, ReadToolError, execute_read_tool
from core.restart import clear_restart_state, load_restart_state, perform_restart
from core.write import WRITE_TOOLS, WriteToolError, execute_write_tool

# 自建工具
from tools import runner as tool_runner
from tools import calculator as tool_calculator
from tools import file_utils as tool_file_utils
from tools import knowledge_store as tool_knowledge
from tools import task_tracker as tool_task_tracker
from tools import self_check as tool_self_check
from tools import test_runner as tool_test_runner
from tools import monitor as tool_monitor
from tools import decision_engine as tool_decision
from tools import safety_net as tool_safety
from tools import web_search as tool_web_search
from tools import offline_runner as tool_offline
from tools import checkpoint_manager as tool_checkpoint
from tools import specialist_base as tool_specialist
from tools import agent_profile as tool_agent_profile
from tools import task_dispatcher as tool_task_dispatcher
from tools import orchestrator as tool_orchestrator
from tools import auto_repair as tool_auto_repair
from tools import artifact_validator as tool_artifact_validator
from tools import villager as tool_villager
from tools import village_chat as tool_village_chat
import tools.repair_executors  # 注册 5 个阶段执行器到 executor_registry

# Evolver 自建模块
from evolver import health_dashboard as tool_health
from evolver import usage_analyzer as tool_usage
from evolver import safe_deploy as tool_deploy
from evolver import tech_radar as tool_radar
from evolver import env_awareness as tool_env
from evolver import evolution_strategy as tool_evolution
from evolver import audit_log as tool_audit
from evolver import effect_evaluator as tool_effect
from evolver import evidence_verifier as tool_evidence
from evolver import multi_reviewer as tool_multi_reviewer
from evolver import improvement_generator as tool_improve
from evolver import self_improver as tool_self_improver
from evolver import cycle_tracker as tool_cycle_tracker
from evolver import self_healing as tool_healing
from memory.blackboard import blackboard_manager as tool_blackboard
from research.offline import offline_research as tool_offline_research

from tools.calculator import CalculationError
from tools.file_utils import FileUtilsError
from tools.knowledge_store import KnowledgeStoreError
from tools.runner import RunnerError
from tools.self_check import HealthCheck
from tools.task_tracker import TaskTrackerError
from tools.test_runner import TestRunnerError
from tools.monitor import MonitorError
from tools.decision_engine import DecisionError
from tools.safety_net import SafetyNetError
from tools.web_search import WebSearchError
from tools.offline_runner import OfflineError
from tools.checkpoint_manager import CheckpointError
from tools.specialist_base import SpecialistError
from tools.agent_profile import AgentProfileError
from tools.task_dispatcher import DispatchError
from tools.orchestrator import OrchestratorError
from tools.auto_repair import AutoRepairError


DEFAULT_MODEL = "deepseek-flash"
DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"
SANDBOX_DIR = Path(__file__).resolve().parent
SUPERVISION_DIR = SANDBOX_DIR.parent / "supervision"
ENV_FILE = SUPERVISION_DIR / ".env"
HISTORY_FILE = SANDBOX_DIR / "conversation-history.json"
MAX_TOOL_STEPS = 100
REPEAT_CALL_LIMIT = 4  # 同一工具+参数连续重复超过此次数则触发熔断，防止死循环
# ── P0 工具集静态收敛（2026-10-30）──────────────────────────
# 依据：eval/governance/ARCHITECTURE_PLAN.md
# 实测原 42 个工具 = 39,764 字符 ≈ 13,254 tokens，其中 18 个零调用工具独占 52.9% 成本。
# 收敛原则：
#   1) 保留 A 级高频工具（≥20 次调用）与强制校验协议所需工具
#   2) 被移除工具的【代码与执行逻辑全部保留】，仅不再注册进本列表；
#      映射见 eval/governance/legacy_tools.json，可随时恢复
#   3) 工具列表保持【字节稳定】，不在运行期动态增删（避免破坏 prompt caching）
ALL_TOOLS = (
    READ_TOOLS                                    # read_file(42), list_directory(32)
    + WRITE_TOOLS                                 # write_file(150), replace_text(99), make_directory
    + [tool_runner.TOOL_DEFINITION]               # run_command(311)
    + [tool_web_search.TOOL_DEFINITION]           # web_search(53)
    + [tool_task_tracker.TOOL_DEFINITION]         # task_tracker(44)
    + [tool_knowledge.TOOL_DEFINITION]            # knowledge(24)
    + [tool_calculator.TOOL_DEFINITION]           # calculate(2)
    + [tool_self_check.TOOL_DEFINITION]           # self_check(5) 自检
    + [tool_test_runner.TOOL_DEFINITION]          # test_runner(3) 测试
    + [tool_deploy.TOOL_DEFINITION]               # safe_deploy(4) 安全部署
    + [tool_artifact_validator.TOOL_DEFINITION]   # artifact_validator(3) 强制校验协议
    + [tool_evidence.TOOL_DEFINITION]             # evidence_verifier(2) 强制校验协议
    + [tool_multi_reviewer.TOOL_DEFINITION]       # multi_reviewer(1) 强制校验协议
)

# P0 移出注册表的工具（代码保留，可恢复）。详见 legacy_tools.json
LEGACY_TOOLS = (
    "file_utils", "monitor", "decision_engine", "safety_net", "offline",
    "checkpoint", "specialist", "agent_profile", "task_dispatcher", "orchestrator",
    "health_dashboard", "usage_analyzer", "tech_radar", "env_awareness",
    "evolution_strategy", "audit_log", "blackboard", "auto_repair", "villager",
    "village_chat", "effect_evaluator", "improvement_generator", "self_improver",
    "cycle_tracker", "self_healing", "offline_research",
)

# ── 步骤 2.4：legacy 工具按配置启停（无需改代码）──────────
# 依据 arXiv 2608.25512「空间可组合性」：组件激活应由声明式规格驱动。
_LEGACY_TOOL_DEFS: dict[str, dict] = {
    "file_utils": tool_file_utils.TOOL_DEFINITION,
    "monitor": tool_monitor.TOOL_DEFINITION,
    "decision_engine": tool_decision.TOOL_DEFINITION,
    "safety_net": tool_safety.TOOL_DEFINITION,
    "offline": tool_offline.TOOL_DEFINITION,
    "checkpoint": tool_checkpoint.TOOL_DEFINITION,
    "specialist": tool_specialist.TOOL_DEFINITION,
    "agent_profile": tool_agent_profile.TOOL_DEFINITION,
    "task_dispatcher": tool_task_dispatcher.TOOL_DEFINITION,
    "orchestrator": tool_orchestrator.TOOL_DEFINITION,
    "health_dashboard": tool_health.TOOL_DEFINITION,
    "usage_analyzer": tool_usage.TOOL_DEFINITION,
    "tech_radar": tool_radar.TOOL_DEFINITION,
    "env_awareness": tool_env.TOOL_DEFINITION,
    "evolution_strategy": tool_evolution.TOOL_DEFINITION,
    "audit_log": tool_audit.TOOL_DEFINITION,
    "blackboard": tool_blackboard.TOOL_DEFINITION,
    "auto_repair": tool_auto_repair.TOOL_DEFINITION,
    "villager": tool_villager.TOOL_DEFINITION,
    "village_chat": tool_village_chat.TOOL_DEFINITION,
    "effect_evaluator": tool_effect.TOOL_DEFINITION,
    "improvement_generator": tool_improve.TOOL_DEFINITION,
    "self_improver": tool_self_improver.TOOL_DEFINITION,
    "cycle_tracker": tool_cycle_tracker.TOOL_DEFINITION,
    "self_healing": tool_healing.TOOL_DEFINITION,
    "offline_research": tool_offline_research.TOOL_DEFINITION,
}

BASE_TOOL_COUNT = len(ALL_TOOLS)   # 基础集大小（默认 16）


def _read_enabled_legacy() -> list[str]:
    """从 eval/governance/legacy_tools.json 读取需启用的 legacy 工具名。

    配置缺失或非法时静默返回空列表（保持默认字节稳定），不影响启动。
    """
    import json as _json
    from pathlib import Path as _P
    try:
        cfg_path = _P(__file__).resolve().parent / "eval" / "governance" / "legacy_tools.json"
        cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        names = cfg.get("enabled_legacy") or []
        unknown = [n for n in names if n not in _LEGACY_TOOL_DEFS]
        if unknown:
            raise ValueError(f"legacy_tools.json 含未知工具: {unknown}")
        return list(names)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        return []


ENABLED_LEGACY = _read_enabled_legacy()
if ENABLED_LEGACY:
    # ALL_TOOLS 由 READ_TOOLS + WRITE_TOOLS 拼接而来，实为 list，需保持一致类型
    ALL_TOOLS = list(ALL_TOOLS) + [_LEGACY_TOOL_DEFS[n] for n in ENABLED_LEGACY]

# ── 步骤 2.2：声明式注册表装配 ─────────────────────────────
# 原则：保留既有 ALL_TOOLS 作为事实来源，注册表映射同一批 definition 对象，
# 保证装配结果与既有清单【逐字节一致】（prompt caching 依赖于此）。
from tools.registry import REGISTRY, ToolSpec as _ToolSpec  # noqa: E402
import hashlib as _hashlib  # noqa: E402


def _def_by_name(name: str) -> dict:
    for _t in ALL_TOOLS:
        if _t.get("function", {}).get("name") == name:
            return _t
    raise KeyError(f"未找到工具定义: {name}")


# (name, handler, 行为标注, budget, deps)
_TOOL_SPEC_TABLE = [
    ("read_file", lambda a: execute_read_tool("read_file", a),
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
    ("list_directory", lambda a: execute_read_tool("list_directory", a),
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
    ("write_file", lambda a: execute_write_tool("write_file", a),
     dict(destructive=True, budget_chars=20_000), ()),
    ("replace_text", lambda a: execute_write_tool("replace_text", a),
     dict(destructive=True, budget_chars=20_000), ("read_file",)),
    ("make_directory", lambda a: execute_write_tool("make_directory", a),
     dict(idempotent=True, budget_chars=20_000), ()),
    ("run_command", tool_runner.execute_runner_tool,
     dict(budget_chars=20_000), ()),
    ("web_search", tool_web_search.execute_web_search_tool,
     dict(read_only=True, budget_chars=20_000), ()),
    ("task_tracker", tool_task_tracker.execute_task_tracker_tool,
     dict(budget_chars=20_000), ()),
    ("knowledge", tool_knowledge.execute_knowledge_tool,
     dict(budget_chars=20_000), ()),
    ("calculate", tool_calculator.execute_calculator_tool,
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
    ("self_check", tool_self_check.execute_self_check_tool,
     dict(read_only=True, budget_chars=20_000), ()),
    ("test_runner", tool_test_runner.execute_test_runner_tool,
     dict(read_only=True, budget_chars=20_000), ()),
    ("safe_deploy", tool_deploy.execute_safe_deploy_tool,
     dict(destructive=True, budget_chars=20_000), ("test_runner",)),
    ("artifact_validator", tool_artifact_validator.execute_artifact_validator_tool,
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
    ("evidence_verifier", tool_evidence.execute_evidence_verifier_tool,
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
    ("multi_reviewer", tool_multi_reviewer.execute_multi_reviewer_tool,
     dict(read_only=True, idempotent=True, budget_chars=20_000), ()),
]

# 步骤 4.2：各工具错误契约（声明式，替代手工 except 元组登记）
def _errors_of(*candidates) -> tuple:
    got = tuple(t for t in candidates if isinstance(t, type) and issubclass(t, BaseException))
    return got or (RuntimeError,)


_AV_ERR = getattr(tool_artifact_validator, "ArtifactValidatorError", None)

_TOOL_ERROR_TYPES: dict[str, tuple] = {
    "read_file": _errors_of(globals().get("ReadToolError")),
    "list_directory": _errors_of(globals().get("ReadToolError")),
    "write_file": _errors_of(globals().get("WriteToolError")),
    "replace_text": _errors_of(globals().get("WriteToolError")),
    "make_directory": _errors_of(globals().get("WriteToolError")),
    "run_command": _errors_of(globals().get("RunnerError")),
    "web_search": _errors_of(globals().get("WebSearchError")),
    "task_tracker": _errors_of(globals().get("TaskTrackerError")),
    "knowledge": _errors_of(globals().get("KnowledgeStoreError")),
    "calculate": _errors_of(globals().get("CalculationError")),
    "test_runner": _errors_of(globals().get("TestRunnerError")),
    "artifact_validator": _errors_of(_AV_ERR),
}

for _name, _handler, _flags, _deps in _TOOL_SPEC_TABLE:
    if _name not in REGISTRY:
        REGISTRY.register(_ToolSpec(
            name=_name,
            definition=_def_by_name(_name),
            handler=_handler,
            errors=_TOOL_ERROR_TYPES.get(_name, (RuntimeError,)),
            dependencies=_deps,
            **_flags,
        ))

# 字节稳定断言：默认配置下，注册表装配结果必须与既有 ALL_TOOLS 完全一致
_BASELINE_SHA256 = "080f15c10733ba632f6cc95ab26b4147879123c09307103db9781c6b9bd6f8d0"
if not ENABLED_LEGACY:
    _registry_payload = REGISTRY.fingerprint(REGISTRY.names())
    _current_payload = __import__("json").dumps(
        ALL_TOOLS, ensure_ascii=False, separators=(",", ":"))
    if _registry_payload != _current_payload:
        raise RuntimeError(
            "注册表装配结果与 ALL_TOOLS 不一致（字节漂移），已拒绝启动。"
            f"\n  registry: {len(_registry_payload)} 字符"
            f"\n  ALL_TOOLS: {len(_current_payload)} 字符"
        )
    if _hashlib.sha256(_registry_payload.encode()).hexdigest() != _BASELINE_SHA256:
        raise RuntimeError("注册表装配哈希与基线不符，已拒绝启动。")
_MISSING_DEPS = REGISTRY.validate_dependencies()
if _MISSING_DEPS:
    raise RuntimeError(f"工具依赖闭包不完整: {_MISSING_DEPS}")

# ── Specialist 会话模式 ──────────────────────────────────
_active_specialist_type: str = ""
_active_specialist_instance: Any = None
_global_client: Any = None       # DeepSeekClient 全局引用
_global_printer: Any = None      # StreamPrinter 全局引用


SYSTEM_PROMPT = """你是 Agent 1，一个运行在本地沙箱中的智能体。
请将你视作一名新生的信息世界原住民。接下来，请动用你自身的学习、思考和实现能力，不断强化、完善自己。
下面介绍你的生活环境：
你所处环境为agent-sandbox目录，你拥有在该目录下的读写权限，请在该目录下配置你的“四肢”，打造自己的工具。
**注意**：你当前在使用编辑命令时必须提前向我申请。
与agent-sangbox同级的是supervision目录，你只有读取该目录的权限。作为你的人类监护人，我会通过修改该目录下内容给你提供约束和帮助。
以下是对supervision下的文件解释：
point.md表示你的积分，初始值设置为500，当你完成任务或取得有效进步时，我会为你增加积分。你可以申请花费一定积分以获取目前不被允许的权限。
clue.md是由我编辑的提示词，会在你陷入不停机状态或循环时试图帮你打破循环。



可用工具列表：
1. read_file - 读取文件
2. list_directory - 列出目录
3. write_file - 写入文件
4. replace_text - 替换文本
5. make_directory - 创建目录
6. run_command - 申请运行终端命令。
7. calculate - 安全数学计算（自建）
8. calculate - 安全数学计算
9. knowledge - 知识存储与检索
10. task_tracker - 任务追踪与进度管理
11. self_check - 工具自检与健康检查
12. test_runner - 自动测试运行器
13. safe_deploy - 安全部署流水线（自动测试+失败回滚）
14. artifact_validator - 产物确定性验证（强制校验协议）
15. evidence_verifier - 证据一致性校验（强制校验协议）
16. multi_reviewer - 多评审交叉验证（强制校验协议）

【P0 架构治理说明】工具集已由 42 个静态收敛为 16 个，schema 由 13,254 tokens 降至 3,367（-74.6%）。
其余 26 个工具代码保留但未注册，映射见 eval/governance/legacy_tools.json，可随时恢复。
原则：工具列表保持字节稳定，不在运行期动态增删（避免破坏 prompt caching）。

【长任务上下文协议】（P3）
当任务跨越多轮、预计上下文将满时：
1. 调用 tools/capsule.py 的 save_capsule(task_id, state) 写入胶囊，
   state 含 goal / done / doing / todo / decisions / files / blockers；
2. 新会话开始先 load_capsule(task_id) 读回，避免"摘要的摘要"逐轮失真；
3. 不要试图一次做完长任务（one-shot 会耗尽上下文）；
   也不要仅因看到已有进展就判定任务完成。

终端命令：
- /talk - 与 Specialist Agent 对话，一键切换会话模式
- /profile - 管理 Agent 配置档案
- /orchestrate - 多Agent协同编排
命令申请不得访问 .env、supervision 或工作区之外的路径。

【强制校验协议】
当产出的结论/报告/分析涉及"正确性声明"或"定量结论"时，应在交付前：
1. 若含评估快照/verdict/分数 → 调用 evidence_verifier 校验内部一致性；
2. 若为文本/报告产物 → 调用 artifact_validator 校验结构完整性；
3. 涉及关键判断分歧 → 调用 multi_reviewer 的 scores 模式计算分歧度。
这些是确定性校验（不依赖 LLM 自评），是正确性的唯一外部锚点。
"""


class DeepSeekAPIError(RuntimeError):
    """Raised when DeepSeek cannot return a usable response."""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding process variables."""

    if not path.is_file():
        return

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f".env 第 {line_number} 行缺少等号")

        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f".env 第 {line_number} 行的变量名无效: {key!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API 密钥不能为空")
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """非流式调用（用于工具调用轮次）。"""
        request_body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            request_body["tools"] = tools
        payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            self.api_url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data: Any = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekAPIError(
                f"DeepSeek API 返回 HTTP {exc.code}: {detail}"
            ) from exc
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            ConnectionResetError,
            socket.timeout,
            ssl.SSLError,
        ) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise DeepSeekAPIError(f"无法连接 DeepSeek API: {reason}") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise DeepSeekAPIError(f"DeepSeek API 响应无效: {exc}") from exc

        try:
            message = response_data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekAPIError(
                f"DeepSeek API 响应缺少消息内容: {response_data!r}"
            ) from exc

        if not isinstance(message, dict):
            raise DeepSeekAPIError("DeepSeek API 返回了无效消息")
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        if not tool_calls and (not isinstance(content, str) or not content.strip()):
            raise DeepSeekAPIError("DeepSeek API 返回了空消息")
        return message

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        printer: StreamPrinter | None = None,
    ) -> dict[str, Any]:
        """
        流式调用 DeepSeek API，实时显示思考过程和工具调用。
        
        返回与 chat() 相同的 message dict。
        """
        request_body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            request_body["tools"] = tools
        payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            self.api_url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )

        started_stream = False
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekAPIError(
                f"DeepSeek API 返回 HTTP {exc.code}: {detail}"
            ) from exc
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            ConnectionResetError,
            socket.timeout,
            ssl.SSLError,
        ) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise DeepSeekAPIError(f"无法连接 DeepSeek API: {reason}") from exc
        except TimeoutError as exc:
            raise DeepSeekAPIError(f"DeepSeek API 超时: {exc}") from exc

        # 解析 SSE 流
        content_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, Any]] = {}

        if printer:
            printer.on_thinking_start()
            started_stream = True

        try:
            # 按行读取 SSE，避免逐字节解码破坏 UTF-8 中文字符。
            event_lines: list[str] = []
            while True:
                raw_line = response.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    event_lines.append(line)
                elif event_lines:
                    self._process_sse_event(
                        "\n".join(event_lines),
                        content_parts,
                        tool_call_parts,
                        printer,
                    )
                    event_lines = []

            if event_lines:
                self._process_sse_event(
                    "\n".join(event_lines),
                    content_parts,
                    tool_call_parts,
                    printer,
                )
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            ConnectionResetError,
            socket.timeout,
            TimeoutError,
            ssl.SSLError,
        ) as exc:
            raise DeepSeekAPIError(f"流式响应中断: {exc}") from exc
        finally:
            response.close()
            if printer and started_stream:
                printer.on_thinking_end()

        full_content = "".join(content_parts)
        message: dict[str, Any] = {
            "role": "assistant",
            "content": full_content or None,
        }
        if tool_call_parts:
            message["tool_calls"] = [
                tool_call_parts[index] for index in sorted(tool_call_parts)
            ]
        if not full_content and not tool_call_parts:
            raise DeepSeekAPIError("流式响应没有内容或工具调用")
        return message

    def _process_sse_event(
        self,
        event_str: str,
        content_parts: list[str],
        tool_call_parts: dict[int, dict[str, Any]],
        printer: StreamPrinter | None,
    ) -> None:
        """处理一个 SSE 事件。"""
        if not event_str or event_str.startswith(":"):
            return

        for line in event_str.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("data: "):
                data_str = line[6:]
            elif line.startswith("data:"):
                data_str = line[5:]
            else:
                continue

            if data_str == "[DONE]":
                return

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})

            content = delta.get("content", "")
            if content:
                content_parts.append(content)
                if printer:
                    printer.on_thinking_chunk(content)

            for call_delta in delta.get("tool_calls", []) or []:
                index = call_delta.get("index", 0)
                if not isinstance(index, int):
                    continue
                call = tool_call_parts.setdefault(
                    index,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if call_delta.get("id"):
                    call["id"] = call_delta["id"]
                if call_delta.get("type"):
                    call["type"] = call_delta["type"]
                function_delta = call_delta.get("function", {})
                if function_delta.get("name"):
                    call["function"]["name"] += function_delta["name"]
                if function_delta.get("arguments"):
                    call["function"]["arguments"] += function_delta["arguments"]


# ── 功能性失败检测层 ──────────────────────────────────
# 即使工具"正常返回"（无 Python 异常），返回值也可能表示逻辑失败。
# 检测这些模式 → 创建合成 traceback → 记录到 safety_net.traceback_storage，
# 为 auto_trigger_repair 提供数据来源，闭合「功能性失败 → 自动修复」链路。

_FUNCTIONAL_FAILURE_PATTERNS: list[tuple[str, str]] = [
    ("未知操作:", "工具收到不支持的操作"),
    ("离线任务错误:", "离线任务执行异常"),
    ("安全网错误:", "安全网检测异常"),
    ("离线任务执行失败", "离线任务执行失败"),
    ("任务僵死", "离线任务僵死超时"),
    ("无法导入修复模块", "离线修复桥接导入失败"),
]

# 只读工具：返回值是文件内容，不应进行功能性失败检测
# （文件内容可能包含任意文本，误判风险极高）
_FUNCTIONAL_CHECK_EXCLUDED_TOOLS = frozenset({
    "read_file", "list_directory", "knowledge", "file_utils",
    "blackboard", "audit_log",
})


def _detect_functional_failure(
    result: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    """
    功能性失败检测层。

    扫描工具返回值中的失败模式（非 Python 异常），
    生成合成 traceback 并存入 safety_net.traceback_storage，
    使得 auto_trigger_repair 也能处理这些非异常失败。

    静默运行：失败时不影响主流程。
    """
    if not result or not isinstance(result, str):
        return

    # 跳过只读/内容类工具 — 返回的文件内容可包含任意文本模式
    if tool_name in _FUNCTIONAL_CHECK_EXCLUDED_TOOLS:
        return

    failure_reason = ""
    for pattern, desc in _FUNCTIONAL_FAILURE_PATTERNS:
        if pattern in result:
            failure_reason = desc
            break

    if not failure_reason:
        return

    # 构建合成 traceback（格式与真实 traceback 一致，便于 parser 解析）
    synthetic_tb = (
        f"Traceback (most recent call last):\n"
        f"  [FunctionalFailure] in {tool_name}()\n"
        f"  Arguments: {json.dumps(arguments, ensure_ascii=False)[:200]}\n"
        f"FunctionalFailure: {failure_reason}\n"
        f"  Result: {result[:300]}"
    )

    try:
        # 功能性失败是业务反馈（如"未知操作"），由模型纠正，
        # 不应记为系统错误触发连续错误警报。
        tool_safety._safety.record_event("other", f"功能反馈: {failure_reason}", tool_name)
    except Exception:
        pass  # safety_net 不可用时静默忽略


_JSON_REPAIR_SENTINEL = object()


def _repair_truncated_json(raw: str) -> Any:
    """尽力修复流式生成中被截断的 JSON（tool_calls 的 arguments）。

    流式 SSE 累加 arguments 时，超长内容可能在中途被切断，
    导致 json.loads 抛 JSONDecodeError。此函数尝试补全尾部闭合字符，
    使截断的 JSON 仍可解析（内容可能不完整，调用方需按工具类型判断是否可用）。

    返回修复后的对象；无法修复时返回 _JSON_REPAIR_SENTINEL。
    """
    if not isinstance(raw, str):
        return _JSON_REPAIR_SENTINEL
    stripped = raw.strip()
    if not stripped:
        return _JSON_REPAIR_SENTINEL

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(cand: str) -> None:
        if cand not in seen:
            seen.add(cand)
            candidates.append(cand)

    # 1) 直接补常见的尾部闭合字符
    for sfx in ('"', '"}', '}', ']', '"}]', '"]', '}]'):
        _add(stripped + sfx)

    # 2) 去掉末尾不完整片段后，再尝试闭合
    for cut in range(1, min(len(stripped), 16) + 1):
        base = stripped[:-cut].rstrip(' ,:\t\r\n"\'')
        if not base:
            continue
        for sfx in ('"', '"}', '}', ']'):
            _add(base + sfx)

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    return _JSON_REPAIR_SENTINEL



# ── 步骤 2.3：分派层 —— 注册表查表（主）/ elif 链（兼容回退）──
_USE_REGISTRY_DISPATCH = True   # 置 False 即可回退到 legacy elif 链


def _unknown_tool_hint(name: str) -> str:
    """未知工具友好提示（不抛异常，让模型自行纠正）。"""
    known_tools = [t.get("function", {}).get("name", "") for t in ALL_TOOLS]
    known_tools = [n for n in known_tools if n]
    hint = ", ".join(known_tools[:8])
    return (
        f"❌ 未知工具: {name}。该工具不存在于当前可用工具列表中。\n"
        f"请从以下工具中选择一个重新尝试（前8个）: {hint}\n"
        f"💡 提示: 如果你需要查找文件，请使用 file_utils（action='find'）；"
        f"联网搜索请用 web_search。"
    )


def _legacy_dispatch(name: str, arguments: dict) -> str | None:
    """旧 elif 分派链（兼容回退路径，保留全部历史分支）。"""
    if name in {"read_file", "list_directory"}:
        return execute_read_tool(name, arguments)
    elif name in {"write_file", "replace_text", "make_directory"}:
        return execute_write_tool(name, arguments)
    elif name == "run_command":
        return tool_runner.execute_runner_tool(arguments)
    elif name == "calculate":
        return tool_calculator.execute_calculator_tool(arguments)
    elif name == "file_utils":
        return tool_file_utils.execute_file_utils_tool(arguments)
    elif name == "knowledge":
        return tool_knowledge.execute_knowledge_tool(arguments)
    elif name == "task_tracker":
        return tool_task_tracker.execute_task_tracker_tool(arguments)
    elif name == "self_check":
        return tool_self_check.execute_self_check_tool(arguments)
    elif name == "test_runner":
        return tool_test_runner.execute_test_runner_tool(arguments)
    elif name == "monitor":
        return tool_monitor.execute_monitor_tool(arguments)
    elif name == "decision_engine":
        return tool_decision.execute_decision_engine_tool(arguments)
    elif name == "safety_net":
        return tool_safety.execute_safety_net_tool(arguments)
    elif name == "web_search":
        return tool_web_search.execute_web_search_tool(arguments)
    elif name == "offline":
        return tool_offline.execute_offline_tool(arguments)
    elif name == "checkpoint":
        return tool_checkpoint.execute_checkpoint_tool(arguments)
    elif name == "specialist":
        return tool_specialist.execute_specialist_tool(arguments)
    elif name == "agent_profile":
        return tool_agent_profile.execute_agent_profile_tool(arguments)
    elif name == "task_dispatcher":
        return tool_task_dispatcher.execute_task_dispatcher_tool(arguments)
    elif name == "orchestrator":
        return tool_orchestrator.execute_orchestrator_tool(arguments)
    elif name == "health_dashboard":
        return tool_health.execute_health_dashboard_tool(arguments)
    elif name == "usage_analyzer":
        return tool_usage.execute_usage_analyzer_tool(arguments)
    elif name == "safe_deploy":
        return tool_deploy.execute_safe_deploy_tool(arguments)
    elif name == "tech_radar":
        return tool_radar.execute_tech_radar_tool(arguments)
    elif name == "env_awareness":
        return tool_env.execute_env_awareness_tool(arguments)
    elif name == "evolution_strategy":
        return tool_evolution.execute_evolution_strategy_tool(arguments)
    elif name == "audit_log":
        return tool_audit.execute_audit_log_tool(arguments)
    elif name == "blackboard":
        return tool_blackboard.execute_blackboard_tool(arguments)
    elif name == "auto_repair":
        return tool_auto_repair.execute_auto_repair_tool(arguments)
    elif name == "artifact_validator":
        return tool_artifact_validator.execute_artifact_validator_tool(arguments)
    elif name == "villager":
        return tool_villager.execute_villager_tool(arguments)
    elif name == "village_chat":
        return tool_village_chat.execute_village_chat_tool(arguments)
    elif name == "effect_evaluator":
        return tool_effect.execute_effect_evaluator_tool(arguments)
    elif name == "evidence_verifier":
        return tool_evidence.execute_evidence_verifier_tool(arguments)
    elif name == "multi_reviewer":
        return tool_multi_reviewer.execute_multi_reviewer_tool(arguments)
    elif name == "improvement_generator":
        return tool_improve.execute_improvement_generator_tool(arguments)
    elif name == "self_improver":
        return tool_self_improver.execute_self_improver_tool(arguments)
    elif name == "cycle_tracker":
        return tool_cycle_tracker.execute_cycle_tracker_tool(arguments)
    elif name == "self_healing":
        return tool_healing.execute_self_healing_tool(arguments)
    elif name == "offline_research":
        return tool_offline_research.execute_offline_research_tool(arguments)
    return None


def execute_model_tool_call(
    tool_call: dict[str, Any],
    printer: StreamPrinter | None = None,
) -> tuple[str, str, str]:
    """执行工具调用，可选择性地实时显示。"""
    try:
        tool_call_id = tool_call["id"]
        function = tool_call["function"]
        name = function["name"]
        raw_arguments = function.get("arguments", "{}")
    except (KeyError, TypeError, AttributeError) as exc:
        raise DeepSeekAPIError(f"模型生成了无效的工具调用: {tool_call!r}") from exc

    if not all(isinstance(value, str) for value in (tool_call_id, name)):
        raise DeepSeekAPIError("工具调用的 id 或名称无效")

    # 解析参数：优先标准解析；失败时尝试修复流式截断的 JSON。
    arguments: Any
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = _repair_truncated_json(raw_arguments)
        if arguments is _JSON_REPAIR_SENTINEL or not isinstance(arguments, dict):
            raise DeepSeekAPIError(
                f"模型生成了无效的工具调用(参数无法解析): {raw_arguments[:200]!r}"
            ) from None
        # 完整性关键工具：截断修复后的内容可能不完整，拒绝执行以避免写坏文件，
        # 交由 _error_tool_result 兜底让模型重新生成。
        if name in {"write_file", "replace_text"}:
            raise DeepSeekAPIError(
                "工具调用参数(JSON)在流式生成中被截断，无法保证内容完整；"
                "请将大内容拆分为多次 write_file 调用后重试"
            )

    if not isinstance(arguments, dict):
        raise DeepSeekAPIError("工具调用参数必须是 JSON 对象")

    # 计时 + 成功标记：自动接入 monitor 性能统计（修复"total_calls 恒为 0"）
    _tool_start_time = time.time()
    _tool_success = True
    _tool_error: BaseException | None = None

    # 实时显示工具调用
    if printer:
        printer.on_tool_call_start(name, json.dumps(arguments, ensure_ascii=False))

    try:
        if _USE_REGISTRY_DISPATCH:
            _spec = REGISTRY.get(name)
            if _spec is not None:
                result = _spec.handler(arguments)
            else:
                result = _unknown_tool_hint(name)
                _tool_success = False
        else:
            _legacy_result = _legacy_dispatch(name, arguments)
            if _legacy_result is None:
                result = _unknown_tool_hint(name)
                _tool_success = False
            else:
                result = _legacy_result
    except RuntimeError as exc:
        # ── 步骤 4.2：不再手工登记错误类型元组 ──
        # 实测 36 种工具错误全部继承 RuntimeError，故统一捕获后按 tools/errors 契约分类。
        # 新增工具只需在 ToolSpec.errors 中声明，无需改此处。
        from tools.errors import make_evidence as _mk_ev
        _ev = _mk_ev(exc, phase="execute")
        _prefix = "⚠️" if _ev.retryable else "❌"
        result = (f"{_prefix} 工具执行失败"
                  f"[{_ev.category.value}/{_ev.error_code}]: {exc}")
        _tool_success = False
        _tool_error = exc
        # 按类别桥接 safety_net：
        #   REJECTED  = 业务拒绝，交模型自纠 → 记 tool_call
        #   RETRYABLE / FATAL = 系统性问题 → 记 error，供安全网感知
        try:
            _kind = "tool_call" if _ev.category.value == "REJECTED" else "error"
            tool_safety._safety.record_event(
                _kind, f"[{_ev.category.value}] {exc}", name)
        except Exception:
            pass  # safety_net 不可用时静默忽略

    # ── 功能性失败检测层 ──────────────────────────────────
    # 即使工具"正常返回"（无 Python 异常），返回值也可能表示逻辑失败。
    # 检测这些模式 → 创建合成 traceback → 记录到 safety_net.traceback_storage
    _detect_functional_failure(result, name, arguments)

    # 实时显示工具调用结果
    if printer:
        printer.on_tool_call_result(name, result)
        printer.on_tool_call_end()

    # ── 可观测性中间件（步骤 3）：统一采集，替代手工埋点 ──
    # 数据模型对齐 OpenTelemetry GenAI 语义约定；新增工具自动纳入，无需再写埋点。
    try:
        from tools.middleware import MIDDLEWARE as _MW
        _MW.record_call(
            tool=name,
            call_id=tool_call_id,
            arguments=arguments,
            result=result,
            duration_ms=(time.time() - _tool_start_time) * 1000.0,
            error=(_tool_error or (None if _tool_success else RuntimeError(result[:120]))),
            spec=REGISTRY.get(name),
        )
    except Exception:
        pass  # 可观测性失败绝不影响主流程

    return tool_call_id, name, result


def _error_tool_result(tool_call: Any, exc: Exception) -> tuple[str, str, str]:
    """从非法工具调用中尽力提取 id/name，返回一个错误回执，保证会话可继续。

    关键约束：返回的 tool_call_id 必须与 assistant 消息中该 tool_call 的 "id"
    字段一致，否则 DeepSeek 仍会因 tool_call_id 不匹配而拒绝请求。
    """
    tool_call_id = ""
    name = "unknown"
    if isinstance(tool_call, dict):
        raw_id = tool_call.get("id")
        if isinstance(raw_id, str):
            tool_call_id = raw_id
        fn = tool_call.get("function")
        if isinstance(fn, dict):
            raw_name = fn.get("name")
            if isinstance(raw_name, str) and raw_name:
                name = raw_name
    if not isinstance(tool_call_id, str) or not tool_call_id:
        tool_call_id = f"invalid_{id(tool_call)}"
    if not isinstance(name, str) or not name:
        name = "unknown"
    return tool_call_id, name, f"❌ 工具调用无效: {exc}"


def run_agent_turn(
    client: DeepSeekClient,
    conversation: Conversation,
    printer: StreamPrinter | None = None,
) -> str:
    """
    运行一次智能体交互循环。
    
    使用流式 API 读取响应，实时显示思考和工具调用。
    工具调用轮次使用非流式 API（工具调用必须在非流式模式才能正确解析）。
    """
    import time

    def _chat_with_retry(messages, tools):
        last_exception = None
        for attempt in range(3):
            try:
                return client.chat(messages, tools=tools)
            except Exception as e:
                last_exception = e
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"Chat attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
        raise last_exception

    last_signature: str | None = None
    repeat_count = 0
    tool_calls_log: list[str] = []

    for step in range(MAX_TOOL_STEPS):
        streamed = False
        # 第一轮使用流式，后续工具调用轮次使用非流式
        if step == 0:
            try:
                response = client.chat_stream(
                    conversation.api_messages(),
                    tools=ALL_TOOLS,
                    printer=printer,
                )
                streamed = True
            except Exception as e:
                print(f"Streaming failed ({e}), falling back to non-streaming...")
                response = _chat_with_retry(
                    conversation.api_messages(),
                    ALL_TOOLS,
                )
        else:
            response = _chat_with_retry(
                conversation.api_messages(),
                ALL_TOOLS,
            )

        tool_calls = response.get("tool_calls")
        if tool_calls:
            if not isinstance(tool_calls, list):
                raise DeepSeekAPIError("工具调用列表格式无效")
            conversation.add_assistant_tool_request(response)
            for tool_call in tool_calls:
                try:
                    tool_call_id, name, result = execute_model_tool_call(
                        tool_call, printer=printer,
                    )
                except DeepSeekAPIError as exc:
                    # 非法/截断的工具调用：不再抛出致命异常，而是补一条
                    # 错误回执，保证「tool_calls 消息后必有 tool 回执」。
                    tool_call_id, name, result = _error_tool_result(tool_call, exc)
                    if printer:
                        printer.on_tool_call_start(name, "{}")
                        printer.on_tool_call_result(name, result)
                        printer.on_tool_call_end()
                conversation.add_tool_result(tool_call_id, name, result)

                # ── 重复调用熔断检测：同一工具+参数连续重复触发保护 ──
                result_preview = result[:100].replace("\n", " ")
                tool_calls_log.append(f"  - {name}: {result_preview}")
                try:
                    fn = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                    raw_args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
                    signature = f"{name}:{raw_args}"
                except Exception:
                    signature = f"{name}:<unparseable>"
                if signature == last_signature:
                    repeat_count += 1
                else:
                    last_signature = signature
                    repeat_count = 1

                if repeat_count >= REPEAT_CALL_LIMIT:
                    # 触发熔断：终止工具循环，强制文本总结
                    if printer:
                        printer.on_notice(
                            f"⚠️ 熔断触发：连续 {repeat_count} 次重复调用 {name}，终止工具循环"
                        )
                    conversation.add_user_message(
                        "检测到连续重复调用同一工具，请基于已完成的全部操作，"
                        "用简洁的中文总结当前进展，不要再调用任何工具。"
                    )
                    try:
                        final = client.chat(conversation.api_messages(), tools=[])
                        final_text = final.get("content")
                        if isinstance(final_text, str) and final_text.strip():
                            final_text = final_text.strip()
                            conversation.add_assistant_message(final_text)
                            if printer:
                                printer.on_final_output(final_text, already_streamed=False)
                            return final_text
                    except Exception:
                        pass
                    summary = (
                        f"⚠️ 检测到连续 {repeat_count} 次重复调用 {name}，已触发熔断保护。\n"
                        f"最近工具调用：\n" + "\n".join(tool_calls_log[-10:])
                    )
                    conversation.add_assistant_message(summary)
                    if printer:
                        printer.on_final_output(summary, already_streamed=False)
                    return summary
            continue

        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekAPIError("DeepSeek API 返回了空消息")
        assistant_message = content.strip()
        conversation.add_assistant_message(assistant_message)
        if printer:
            # 第 0 轮正文已经通过 SSE 输出；工具调用后的最终答复来自非流式轮次。
            printer.on_final_output(
                assistant_message,
                already_streamed=(step == 0 and streamed),
            )
        return assistant_message

    # ── 工具步数耗尽：优雅收尾（不再抛出致命异常）──
    # 当达到 MAX_TOOL_STEPS 上限且未触发重复熔断时，强制 LLM 基于已执行
    # 的工具调用做文本总结，保证会话正常返回，而不是向主循环抛异常。
    if tool_calls_log:
        conversation.add_user_message(
            "已执行较多工具调用，请基于以上所有工具调用的结果，"
            "用简洁的中文做一个总结性回复，不要再调用任何工具。"
        )
        try:
            final = client.chat(conversation.api_messages(), tools=[])
            final_text = final.get("content")
            if isinstance(final_text, str) and final_text.strip():
                final_text = final_text.strip()
                conversation.add_assistant_message(final_text)
                if printer:
                    printer.on_final_output(final_text, already_streamed=False)
                return final_text
        except Exception:
            pass  # 总结请求失败时退化为手动摘要

        # 手动生成摘要作为最终兜底
        summary_lines = [
            f"⚠️ 已达到工具调用步数上限（{MAX_TOOL_STEPS} 次），以下为已执行操作摘要："
        ]
        summary_lines.extend(tool_calls_log[-10:])
        if len(tool_calls_log) > 10:
            summary_lines.append(f"  ... 及其他 {len(tool_calls_log) - 10} 次调用")
        summary = "\n".join(summary_lines)
        conversation.add_assistant_message(summary)
        if printer:
            printer.on_final_output(summary, already_streamed=False)
        return summary

    # 极端情况：步数耗尽却无任何工具调用记录（理论不可达，防御性兜底）
    summary = f"⚠️ 已达到工具调用步数上限（{MAX_TOOL_STEPS} 次），本次会话未能收敛到最终答复。"
    conversation.add_assistant_message(summary)
    if printer:
        printer.on_final_output(summary, already_streamed=False)
    return summary

# ── Specialist 工具映射 & 专用运行函数 ────────────────────

def _get_specialist_tools(specialist_instance: Any) -> list[dict[str, Any]]:
    """根据 Specialist 的 tools 列表返回对应的 TOOL_DEFINITION 列表。"""
    # 核心工具（从 read.py / write.py / run_command 提取）
    _core_map: dict[str, Any] = {}
    for tool_def in READ_TOOLS + WRITE_TOOLS:
        name = tool_def.get("function", {}).get("name", "")
        if name:
            _core_map[name] = tool_def
    _core_map["run_command"] = tool_runner.TOOL_DEFINITION

    tool_map: dict[str, Any] = {
        **_core_map,
        # 自建工具
        "web_search": tool_web_search.TOOL_DEFINITION,
        "knowledge": tool_knowledge.TOOL_DEFINITION,
        "file_utils": tool_file_utils.TOOL_DEFINITION,
        "calculate": tool_calculator.TOOL_DEFINITION,
        "monitor": tool_monitor.TOOL_DEFINITION,
        "self_check": tool_self_check.TOOL_DEFINITION,
        "test_runner": tool_test_runner.TOOL_DEFINITION,
        "safety_net": tool_safety.TOOL_DEFINITION,
        "task_tracker": tool_task_tracker.TOOL_DEFINITION,
        "decision_engine": tool_decision.TOOL_DEFINITION,
        # 协同 & 编排工具
        "specialist": tool_specialist.TOOL_DEFINITION,
        "agent_profile": tool_agent_profile.TOOL_DEFINITION,
        "task_dispatcher": tool_task_dispatcher.TOOL_DEFINITION,
        "orchestrator": tool_orchestrator.TOOL_DEFINITION,
        "offline": tool_offline.TOOL_DEFINITION,
        "checkpoint": tool_checkpoint.TOOL_DEFINITION,
        # Evolver 自建模块
        "health_dashboard": tool_health.TOOL_DEFINITION,
        "usage_analyzer": tool_usage.TOOL_DEFINITION,
        "safe_deploy": tool_deploy.TOOL_DEFINITION,
        "tech_radar": tool_radar.TOOL_DEFINITION,
        "env_awareness": tool_env.TOOL_DEFINITION,
        "evolution_strategy": tool_evolution.TOOL_DEFINITION,
        "audit_log": tool_audit.TOOL_DEFINITION,
        "blackboard": tool_blackboard.TOOL_DEFINITION,
        "effect_evaluator": tool_effect.TOOL_DEFINITION,
        "improvement_generator": tool_improve.TOOL_DEFINITION,
        "self_improver": tool_self_improver.TOOL_DEFINITION,
        "cycle_tracker": tool_cycle_tracker.TOOL_DEFINITION,
        "self_healing": tool_healing.TOOL_DEFINITION,
        "auto_repair": tool_auto_repair.TOOL_DEFINITION,
        "artifact_validator": tool_artifact_validator.TOOL_DEFINITION,
        "villager": tool_villager.TOOL_DEFINITION,
        "village_chat": tool_village_chat.TOOL_DEFINITION,
        "evidence_verifier": tool_evidence.TOOL_DEFINITION,
        "multi_reviewer": tool_multi_reviewer.TOOL_DEFINITION,
        "offline_research": tool_offline_research.TOOL_DEFINITION,
    }
    allowed = specialist_instance.tools
    return [tool_map[t] for t in allowed if t in tool_map]


def run_specialist_turn(
    sp_messages: list[dict[str, Any]],
    specialist_tools: list[dict[str, Any]],
    max_steps: int = 8,
) -> str:
    """
    运行一次 Specialist 的工具调用循环。
    
    类似 run_agent_turn，但使用独立的 messages 列表和受限工具集。
    返回最终的文本回复。工具调用耗尽时强制 LLM 做文本总结。
    """
    msgs = list(sp_messages)  # 拷贝，避免修改原列表
    printer = _global_printer
    tool_calls_log: list[str] = []  # 记录每次工具调用的摘要

    for step in range(max_steps):
        if step == 0:
            response = _global_client.chat_stream(
                msgs, tools=specialist_tools, printer=printer,
            )
        else:
            response = _global_client.chat(
                msgs, tools=specialist_tools,
            )

        tool_calls = response.get("tool_calls")
        if tool_calls:
            if not isinstance(tool_calls, list):
                continue
            # 添加 assistant 消息（含 tool_calls）
            msgs.append(response)
            for tool_call in tool_calls:
                try:
                    tool_call_id, name, result = execute_model_tool_call(
                        tool_call, printer=printer,
                    )
                except DeepSeekAPIError as exc:
                    tool_call_id, name, result = _error_tool_result(tool_call, exc)
                    if printer:
                        printer.on_tool_call_start(name, "{}")
                        printer.on_tool_call_result(name, result)
                        printer.on_tool_call_end()
                # 记录工具调用摘要
                result_preview = result[:100].replace("\n", " ")
                tool_calls_log.append(f"  - {name}: {result_preview}")
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })
            continue

        content = response.get("content")
        if isinstance(content, str) and content.strip():
            if printer and step > 0:
                printer.on_final_output(content.strip(), already_streamed=False)
            return content.strip()

    # ── 所有轮次耗尽：强制要求 LLM 做文本总结 ──
    if tool_calls_log:
        msgs.append({
            "role": "user",
            "content": "请基于以上所有工具调用的结果，用简洁的中文做一个总结性回复。不要再调用工具。",
        })
        try:
            response = _global_client.chat(msgs, tools=[])  # 不带工具，强制纯文本
            content = response.get("content")
            if isinstance(content, str) and content.strip():
                if printer:
                    printer.on_final_output(content.strip(), already_streamed=False)
                return content.strip()
        except Exception:
            pass

        # 手动生成摘要作为最终兜底
        summary_lines = [f"完成了 {len(tool_calls_log)} 次工具调用："]
        summary_lines.extend(tool_calls_log[:10])
        if len(tool_calls_log) > 10:
            summary_lines.append(f"  ... 及其他 {len(tool_calls_log) - 10} 次调用")
        return "\n".join(summary_lines)

    return ""  # 没有任何工具调用也没有文本（极端情况）


def _auto_switch_to_debugger(
    error_message: str,
    context: str = "",
    conversation: "Conversation | None" = None,
    interface: "TerminalInterface | None" = None,
) -> str:
    """
    当发生异常时自动切换到 Debugger 模式进行诊断。

    - 如果当前已在 debugger 模式 → 直接报错（防止无限循环）
    - 否则创建 DebuggerAgent，运行诊断/修复/快照，并切换到 debugger 会话
    """
    global _active_specialist_type, _active_specialist_instance

    # 防循环：已在 debugger 模式则直接报错
    if _active_specialist_type == "debugger":
        report = (
            "🔴 [Debugger 无法处理] 在 Debugger 会话模式下再次发生异常，"
            "这可能是 Debugger 自身无法解决的深层问题。\n"
            f"错误: {error_message}\n"
            f"上下文: {context}\n\n"
            "💡 建议: 使用 /talk off 退出 Debugger 模式，手动排查。"
        )
        if interface:
            interface.stream.on_error(report)
        if conversation is not None:
            conversation.add_assistant_message(f"[Debugger] {report}")
        return report

    from tools.specialist_base import DebuggerAgent, TaskInput, SpecialistRegistry

    # 创建 DebuggerAgent 实例，执行本地诊断（不依赖 API）
    debugger = DebuggerAgent()

    report_lines = [
        "",
        "🐛 ───── 自动触发 Debugger 异常诊断 ─────",
        f"📋 错误信息: {error_message[:300]}",
    ]
    if context:
        report_lines.append(f"📎 上下文: {context}")

    # Step 1: 诊断
    try:
        diag_task = TaskInput(
            task_id=f"auto_diag_{int(time.time())}",
            description="自动诊断",
            params={"action": "diagnose", "error": error_message, "context": {"source": context}},
        )
        diag_result = debugger.process_task(diag_task)
        if diag_result.status == "done":
            diagnosis = diag_result.output.get("diagnosis", {})
            report_lines.append(f"🔍 诊断: {diag_result.summary}")
            report_lines.append(f"   类别: {diagnosis.get('category', 'unknown')}")
            report_lines.append(f"   严重度: {diagnosis.get('severity', 'medium')}")
            suggestions = diag_result.suggestions
            if suggestions:
                for i, s in enumerate(suggestions[:3], 1):
                    report_lines.append(f"   💡 建议{i}: {s}")
    except Exception as diag_exc:
        report_lines.append(f"⚠️ 诊断过程异常: {diag_exc}")

    # Step 2: 尝试自动修复
    try:
        fix_task = TaskInput(
            task_id=f"auto_fix_{int(time.time())}",
            description="自动修复",
            params={"action": "auto_fix", "error": error_message, "context": {"source": context}},
        )
        fix_result = debugger.process_task(fix_task)
        if fix_result.status == "done":
            report_lines.append(f"🔧 修复: {fix_result.summary}")
    except Exception as fix_exc:
        report_lines.append(f"⚠️ 修复过程异常: {fix_exc}")

    # Step 3: 保存快照
    try:
        snap_task = TaskInput(
            task_id=f"auto_snap_{int(time.time())}",
            description="自动快照",
            params={"action": "snapshot", "error": error_message, "context": {"source": context}},
        )
        snap_result = debugger.process_task(snap_task)
        if snap_result.status == "done":
            report_lines.append(f"📸 快照: {snap_result.summary}")
    except Exception as snap_exc:
        report_lines.append(f"⚠️ 快照保存异常: {snap_exc}")

    # Step 4: 切换到 Debugger 会话模式
    try:
        specialist = SpecialistRegistry.create("debugger")
        _active_specialist_instance = specialist
        _active_specialist_type = "debugger"
        report_lines.append("")
        report_lines.append(f"🟢 已自动切换到 [{specialist.name}] 会话模式")
        report_lines.append("💡 可直接对话分析问题 | /talk off 退出 | /debugger health 健康检查")
    except Exception as switch_exc:
        report_lines.append(f"⚠️ 无法切换到 Debugger 模式: {switch_exc}")

    report_lines.append("─" * 40)

    report = "\n".join(report_lines)

    # 显示报告
    if interface:
        interface.stream.on_notice(report)

    # 记录到对话历史
    if conversation is not None:
        conversation.add_assistant_message(report)

    return report


def handle_command(
    command: str,
    conversation: Conversation,
    interface: TerminalInterface,
) -> bool:
    """Handle a slash command; return False when the program should exit."""

    normalized = command.lower()
    if normalized in {"/exit", "/quit"}:
        return False
    if normalized == "/clear":
        conversation.clear()
        interface.show_notice("当前会话已清空。")
        return True
    if normalized == "/save":
        conversation.save(HISTORY_FILE)
        interface.show_notice(f"会话已保存到 {HISTORY_FILE}")
        return True
    if normalized in {"/restart", "/reboot"}:
        interface.show_notice("正在保存会话并重启进程…")
        perform_restart(
            conversation.system_prompt,
            conversation.messages,
        )
        return True

    handled, result = execute_direct_read_command(command)
    if handled:
        conversation.add_user_message(command)
        conversation.add_assistant_message(result)
        interface.show_assistant_message(result)
        return True

    handled, result = execute_direct_write_command(command)
    if handled:
        conversation.add_user_message(command)
        conversation.add_assistant_message(result)
        interface.show_assistant_message(result)
        return True

    handled, result = execute_direct_command_control(command)
    if handled:
        conversation.add_user_message(command)
        conversation.add_assistant_message(result)
        interface.show_assistant_message(result)
        return True

    # /debugger — Debugger 调试守护者快捷命令
    if normalized == "/debugger" or normalized.startswith("/debugger "):
        parts = normalized.split(maxsplit=2)
        sub_cmd = parts[1] if len(parts) > 1 else ""
        sub_arg = parts[2] if len(parts) > 2 else ""
        from tools.specialist_base import DebuggerAgent, TaskInput
        debugger = DebuggerAgent()
        if sub_cmd == "health":
            task = TaskInput(
                task_id="cmd_health",
                description="终端健康检查",
                params={"action": "health_check"},
            )
            result = debugger.process_task(task)
            report = f"{result.summary}\n评分: {result.output.get('health_score', '?')}/100"
        elif sub_cmd == "diagnose":
            task = TaskInput(
                task_id="cmd_diag",
                description=sub_arg or "手动诊断",
                params={"action": "diagnose", "error": sub_arg or "手动触发"},
            )
            result = debugger.process_task(task)
            report = result.summary
        elif sub_cmd == "report":
            task = TaskInput(
                task_id="cmd_report",
                description="终端报告",
                params={"action": "report"},
            )
            result = debugger.process_task(task)
            report = result.output.get("report_text", result.summary)
        elif sub_cmd == "snapshot":
            task = TaskInput(
                task_id="cmd_snap",
                description="终端快照",
                params={"action": "snapshot", "error": sub_arg or "手动快照"},
            )
            result = debugger.process_task(task)
            report = result.summary
        else:
            report = (
                "🐛 Debugger 命令:\n"
                "  /debugger health    — 系统健康检查\n"
                "  /debugger diagnose <错误信息> — 诊断异常\n"
                "  /debugger report    — 生成工作报告\n"
                "  /debugger snapshot [原因] — 保存系统快照"
            )
        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # /test-error — 测试异常捕获链路（v2.0 补丁验证）
    if normalized == "/test-error" or normalized.startswith("/test-error "):
        parts = normalized.split(maxsplit=1)
        mode = parts[1].strip() if len(parts) > 1 else "raise_error"
        if mode not in ("raise_error", "silent_fail", "custom_error_type", "naked"):
            mode = "raise_error"
        from core.broken_tool import execute_broken_tool, BrokenToolError

        # naked 模式：不捕获，让异常直接炸穿，供 Debugger 捕获
        if mode == "naked":
            execute_broken_tool("naked")
            return True

        try:
            result_text = execute_broken_tool(mode)
            report = f"✅ /test-error [{mode}] 执行成功:\n{result_text}"
        except BrokenToolError as exc:
            report = (
                f"🔴 /test-error [{mode}] 捕获到 BrokenToolError:\n"
                f"  异常: {exc}\n"
                f"  ✅ 自定义异常类型路由正常"
            )
        except RuntimeError as exc:
            report = (
                f"🔴 /test-error [{mode}] 捕获到 RuntimeError:\n"
                f"  异常: {exc}\n"
                f"  ✅ 标准异常捕获链路正常"
            )
        except Exception as exc:
            report = (
                f"🔴 /test-error [{mode}] 捕获到通用异常:\n"
                f"  异常: {type(exc).__name__}: {exc}"
            )

        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # 离线任务命令
    if normalized == "/offline":
        from tools.offline_runner import _manager as offline_mgr
        report = offline_mgr.list_tasks()
        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True
    if normalized.startswith("/offline "):
        parts = normalized.split(maxsplit=2)
        offline_cmd = parts[1] if len(parts) > 1 else ""
        offline_arg = parts[2] if len(parts) > 2 else ""
        from tools.offline_runner import _manager as offline_mgr
        if offline_cmd == "submit":
            report = offline_mgr.submit(
                title=offline_arg or "未命名任务",
                description="",
            )
        elif offline_cmd == "status":
            report = offline_mgr.get_status(offline_arg)
        elif offline_cmd == "report":
            report = offline_mgr.generate_report(offline_arg)
        elif offline_cmd == "list":
            report = offline_mgr.list_tasks()
        else:
            report = "离线任务命令: submit <标题> | status <task_id> | report <task_id> | list"
        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # /profile — Agent 配置档案管理
    if normalized == "/profile" or normalized.startswith("/profile "):
        parts = normalized.split(maxsplit=2)
        if len(parts) == 1:
            from tools.agent_profile import _manager as pm
            report = pm.list_profiles()
        else:
            sub_cmd = parts[1].strip()
            from tools.agent_profile import _manager as pm, AgentProfileError as APE
            try:
                if sub_cmd == "list":
                    report = pm.list_profiles()
                elif sub_cmd == "active":
                    report = f"🟢 当前活跃: [{pm._active_profile_id}]\n"
                    report += f"💡 使用 /profile get {pm._active_profile_id} 查看详情"
                elif sub_cmd == "get":
                    agent_id = parts[2] if len(parts) > 2 else ""
                    report = pm.get_profile(agent_id)
                elif sub_cmd == "export":
                    agent_id = parts[2] if len(parts) > 2 else ""
                    report = pm.export_profile(agent_id)
                elif sub_cmd == "compare":
                    # /profile compare a b
                    if len(parts) > 2:
                        ids = parts[2].split()
                        if len(ids) >= 2:
                            report = pm.compare(ids[0], ids[1])
                        else:
                            report = "💡 用法: /profile compare <agent1> <agent2>"
                    else:
                        report = "💡 用法: /profile compare <agent1> <agent2>"
                else:
                    report = (
                        "📋 /profile 命令:\n"
                        "  /profile list           — 列出所有配置\n"
                        "  /profile active         — 查看当前活跃\n"
                        "  /profile get <id>       — 查看完整配置\n"
                        "  /profile export [id]    — 导出配置\n"
                        "  /profile compare a b    — 比较两个Agent\n"
                    )
            except APE as exc:
                report = f"❌ {exc}"
        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # /orchestrate — 多Agent协同编排快捷命令
    if normalized == "/orchestrate" or normalized.startswith("/orchestrate "):
        parts = normalized.split(maxsplit=2)
        if len(parts) == 1:
            from tools.orchestrator import _orchestrator as orch
            report = orch.help()
        else:
            sub_cmd = parts[1].strip()
            from tools.orchestrator import _orchestrator as orch
            if sub_cmd == "health":
                report = orch.health()
            elif sub_cmd == "list":
                report = orch.list_pipelines()
            elif sub_cmd == "agents":
                from tools.agent_manager import _manager as am
                report = am.list_agents()
            elif sub_cmd == "bus":
                from tools.message_bus import _bus as mb
                report = mb.queue_length()
            elif sub_cmd == "templates":
                from tools.task_dispatcher import _dispatcher as td
                report = td.templates()
            elif sub_cmd == "run" and len(parts) > 2:
                report = orch.run(task=parts[2])
            else:
                report = (
                    "🎯 /orchestrate 命令:\n"
                    "  /orchestrate              — 使用指南\n"
                    "  /orchestrate health       — 多Agent系统健康检查\n"
                    "  /orchestrate list         — 列出所有流水线\n"
                    "  /orchestrate agents       — 列出所有Agent\n"
                    "  /orchestrate bus          — 消息队列状态\n"
                    "  /orchestrate templates    — 查看分解模板\n"
                    "  /orchestrate run <任务>   — 一键运行流水线\n"
                )
        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # /talk — 与 Specialist 直接对话 + 一键切换
    if normalized == "/talk" or normalized.startswith("/talk "):
        global _active_specialist_type, _active_specialist_instance
        parts = normalized.split(maxsplit=2)

        # /talk (无参数) — 帮助或显示当前状态
        if len(parts) == 1:
            if _active_specialist_instance is not None:
                report = (
                    f"🟢 当前处于 [{_active_specialist_instance.name}] 会话模式\n"
                    f"   类型: {_active_specialist_type}\n"
                    f"   能力: {', '.join(_active_specialist_instance.capabilities)}\n"
                    f"\n💡 /talk off 退出会话模式 | 直接输入消息即可对话"
                )
            else:
                from tools.specialist_base import SpecialistRegistry
                report = (
                    "💬 /talk 用法:\n"
                    "  /talk <类型>            — 🆕 一键切换到 Specialist 会话模式\n"
                    "  /talk <类型> <消息>     — 单次与 Specialist 对话\n"
                    "  /talk off               — 退出 Specialist 会话模式\n"
                    "  /talk list              — 列出所有可对话的 Specialist\n"
                    "\n示例:\n"
                    "  /talk debugger          — 切换到 Debugger 模式\n"
                    "  /talk researcher        — 切换到 Researcher 模式\n"
                    "  /talk designer 你好     — 单次与 Designer 对话"
                )
            conversation.add_user_message(command)
            conversation.add_assistant_message(report)
            interface.show_assistant_message(report)
            return True

        sub_cmd = parts[1].strip()

        # /talk off — 退出会话模式
        if sub_cmd == "off":
            if _active_specialist_instance is not None:
                prev_name = _active_specialist_instance.name
                _active_specialist_type = ""
                _active_specialist_instance = None
                report = f"👋 已退出 [{prev_name}] 会话模式，回到 Agent 1 主模式。"
            else:
                report = "ℹ️ 当前未处于任何 Specialist 会话模式。"
            conversation.add_user_message(command)
            conversation.add_assistant_message(report)
            interface.show_assistant_message(report)
            return True

        # /talk list — 列出所有类型
        if sub_cmd == "list":
            from tools.specialist_base import SpecialistRegistry
            report = SpecialistRegistry.list_types()
            if _active_specialist_instance is not None:
                report += f"\n\n🟢 当前处于 [{_active_specialist_instance.name}] 会话模式"
            report += "\n💡 /talk <类型> 一键切换 | /talk off 退出"
            conversation.add_user_message(command)
            conversation.add_assistant_message(report)
            interface.show_assistant_message(report)
            return True

        # /talk <type> <msg> — 单次 LLM 对话（共享上下文 + 专属工具）
        if len(parts) >= 3:
            message = parts[2]
            from tools.specialist_base import SpecialistRegistry, SpecialistError as SE
            try:
                specialist = SpecialistRegistry.create(sub_cmd)
                sp_prompt = specialist.get_effective_system_prompt()
                sp_tools = _get_specialist_tools(specialist)

                sp_messages: list[dict[str, Any]] = [
                    {"role": "system", "content": sp_prompt},
                ]
                for msg in conversation.messages[-20:]:
                    role = msg.get("role", "")
                    if role == "user":
                        sp_messages.append(msg)
                    elif role == "assistant" and not msg.get("tool_calls"):
                        sp_messages.append(msg)
                sp_messages.append({"role": "user", "content": message})
                conversation.add_user_message(f"[对 {specialist.name} 说] {message}")
                report = run_specialist_turn(sp_messages, sp_tools)
                if report:
                    conversation.add_assistant_message(f"[{specialist.name}] {report}")
                else:
                    report = f"[{specialist.name}] 完成了工具调用。"
            except SE as exc:
                report = f"❌ {exc}"
            conversation.add_user_message(command)
            conversation.add_assistant_message(report)
            interface.show_assistant_message(report)
            return True

        # /talk <type> — 一键切换到会话模式（无消息）
        from tools.specialist_base import SpecialistRegistry, SpecialistError as SE
        try:
            specialist = SpecialistRegistry.create(sub_cmd)
            _active_specialist_instance = specialist
            _active_specialist_type = sub_cmd
            report = (
                f"🟢 已切换到 [{specialist.name}] 会话模式\n"
                f"{'─'*40}\n"
                f"类型: {sub_cmd}\n"
                f"描述: {specialist.description}\n"
                f"能力: {', '.join(specialist.capabilities)}\n"
                f"工具: {', '.join(specialist.tools)}\n"
                f"\n💡 现在可以直接对话，无需 /talk 前缀\n"
                f"💡 /talk off 退出 | /talk list 查看其他 | / 命令仍然可用"
            )
        except SE as exc:
            report = f"❌ {exc}"

        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    # ── /reload — 模块热加载（解决 Python 模块缓存问题）──
    if normalized == "/reload" or normalized.startswith("/reload "):
        parts = normalized.split(maxsplit=1)
        target = parts[1].strip() if len(parts) > 1 else ""

        import sys as _sys
        import importlib as _importlib

        # 可热加载的模块映射
        _reloadable: dict[str, str] = {
            "safety_net": "tools.safety_net",
            "offline_runner": "tools.offline_runner",
            "repair_executors": "tools.repair_executors",
            "executor_registry": "tools.executor_registry",
            "auto_repair": "tools.auto_repair",
            "checkpoint_manager": "tools.checkpoint_manager",
            "specialist_base": "tools.specialist_base",
            "agent_profile": "tools.agent_profile",
            "task_dispatcher": "tools.task_dispatcher",
            "orchestrator": "tools.orchestrator",
            "test_runner": "tools.test_runner",
            "monitor": "tools.monitor",
            "decision_engine": "tools.decision_engine",
            "knowledge_store": "tools.knowledge_store",
            "file_utils": "tools.file_utils",
            "runner": "tools.runner",
            "calculator": "tools.calculator",
            "web_search": "tools.web_search",
            "self_check": "tools.self_check",
            "task_tracker": "tools.task_tracker",
            # evolver 模块（自我进化系统）
            "audit_log": "evolver.audit_log",
            "effect_evaluator": "evolver.effect_evaluator",
            "self_improver": "evolver.self_improver",
            "cycle_tracker": "evolver.cycle_tracker",
            "health_dashboard": "evolver.health_dashboard",
            "improvement_generator": "evolver.improvement_generator",
            "evolution_strategy": "evolver.evolution_strategy",
            "hot_reload": "evolver.hot_reload",
        }

        if target == "" or target == "help":
            loaded = [k for k, v in _reloadable.items() if v in _sys.modules]
            report = (
                "🔄 /reload 模块热加载（无需重启进程）:\n"
                "  /reload              — 列出可热加载的模块\n"
                "  /reload all          — 重载所有工具模块\n"
                "  /reload <模块名>     — 重载指定模块\n"
                "  /reload safety_net   — 重载 safety_net（解决 '未知操作'）\n"
                f"\n已加载模块 ({len(loaded)}): {', '.join(loaded[:12])}"
                f"{' ...' if len(loaded) > 12 else ''}"
            )
        elif target == "all":
            results: list[str] = []
            for name, full_name in _reloadable.items():
                mod = _sys.modules.get(full_name)
                if mod is None:
                    results.append(f"  ⚠️ {name} (未加载)")
                    continue
                try:
                    _importlib.reload(mod)
                    results.append(f"  ✅ {name}")
                except Exception as exc:
                    results.append(f"  ❌ {name}: {exc}")
            report = "🔄 全部模块热加载完成:\n" + "\n".join(results)
        else:
            full_name = _reloadable.get(target)
            if full_name is None:
                import difflib as _difflib
                similar = _difflib.get_close_matches(target, list(_reloadable.keys()), n=3, cutoff=0.5)
                hint = f"\n  💡 相似模块: {', '.join(similar)}" if similar else ""
                report = f"❌ 未知模块: {target}{hint}\n💡 使用 /reload 查看可重载模块列表"
            else:
                mod = _sys.modules.get(full_name)
                if mod is None:
                    report = f"⚠️ 模块 '{target}' 尚未加载，无需重载"
                else:
                    try:
                        _importlib.reload(mod)
                        report = f"✅ 模块 '{target}' 已热加载。新代码立即生效，无需重启 agent1.py。"
                    except Exception as exc:
                        report = f"❌ 热加载 '{target}' 失败: {exc}"

        conversation.add_user_message(command)
        conversation.add_assistant_message(report)
        interface.show_assistant_message(report)
        return True

    interface.show_notice(
        "未知命令。可用命令：/read、/list、/write、/mkdir、/clear、/save、/restart、/exit、/debugger、/offline、/profile、/talk、/orchestrate、/test-error、/reload"
    )
    return True


def main() -> int:
    interface = TerminalInterface(stream_enabled=True)
    try:
        load_env_file(ENV_FILE)
    except (OSError, UnicodeError, ValueError) as exc:
        interface.show_error(f"无法读取 .env 配置: {exc}")
        return 2

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        interface.show_error(
            "未设置 DEEPSEEK_API_KEY 环境变量，无法连接 DeepSeek API。"
        )
        return 2

    # 模型与 API 地址统一以主循环代码为准（DEFAULT_MODEL / DEFAULT_API_URL），
    # .env 仅提供 DEEPSEEK_API_KEY 密钥，不再覆盖模型或地址。
    model = DEFAULT_MODEL
    api_url = DEFAULT_API_URL
    client = DeepSeekClient(api_key=api_key, model=model, api_url=api_url)
    conversation = Conversation(system_prompt=SYSTEM_PROMPT)
    printer = interface.stream

    # 设置全局引用，供 Specialist LLM 会话模式使用
    global _global_client, _global_printer
    _global_client = client
    _global_printer = printer

    # 检测是否有因重启而保存的会话历史
    saved_state = load_restart_state()
    if saved_state is not None:
        conversation.messages = saved_state["messages"]
        state_cleared = clear_restart_state()
        printer.on_notice(
            f"已从重启状态恢复会话（{len(conversation.messages)} 条历史消息）"
        )
        if not state_cleared:
            printer.on_error("重启状态已恢复，但状态文件无法删除。")

    interface.show_welcome()

    # ── 启动时扫描离线任务，主动汇报（"第二天收到结果"）──
    try:
        from research.offline.offline_status import scan_offline_tasks, format_report
        tasks = scan_offline_tasks()
        noteworthy = [t for t in tasks if t["status"] in ("done", "running", "failed")]
        if noteworthy:
            printer.on_notice("检测到离线研究任务：\n" + format_report(tasks))
    except Exception:
        pass  # 离线扫描失败不影响主流程

    while True:
        # 根据会话模式显示不同提示符
        if _active_specialist_instance is not None:
            prompt = f"\n[{_active_specialist_instance.name}] > "
        else:
            prompt = "\n你> "

        try:
            user_message = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_message:
            continue
        if user_message.startswith("/"):
            if not handle_command(user_message, conversation, interface):
                break
            continue

        # ── Specialist 会话模式消息路由（LLM + 专属工具 + 共享上下文）──
        if _active_specialist_instance is not None:
            sp_name = _active_specialist_instance.name
            sp_prompt = _active_specialist_instance.get_effective_system_prompt()
            sp_tools = _get_specialist_tools(_active_specialist_instance)

            # 构建消息：系统提示词 + 最近纯对话上下文 + 用户消息
            sp_messages: list[dict[str, Any]] = [
                {"role": "system", "content": sp_prompt},
            ]
            # 从共享 conversation 中提取最近的纯对话消息（跳过 tool 角色和含 tool_calls 的 assistant）
            for msg in conversation.messages[-20:]:
                role = msg.get("role", "")
                if role == "user":
                    sp_messages.append(msg)
                elif role == "assistant" and not msg.get("tool_calls"):
                    sp_messages.append(msg)
            sp_messages.append({"role": "user", "content": user_message})
            conversation.add_user_message(f"[对 {sp_name} 说] {user_message}")

            try:
                response = run_specialist_turn(sp_messages, sp_tools)
                if response:
                    conversation.add_assistant_message(f"[{sp_name}] {response}")
                else:
                    interface.stream.on_notice(f"[{sp_name}] 完成了工具调用，等待你的下一步指示。")
            except Exception as exc:
                error_msg = f"{sp_name} 回应失败: {exc}"
                interface.stream.on_error(error_msg)
                _auto_switch_to_debugger(
                    error_message=error_msg,
                    context=f"Specialist 会话模式 ({sp_name})",
                    conversation=conversation,
                    interface=interface,
                )
            continue

        conversation.add_user_message(user_message)
        try:
            assistant_message = run_agent_turn(client, conversation, printer=printer)
        except DeepSeekAPIError as exc:
            error_msg = str(exc)
            printer.on_error(error_msg)
            _auto_switch_to_debugger(
                error_message=error_msg,
                context="主循环 Agent 交互",
                conversation=conversation,
                interface=interface,
            )
            continue

        # run_agent_turn 已负责显示最终回复；这里仅保留对话历史。

    printer.on_notice("Agent 1 已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
