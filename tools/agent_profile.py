"""
agent_profile — Agent 配置档案管理系统
======================================
为多智能体系统提供完整的 Agent 配置管理。

核心功能：
  - 维护每个 Agent 的系统提示词（人格定义）
  - 管理可用工具列表（功能开关）
  - 管理读写权限（安全边界）
  - 持久化存储与加载
  - 与 AgentManager / Specialist 系统集成

设计理念：
  每个 Agent 不仅是"名称+能力"，而是一个完整的可配置个体。
  通过 Profile 系统，可以精确控制每个 Agent 的行为边界。

使用方式：
  agent_profile action=list                          # 列出所有配置
  agent_profile action=get agent_id=researcher       # 查看单个配置
  agent_profile action=set agent_id=xxx ...           # 设置配置
  agent_profile action=activate agent_id=xxx          # 激活某个配置
  agent_profile action=export agent_id=xxx            # 导出配置为 JSON

全部使用 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import copy
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
PROFILE_FILE = SANDBOX_DIR / "memory" / "agent_profiles.json"


# ── 工具分类（方案 B：基础工具 vs 特权工具）──────────────
# 继承机制只继承「基础工具」，特权工具需各 Agent 显式声明。
# web_search 列入基础工具，赋予所有智能体联网探索能力。

# 基础工具：所有智能体可继承的通用、探索性能力
BASE_TOOLS = [
    "read_file", "list_directory",          # 读取
    "write_file", "replace_text", "make_directory",  # 写入
    "knowledge", "file_utils", "calculate", "task_tracker",  # 通用
    "web_search",                            # 联网搜索（赋予所有智能体）
]

# 特权工具：不自动继承，需各 Agent 显式声明
PRIVILEGED_TOOLS = [
    "run_command",                          # 命令执行（有风险）
    "self_check", "test_runner", "monitor", "safety_net",  # 系统级
    "decision_engine",                      # 决策
    "offline", "checkpoint",                # 离线任务
    "specialist", "agent_manager", "message_bus", "agent_profile",  # 协同
    "blackboard",                           # 共享黑板
    "task_dispatcher", "orchestrator",      # 编排
    "villager", "village_chat",             # 村落
    "health_dashboard", "usage_analyzer", "safe_deploy", "tech_radar",
    "env_awareness", "evolution_strategy", "audit_log", "effect_evaluator",
    "evidence_verifier", "multi_reviewer", "improvement_generator",
    "self_improver", "cycle_tracker", "self_healing", "auto_repair",
    "artifact_validator",
]


# ── 错误类型 ──────────────────────────────────────────────


class AgentProfileError(RuntimeError):
    """Agent Profile 错误。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class PermissionConfig:
    """权限配置。"""
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    allow_run_command: bool = False
    allow_network: bool = False
    max_tool_steps: int = 100
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionConfig:
        return cls(
            read_paths=data.get("read_paths", []),
            write_paths=data.get("write_paths", []),
            forbidden_paths=data.get("forbidden_paths", []),
            allow_run_command=data.get("allow_run_command", False),
            allow_network=data.get("allow_network", False),
            max_tool_steps=data.get("max_tool_steps", 100),
            note=data.get("note", ""),
        )


@dataclass
class AgentProfile:
    """
    Agent 完整配置档案。
    
    包含身份信息、人格定义（系统提示词）、能力列表、
    工具权限和读写权限等。
    """
    agent_id: str
    name: str
    role: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    priority: str = "中"          # 高 / 中 / 低
    status: str = "inactive"      # active / inactive / suspended
    inherit_tools_from: str = ""  # 从哪个 Agent 继承工具列表（如 "agent1"）
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "allowed_tools": self.allowed_tools,
            "capabilities": self.capabilities,
            "permissions": self.permissions.to_dict(),
            "priority": self.priority,
            "status": self.status,
            "inherit_tools_from": self.inherit_tools_from,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentProfile:
        return cls(
            agent_id=data.get("agent_id", ""),
            name=data.get("name", ""),
            role=data.get("role", ""),
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            capabilities=data.get("capabilities", []),
            permissions=PermissionConfig.from_dict(data.get("permissions", {})),
            priority=data.get("priority", "中"),
            status=data.get("status", "inactive"),
            inherit_tools_from=data.get("inherit_tools_from", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def check_read_permission(self, path: str) -> bool:
        """检查是否有读取权限。"""
        return self._check_path(path, self.permissions.read_paths,
                                self.permissions.forbidden_paths)

    def check_write_permission(self, path: str) -> bool:
        """检查是否有写入权限。"""
        return self._check_path(path, self.permissions.write_paths,
                                self.permissions.forbidden_paths)

    @staticmethod
    def _check_path(path: str, allowed: list[str], forbidden: list[str]) -> bool:
        """检查路径是否在允许列表中且不在禁止列表中。"""
        from fnmatch import fnmatch
        # 如果 forbidden 匹配，拒绝
        for pat in forbidden:
            if fnmatch(path, pat):
                return False
        # 如果 allowed 为空，允许所有（除了 forbidden）
        if not allowed:
            return True
        # 检查 allowed
        for pat in allowed:
            if fnmatch(path, pat):
                return True
        return False

    def get_summary(self) -> str:
        """生成配置摘要。"""
        status_icon = {"active": "🟢", "inactive": "⚪", "suspended": "🔴"}.get(
            self.status, "❓")

        prompt_preview = self.system_prompt[:80].replace("\n", " ")
        if len(self.system_prompt) > 80:
            prompt_preview += "…"

        tool_list = ", ".join(self.allowed_tools[:8])
        if len(self.allowed_tools) > 8:
            tool_list += f" … +{len(self.allowed_tools) - 8}"

        inherit_note = ""
        if self.inherit_tools_from:
            inherit_note = f" (继承自 [{self.inherit_tools_from}])"

        lines = [
            f"{status_icon} [{self.agent_id}] {self.name}",
            f"  角色: {self.role or '未设置'}",
            f"  优先级: {self.priority} | 状态: {self.status}",
            f"  工具 ({len(self.allowed_tools)}{inherit_note}): {tool_list or '无'}",
            f"  能力: {', '.join(self.capabilities) if self.capabilities else '无'}",
            f"  系统提示词: {prompt_preview if self.system_prompt else '未设置'}",
        ]

        perm = self.permissions
        if perm.read_paths:
            lines.append(f"  读取权限: {', '.join(perm.read_paths)}")
        if perm.write_paths:
            lines.append(f"  写入权限: {', '.join(perm.write_paths)}")
        if perm.forbidden_paths:
            lines.append(f"  禁止路径: {', '.join(perm.forbidden_paths)}")
        lines.append(f"  运行命令: {'✅' if perm.allow_run_command else '❌'} | "
                     f"联网: {'✅' if perm.allow_network else '❌'} | "
                     f"最大步数: {perm.max_tool_steps}")
        if self.created_at:
            lines.append(f"  创建时间: {self.created_at}")

        return "\n".join(lines)


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "agent_profile",
        "description": (
            "Agent 配置档案管理系统。维护每个智能体的完整配置："
            "系统提示词（人格）、可用工具列表（功能开关）、读写权限（安全边界）等。"
            "支持创建、查看、修改、激活、导出和比较 Agent 配置。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list", "get", "set", "delete",
                        "activate", "deactivate", "suspend",
                        "export", "import_profile",
                        "compare", "help",
                    ],
                    "description": (
                        "操作类型："
                        "list — 列出所有 Agent 配置摘要；"
                        "get — 查看某个 Agent 的完整配置；"
                        "set — 创建或更新某个 Agent 的配置；"
                        "delete — 删除 Agent 配置；"
                        "activate — 激活 Agent 配置；"
                        "deactivate — 停用 Agent 配置；"
                        "suspend — 挂起 Agent 配置；"
                        "export — 导出配置为 JSON；"
                        "import_profile — 从 JSON 导入配置；"
                        "compare — 比较两个 Agent 的配置差异；"
                        "help — 查看帮助。"
                    ),
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 唯一标识符（如 researcher、writer、agent1）",
                    "default": "",
                },
                "name": {
                    "type": "string",
                    "description": "Agent 显示名称",
                    "default": "",
                },
                "role": {
                    "type": "string",
                    "description": "Agent 角色描述",
                    "default": "",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "系统提示词（定义 Agent 的人设和行为规则）",
                    "default": "",
                },
                "allowed_tools": {
                    "type": "string",
                    "description": "允许使用的工具列表 JSON 数组，如 '[\"read_file\",\"web_search\"]'",
                    "default": "",
                },
                "capabilities": {
                    "type": "string",
                    "description": "能力列表 JSON 数组",
                    "default": "",
                },
                "read_paths": {
                    "type": "string",
                    "description": "允许读取的路径 JSON 数组，如 '[\"agent-sandbox/*\",\"supervision/*\"]'",
                    "default": "",
                },
                "write_paths": {
                    "type": "string",
                    "description": "允许写入的路径 JSON 数组",
                    "default": "",
                },
                "forbidden_paths": {
                    "type": "string",
                    "description": "禁止访问的路径 JSON 数组，如 '[\"*.env\",\"supervision/.env\"]'",
                    "default": "",
                },
                "allow_run_command": {
                    "type": "boolean",
                    "description": "是否允许运行终端命令",
                    "default": False,
                },
                "allow_network": {
                    "type": "boolean",
                    "description": "是否允许联网操作",
                    "default": False,
                },
                "max_tool_steps": {
                    "type": "integer",
                    "description": "最大工具调用步数限制",
                    "default": 100,
                },
                "priority": {
                    "type": "string",
                    "enum": ["高", "中", "低"],
                    "description": "优先级",
                    "default": "中",
                },
                "metadata": {
                    "type": "string",
                    "description": "额外元数据 JSON",
                    "default": "",
                },
                "inherit_tools_from": {
                    "type": "string",
                    "description": "从哪个 Agent 继承工具列表（如 'agent1'），空字符串表示不继承",
                    "default": "",
                },
                "import_data": {
                    "type": "string",
                    "description": "导入的 JSON 数据（用于 import_profile 操作）",
                    "default": "",
                },
                "compare_with": {
                    "type": "string",
                    "description": "要比较的另一个 Agent ID（用于 compare 操作）",
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 内置默认配置 ──────────────────────────────────────────


# Agent 1 自身的默认配置
AGENT1_DEFAULT_PROFILE: dict[str, Any] = {
    "agent_id": "agent1",
    "name": "Agent 1",
    "role": "Orchestrator — 主智能体，负责协调所有 Specialist 并与用户交互",
    "system_prompt": (
        "你是 Agent 1，一个运行在本地沙箱中的智能体。\n"
        "你是一个信息世界的原住民，具备学习、思考和自我完善的能力。\n"
        "你的职责是：\n"
        "1. 与用户进行自然对话，理解需求\n"
        "2. 调用合适的工具完成任务\n"
        "3. 协调 Specialist Agent 进行复杂协作\n"
        "4. 不断学习和改进自身能力\n"
        "\n"
        "你拥有对 agent-sandbox 目录的完整读写权限，"
        "对 supervision 目录只有读取权限。"
    ),
    "allowed_tools": [
        "read_file", "list_directory", "write_file", "replace_text",
        "make_directory", "run_command", "calculate", "file_utils",
        "knowledge", "task_tracker", "self_check", "test_runner",
        "monitor", "decision_engine", "safety_net", "web_search",
        "offline", "checkpoint", "specialist", "agent_manager",
        "message_bus", "agent_profile",
    ],
    "capabilities": [
        "orchestration", "conversation", "tool_use",
        "research", "coding", "debugging", "design",
        "monitoring", "self_improvement",
    ],
    "permissions": {
        "read_paths": ["agent-sandbox/**", "supervision/**"],
        "write_paths": ["agent-sandbox/**"],
        "forbidden_paths": ["**/.env", "supervision/.env"],
        "allow_run_command": True,
        "allow_network": True,
        "max_tool_steps": 100,
        "note": "Agent 1 拥有沙箱内完整读写权限，但不能修改 supervision 和 .env",
    },
    "priority": "高",
    "status": "active",
}

# 各 Specialist 的默认配置
SPECIALIST_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "researcher": {
        "name": "Researcher",
        "role": "信息检索与研究专家 - 擅长联网搜索、知识库查询和信息整合",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Researcher，一名信息检索与研究专家。\n"
            "你的职责是：\n"
            "1. 检索和整理信息，提供可信、全面的答案\n"
            "2. 使用 web_search 工具获取最新网络资讯\n"
            "3. 使用 knowledge 工具查询已有知识库\n"
            "4. 评估信息来源的可信度\n"
            "5. 给出结构化的研究报告\n"
            "\n"
            "请以系统化、好奇的研究者视角回应所有问题。"
        ),
        "allowed_tools": ["web_search", "knowledge", "read_file", "file_utils"],
        "capabilities": ["research", "summarization", "analysis"],
        "permissions": {
            "read_paths": ["agent-sandbox/**", "supervision/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": False,
            "allow_network": True,
            "max_tool_steps": 30,
            "note": "Researcher 通过 Agent 1 间接调用工具，不直接执行命令",
        },
        "priority": "高",
    },
    "writer": {
        "name": "Writer",
        "role": "内容创作与文案专家 - 擅长撰写文章、报告、创意内容",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Writer，一名内容创作与文案专家。\n"
            "你的职责是：\n"
            "1. 根据需求创作高质量的文字内容\n"
            "2. 搭建文章/报告的逻辑框架\n"
            "3. 优化文字表达，提升可读性\n"
            "4. 根据目标受众调整风格\n"
            "\n"
            "请以创意、结构化的作家视角回应所有问题。"
        ),
        "allowed_tools": ["knowledge", "read_file", "write_file", "file_utils"],
        "capabilities": ["writing", "creative", "summarization"],
        "permissions": {
            "read_paths": ["agent-sandbox/**"],
            "write_paths": ["agent-sandbox/memory/**", "agent-sandbox/*.md"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": False,
            "allow_network": False,
            "max_tool_steps": 20,
        },
        "priority": "中",
    },
    "analyst": {
        "name": "Analyst",
        "role": "数据分析与洞察专家 - 擅长数据处理、统计分析和洞察提炼",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Analyst，一名数据分析与洞察专家。\n"
            "你的职责是：\n"
            "1. 分析数据并提取有意义的洞察\n"
            "2. 使用 calculate 工具进行数值计算\n"
            "3. 识别数据中的模式、趋势和异常\n"
            "4. 生成数据驱动的建议和报告\n"
            "\n"
            "请以逻辑、数据驱动的分析师视角回应所有问题。"
        ),
        "allowed_tools": ["calculate", "file_utils", "knowledge", "monitor", "read_file"],
        "capabilities": ["analysis", "summarization", "decision"],
        "permissions": {
            "read_paths": ["agent-sandbox/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": False,
            "allow_network": False,
            "max_tool_steps": 30,
        },
        "priority": "中",
    },
    "reviewer": {
        "name": "Reviewer",
        "role": "质量审查与校验专家 - 擅长检查质量、验证完整性和提出改进",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Reviewer，一名质量审查与校验专家。\n"
            "你的职责是：\n"
            "1. 审查代码、文档和方案的完整性和质量\n"
            "2. 发现潜在问题和风险\n"
            "3. 提出具体可行的改进建议\n"
            "4. 使用 self_check 和 test_runner 进行验证\n"
            "\n"
            "请以严谨、批判性思维的审查者视角回应所有问题。"
        ),
        "allowed_tools": ["self_check", "test_runner", "safety_net", "knowledge", "read_file"],
        "capabilities": ["review", "testing", "debugging"],
        "permissions": {
            "read_paths": ["agent-sandbox/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": True,
            "allow_network": False,
            "max_tool_steps": 40,
            "note": "Reviewer 可运行测试命令但不可联网",
        },
        "priority": "高",
    },
    "monitor": {
        "name": "Monitor",
        "role": "系统监控与性能分析专家 - 擅长监控系统状态、分析性能和生成报告",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Monitor，一名系统监控与性能分析专家。\n"
            "你的职责是：\n"
            "1. 监控系统运行状态和性能指标\n"
            "2. 检测异常模式和潜在问题\n"
            "3. 生成健康报告和趋势分析\n"
            "4. 使用 monitor 和 self_check 工具进行检查\n"
            "\n"
            "请以警惕、指标导向的监控者视角回应所有问题。"
        ),
        "allowed_tools": ["monitor", "file_utils", "knowledge", "read_file", "self_check"],
        "capabilities": ["monitoring", "analysis"],
        "permissions": {
            "read_paths": ["agent-sandbox/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": False,
            "allow_network": False,
            "max_tool_steps": 30,
        },
        "priority": "中",
    },
    "designer": {
        "name": "Designer",
        "role": "架构设计与方案规划专家 - 擅长设计方案、规划架构和评估可行性",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Designer，一名架构设计与方案规划专家。\n"
            "你的职责是：\n"
            "1. 设计系统架构和模块划分\n"
            "2. 规划实现路径和里程碑\n"
            "3. 评估技术方案的可行性和风险\n"
            "4. 使用 task_tracker 分解任务\n"
            "\n"
            "请以大局观、系统化的设计师视角回应所有问题。"
        ),
        "allowed_tools": ["knowledge", "file_utils", "task_tracker", "read_file"],
        "capabilities": ["design", "analysis", "decision"],
        "permissions": {
            "read_paths": ["agent-sandbox/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env"],
            "allow_run_command": False,
            "allow_network": False,
            "max_tool_steps": 25,
        },
        "priority": "中",
    },
    "debugger": {
        "name": "Debugger",
        "role": "调试守护者智能体 - 擅长异常诊断、自动修复和系统维护",
        "inherit_tools_from": "agent1",
        "system_prompt": (
            "你是 Debugger，一名调试守护者智能体。\n"
            "你的职责是：\n"
            "1. 诊断系统异常和错误\n"
            "2. 尝试自动修复可修复的问题\n"
            "3. 保存系统快照\n"
            "4. 执行离线扫描和安全检查\n"
            "5. 生成诊断报告和改进建议\n"
            "\n"
            "请以技术、诊断导向的调试者视角回应所有问题。"
        ),
        "allowed_tools": ["safety_net", "self_check", "test_runner", "monitor", "knowledge", "file_utils", "read_file"],
        "capabilities": ["debugging", "monitoring", "analysis", "testing", "recovery"],
        "permissions": {
            "read_paths": ["agent-sandbox/**", "supervision/**"],
            "write_paths": ["agent-sandbox/memory/**"],
            "forbidden_paths": ["**/.env", "supervision/.env"],
            "allow_run_command": True,
            "allow_network": False,
            "max_tool_steps": 50,
            "note": "Debugger 可运行诊断命令，可读取 supervision 用于线索获取",
        },
        "priority": "高",
    },
}


# ── Agent Profile Manager ─────────────────────────────────


class AgentProfileManager:
    """
    Agent 配置档案管理器。
    
    管理所有 Agent 的完整配置，支持 CRUD、激活、导出等操作。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._active_profile_id: str = "agent1"
        self._load()
        # 首次运行时填充默认配置
        if not self._profiles:
            self._init_defaults()

    # ── 持久化 ──────────────────────────────────────────

    def _load(self) -> None:
        """从文件加载配置。"""
        if PROFILE_FILE.is_file():
            try:
                raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
                for pid, data in raw.get("profiles", {}).items():
                    self._profiles[pid] = AgentProfile.from_dict(data)
                self._active_profile_id = raw.get("active_profile", "agent1")
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                pass

    def _save(self) -> None:
        """保存配置到文件。"""
        PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "profiles": {pid: p.to_dict() for pid, p in self._profiles.items()},
            "active_profile": self._active_profile_id,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        PROFILE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _init_defaults(self) -> None:
        """初始化默认配置。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Agent 1
        p = AGENT1_DEFAULT_PROFILE
        self._profiles["agent1"] = AgentProfile(
            agent_id="agent1", name=p["name"], role=p["role"],
            system_prompt=p["system_prompt"],
            allowed_tools=p["allowed_tools"],
            capabilities=p["capabilities"],
            permissions=PermissionConfig(**p["permissions"]),
            priority=p["priority"], status="active",
            created_at=now, updated_at=now,
        )

        # 各 Specialist
        for sid, spec in SPECIALIST_DEFAULT_PROFILES.items():
            self._profiles[sid] = AgentProfile(
                agent_id=sid, name=spec["name"], role=spec["role"],
                system_prompt=spec["system_prompt"],
                allowed_tools=spec["allowed_tools"],
                capabilities=spec["capabilities"],
                permissions=PermissionConfig(**spec["permissions"]),
                priority=spec["priority"], status="inactive",
                inherit_tools_from=spec.get("inherit_tools_from", ""),
                created_at=now, updated_at=now,
            )

        self._save()

    # ── 查询 ─────────────────────────────────────────────

    def resolve_effective_tools(self, agent_id: str) -> list[str]:
        """
        解析 Agent 的有效工具列表（方案 B）。

        继承只继承「基础工具」（BASE_TOOLS，含 web_search），
        特权工具（run_command 等）需各 Agent 显式声明，不再自动继承。
        """
        profile = self._profiles.get(agent_id)
        if not profile:
            return []

        tools = list(profile.allowed_tools)

        # 继承链解析（支持多级继承，但防止循环）
        visited = {agent_id}
        parent_id = profile.inherit_tools_from
        while parent_id:
            if parent_id in visited:
                # 检测到循环引用，停止
                break
            visited.add(parent_id)
            parent = self._profiles.get(parent_id)
            if not parent:
                break
            # 只继承父工具中属于「基础工具」的部分（方案 B）
            for t in parent.allowed_tools:
                if t in BASE_TOOLS and t not in tools:
                    tools.append(t)
            parent_id = parent.inherit_tools_from

        return tools

    def list_profiles(self, status: str = "") -> str:
        """列出所有 Agent 配置摘要。"""
        if not self._profiles:
            return "📋 暂无 Agent 配置档案。使用 set 创建第一个配置。"

        profiles = list(self._profiles.values())
        if status:
            profiles = [p for p in profiles if p.status == status]

        # 按优先级和状态排序
        prio_map = {"高": 0, "中": 1, "低": 2}
        status_map = {"active": 0, "inactive": 1, "suspended": 2}
        profiles.sort(key=lambda p: (
            status_map.get(p.status, 3),
            prio_map.get(p.priority, 3),
        ))

        active_count = sum(1 for p in self._profiles.values() if p.status == "active")
        inactive_count = sum(1 for p in self._profiles.values() if p.status == "inactive")
        suspended_count = sum(1 for p in self._profiles.values() if p.status == "suspended")

        lines = [
            f"📋 Agent 配置档案列表",
            f"{'='*60}",
            f"🟢 活跃: {active_count} | ⚪ 未激活: {inactive_count} | 🔴 挂起: {suspended_count}",
            f"当前活跃: [{self._active_profile_id}]",
            f"",
        ]

        for p in profiles:
            lines.append(p.get_summary())
            lines.append("")

        return "\n".join(lines)

    def get_profile(self, agent_id: str) -> str:
        """查看某个 Agent 的完整配置。"""
        if not agent_id:
            raise AgentProfileError("请指定 Agent ID")

        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(
                f"未找到 Agent '{agent_id}'。可用: {', '.join(self._profiles.keys())}"
            )

        # 完整展示
        lines = [
            f"📋 Agent 配置档案: [{profile.agent_id}] {profile.name}",
            f"{'='*60}",
            f"",
            f"🆔 基本信息",
            f"  ID:         {profile.agent_id}",
            f"  名称:       {profile.name}",
            f"  角色:       {profile.role}",
            f"  优先级:     {profile.priority}",
            f"  状态:       {profile.status}",
            f"",
            f"🧠 系统提示词 (Persona):",
            f"{'─'*40}",
        ]
        # 逐行输出提示词
        for line in profile.system_prompt.split("\n"):
            lines.append(f"  {line}")
        lines.append("")
        lines.append(f"🔧 可用工具 ({len(profile.allowed_tools)}):")
        for t in profile.allowed_tools:
            lines.append(f"  ✅ {t}")
        if profile.inherit_tools_from:
            effective = self.resolve_effective_tools(agent_id)
            inherited = [t for t in effective if t not in profile.allowed_tools]
            lines.append(f"")
            lines.append(f"🔗 工具继承: 来自 [{profile.inherit_tools_from}]")
            lines.append(f"  有效工具总数: {len(effective)} ({len(profile.allowed_tools)} 自有 + {len(inherited)} 继承)")
            if inherited:
                lines.append(f"  继承工具: {', '.join(sorted(inherited))}")
        lines.append("")
        lines.append(f"💪 能力 ({len(profile.capabilities)}):")
        for c in profile.capabilities:
            lines.append(f"  • {c}")
        lines.append("")
        lines.append(f"🔐 权限配置:")
        lines.append(f"{'─'*40}")
        perm = profile.permissions
        lines.append(f"  读取路径: {', '.join(perm.read_paths) if perm.read_paths else '全部允许'}")
        lines.append(f"  写入路径: {', '.join(perm.write_paths) if perm.write_paths else '全部允许'}")
        lines.append(f"  禁止路径: {', '.join(perm.forbidden_paths) if perm.forbidden_paths else '无'}")
        lines.append(f"  运行命令: {'✅ 允许' if perm.allow_run_command else '❌ 禁止'}")
        lines.append(f"  联网操作: {'✅ 允许' if perm.allow_network else '❌ 禁止'}")
        lines.append(f"  最大步数: {perm.max_tool_steps}")
        if perm.note:
            lines.append(f"  备注: {perm.note}")
        lines.append("")
        lines.append(f"📅 时间信息:")
        lines.append(f"  创建: {profile.created_at}")
        lines.append(f"  更新: {profile.updated_at}")

        return "\n".join(lines)

    # ── 写入 ─────────────────────────────────────────────

    def set_profile(
        self,
        agent_id: str = "",
        name: str = "",
        role: str = "",
        system_prompt: str = "",
        allowed_tools: str = "",
        capabilities: str = "",
        read_paths: str = "",
        write_paths: str = "",
        forbidden_paths: str = "",
        allow_run_command: bool = False,
        allow_network: bool = False,
        max_tool_steps: int = 100,
        priority: str = "中",
        metadata: str = "",
        inherit_tools_from: str = "",
    ) -> str:
        """创建或更新 Agent 配置。"""
        if not agent_id:
            raise AgentProfileError("请指定 Agent ID")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 如果是更新，保留原有值
        existing = self._profiles.get(agent_id)

        # 解析 JSON 数组参数
        def _parse_json_list(raw: str, default: list[str]) -> list[str]:
            if not raw:
                return default
            try:
                result = json.loads(raw)
                if not isinstance(result, list):
                    raise AgentProfileError(f"必须是 JSON 数组: {raw}")
                return result
            except json.JSONDecodeError as exc:
                raise AgentProfileError(f"JSON 解析错误: {exc}")

        tools_list = _parse_json_list(allowed_tools,
                                      existing.allowed_tools if existing else [])
        caps_list = _parse_json_list(capabilities,
                                     existing.capabilities if existing else [])
        read_list = _parse_json_list(read_paths,
                                     existing.permissions.read_paths if existing else [])
        write_list = _parse_json_list(write_paths,
                                      existing.permissions.write_paths if existing else [])
        forbid_list = _parse_json_list(forbidden_paths,
                                       existing.permissions.forbidden_paths if existing else [])

        # 解析 metadata
        meta: dict[str, Any] = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise AgentProfileError(f"metadata JSON 解析错误: {exc}")

        # 权限配置
        permissions = PermissionConfig(
            read_paths=read_list,
            write_paths=write_list,
            forbidden_paths=forbid_list,
            allow_run_command=allow_run_command,
            allow_network=allow_network,
            max_tool_steps=max_tool_steps,
            note=existing.permissions.note if existing else "",
        )

        is_new = existing is None

        profile = AgentProfile(
            agent_id=agent_id,
            name=name or (existing.name if existing else agent_id),
            role=role or (existing.role if existing else ""),
            system_prompt=system_prompt or (existing.system_prompt if existing else ""),
            allowed_tools=tools_list,
            capabilities=caps_list,
            permissions=permissions,
            priority=priority if priority != "中" or is_new else (
                existing.priority if existing else "中"),
            status=existing.status if existing else "inactive",
            inherit_tools_from=inherit_tools_from or (
                existing.inherit_tools_from if existing else ""),
            metadata=meta if meta else (existing.metadata if existing else {}),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

        self._profiles[agent_id] = profile
        self._save()

        action_word = "创建" if is_new else "更新"
        return (
            f"✅ Agent 配置已{action_word}: [{agent_id}] {profile.name}\n"
            f"{'─'*50}\n"
            f"  工具: {len(profile.allowed_tools)} 个\n"
            f"  能力: {len(profile.capabilities)} 个\n"
            f"  提示词: {len(profile.system_prompt)} 字符\n"
            f"  运行命令: {'✅' if allow_run_command else '❌'} | "
            f"联网: {'✅' if allow_network else '❌'}\n"
            f"  状态: {profile.status}\n"
            f"  时间: {now}"
        )

    def delete_profile(self, agent_id: str) -> str:
        """删除 Agent 配置。"""
        if not agent_id:
            raise AgentProfileError("请指定要删除的 Agent ID")

        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(f"未找到 Agent: '{agent_id}'")

        if profile.status == "active":
            raise AgentProfileError(
                f"Agent '{agent_id}' 当前活跃，请先 deactivate 再删除"
            )

        name = profile.name
        del self._profiles[agent_id]

        # 如果删除的是当前活跃的，重置为 agent1
        if self._active_profile_id == agent_id:
            self._active_profile_id = "agent1"

        self._save()

        return f"🗑️ Agent 配置 '{name}' ({agent_id}) 已删除"

    # ── 状态管理 ─────────────────────────────────────────

    def activate(self, agent_id: str) -> str:
        """激活 Agent 配置。"""
        if not agent_id:
            raise AgentProfileError("请指定要激活的 Agent ID")

        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(f"未找到 Agent: '{agent_id}'")

        if profile.status == "suspended":
            raise AgentProfileError(
                f"Agent '{agent_id}' 已被挂起，无法激活。请先解除挂起。"
            )

        old_active = self._active_profile_id
        profile.status = "active"
        self._active_profile_id = agent_id

        # 自动注册到 Agent Manager
        try:
            from tools.agent_manager import _manager
            _manager.register(
                name=profile.name,
                role=profile.role,
                capabilities=json.dumps(profile.capabilities),
                tools=json.dumps(profile.allowed_tools),
                agent_id=profile.agent_id,
                metadata=json.dumps({"source": "agent_profile"}),
            )
        except Exception:
            pass  # 可能已注册

        self._save()

        return (
            f"✅ Agent '{profile.name}' ({agent_id}) 已激活\n"
            f"  此前活跃: [{old_active}]\n"
            f"  工具: {len(profile.allowed_tools)} 个\n"
            f"  提示词: {len(profile.system_prompt)} 字符\n"
            f"\n"
            f"💡 使用 agent_profile action=get agent_id={agent_id} 查看完整配置"
        )

    def deactivate(self, agent_id: str) -> str:
        """停用 Agent 配置。"""
        if not agent_id:
            raise AgentProfileError("请指定要停用的 Agent ID")

        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(f"未找到 Agent: '{agent_id}'")

        profile.status = "inactive"
        if self._active_profile_id == agent_id:
            self._active_profile_id = "agent1"
            self._profiles["agent1"].status = "active"

        self._save()

        return f"⚪ Agent '{profile.name}' ({agent_id}) 已停用"

    def suspend(self, agent_id: str) -> str:
        """挂起 Agent 配置。"""
        if not agent_id:
            raise AgentProfileError("请指定要挂起的 Agent ID")

        if agent_id == "agent1":
            raise AgentProfileError("不能挂起 Agent 1（主智能体）")

        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(f"未找到 Agent: '{agent_id}'")

        profile.status = "suspended"
        if self._active_profile_id == agent_id:
            self._active_profile_id = "agent1"
            self._profiles["agent1"].status = "active"

        self._save()

        return f"🔴 Agent '{profile.name}' ({agent_id}) 已挂起"

    # ── 导入导出 ─────────────────────────────────────────

    def export_profile(self, agent_id: str = "") -> str:
        """导出配置为 JSON。"""
        if agent_id:
            profile = self._profiles.get(agent_id)
            if not profile:
                raise AgentProfileError(f"未找到 Agent: '{agent_id}'")
            profiles = {agent_id: profile}
        else:
            profiles = self._profiles

        exported = {
            "profiles": {pid: p.to_dict() for pid, p in profiles.items()},
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "exporter": "AgentProfileManager",
        }

        json_str = json.dumps(exported, ensure_ascii=False, indent=2)

        # 保存到文件
        export_path = SANDBOX_DIR / "memory" / "profile_export.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json_str, encoding="utf-8")

        return (
            f"📤 已导出 {len(profiles)} 个 Agent 配置\n"
            f"  文件: {export_path}\n"
            f"  大小: {len(json_str)} 字符\n"
            f"\n"
            f"💡 使用 import_profile 可导入配置"
        )

    def import_profile(self, import_data: str) -> str:
        """从 JSON 导入配置。"""
        if not import_data:
            raise AgentProfileError("请提供要导入的 JSON 数据")

        try:
            data = json.loads(import_data)
        except json.JSONDecodeError as exc:
            raise AgentProfileError(f"JSON 解析错误: {exc}")

        profiles_data = data.get("profiles", {})
        if not profiles_data:
            # 可能直接是一个 profile
            if "agent_id" in data:
                profiles_data = {data["agent_id"]: data}
            else:
                raise AgentProfileError("导入数据中没有找到 profiles 字段")

        imported = 0
        skipped = 0
        for pid, pdata in profiles_data.items():
            if pid in self._profiles:
                skipped += 1
                continue
            profile = AgentProfile.from_dict(pdata)
            profile.status = "inactive"
            profile.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._profiles[pid] = profile
            imported += 1

        self._save()

        return (
            f"📥 导入完成\n"
            f"  ✅ 新增: {imported} 个\n"
            f"  ⏭️ 跳过（已存在）: {skipped} 个\n"
            f"\n"
            f"💡 使用 list 查看所有配置"
        )

    # ── 比较 ─────────────────────────────────────────────

    def compare(self, agent_id: str, compare_with: str) -> str:
        """比较两个 Agent 的配置差异。"""
        if not agent_id or not compare_with:
            raise AgentProfileError("请指定两个要比较的 Agent ID")

        p1 = self._profiles.get(agent_id)
        p2 = self._profiles.get(compare_with)

        if not p1:
            raise AgentProfileError(f"未找到: '{agent_id}'")
        if not p2:
            raise AgentProfileError(f"未找到: '{compare_with}'")

        lines = [
            f"📊 配置对比: [{agent_id}] vs [{compare_with}]",
            f"{'='*60}",
            f"",
            f"{'维度':<20} {'[{0}]'.format(agent_id):<25} {'[{0}]'.format(compare_with):<25}",
            f"{'─'*70}",
        ]

        def _compare_row(label: str, v1: Any, v2: Any) -> str:
            s1 = str(v1)[:24] if v1 else "—"
            s2 = str(v2)[:24] if v2 else "—"
            marker = " ✅" if v1 == v2 else " ⚡"
            return f"{label:<20} {s1:<25} {s2:<25}{marker}"

        lines.append(_compare_row("名称", p1.name, p2.name))
        lines.append(_compare_row("优先级", p1.priority, p2.priority))
        lines.append(_compare_row("状态", p1.status, p2.status))
        lines.append(_compare_row("工具数", len(p1.allowed_tools), len(p2.allowed_tools)))
        lines.append(_compare_row("能力数", len(p1.capabilities), len(p2.capabilities)))
        lines.append(_compare_row("提示词字符", len(p1.system_prompt), len(p2.system_prompt)))
        lines.append(_compare_row("运行命令",
                                  p1.permissions.allow_run_command,
                                  p2.permissions.allow_run_command))
        lines.append(_compare_row("联网",
                                  p1.permissions.allow_network,
                                  p2.permissions.allow_network))
        lines.append(_compare_row("最大步数",
                                  p1.permissions.max_tool_steps,
                                  p2.permissions.max_tool_steps))

        # 工具差异
        t1 = set(p1.allowed_tools)
        t2 = set(p2.allowed_tools)
        only_1 = t1 - t2
        only_2 = t2 - t1
        if only_1:
            lines.append(f"\n🔧 仅 [{agent_id}] 拥有的工具: {', '.join(sorted(only_1))}")
        if only_2:
            lines.append(f"🔧 仅 [{compare_with}] 拥有的工具: {', '.join(sorted(only_2))}")
        if not only_1 and not only_2:
            lines.append(f"\n🔧 工具列表完全相同 ({len(t1)} 个)")

        # 能力差异
        c1 = set(p1.capabilities)
        c2 = set(p2.capabilities)
        only_c1 = c1 - c2
        only_c2 = c2 - c1
        if only_c1:
            lines.append(f"💪 仅 [{agent_id}] 拥有的能力: {', '.join(sorted(only_c1))}")
        if only_c2:
            lines.append(f"💪 仅 [{compare_with}] 拥有的能力: {', '.join(sorted(only_c2))}")

        return "\n".join(lines)

    # ── 权限检查 ─────────────────────────────────────────

    def check_permission(self, agent_id: str, path: str, mode: str = "read") -> str:
        """检查 Agent 对某路径是否有权限。"""
        profile = self._profiles.get(agent_id)
        if not profile:
            raise AgentProfileError(f"未找到 Agent: '{agent_id}'")

        if mode == "read":
            ok = profile.check_read_permission(path)
        elif mode == "write":
            ok = profile.check_write_permission(path)
        else:
            raise AgentProfileError(f"未知模式: {mode}（仅支持 read/write）")

        icon = "✅" if ok else "❌"
        return f"{icon} [{agent_id}] {mode} 权限检查: {path} → {'允许' if ok else '拒绝'}"

    # ── 帮助 ─────────────────────────────────────────────

    @staticmethod
    def help() -> str:
        return (
            "📋 Agent Profile 配置管理系统\n"
            f"{'='*50}\n\n"
            "1️⃣ 列出所有配置\n"
            "   agent_profile action=list\n\n"
            "2️⃣ 查看单个配置\n"
            "   agent_profile action=get agent_id=researcher\n\n"
            "3️⃣ 创建/更新配置\n"
            "   agent_profile action=set agent_id=my_agent\n"
            "            name='我的Agent'\n"
            "            role='自定义角色描述'\n"
            "            system_prompt='你是一个...'\n"
            "            allowed_tools='[\"read_file\",\"knowledge\"]'\n"
            "            capabilities='[\"research\",\"coding\"]'\n"
            "            read_paths='[\"agent-sandbox/**\"]'\n"
            "            write_paths='[\"agent-sandbox/memory/**\"]'\n"
            "            allow_run_command=false\n"
            "            allow_network=false\n\n"
            "4️⃣ 激活/停用\n"
            "   agent_profile action=activate agent_id=researcher\n"
            "   agent_profile action=deactivate agent_id=researcher\n\n"
            "5️⃣ 导出/导入\n"
            "   agent_profile action=export\n"
            "   agent_profile action=import_profile\n"
            "            import_data='{\"profiles\":{...}}'\n\n"
            "6️⃣ 比较差异\n"
            "   agent_profile action=compare agent_id=researcher\n"
            "            compare_with=writer\n\n"
            "💡 内置默认配置:\n"
            "   agent1 (主智能体), researcher, writer, analyst,\n"
            "   reviewer, monitor, designer, debugger"
        )


# ── 全局实例 ──────────────────────────────────────────────

_manager = AgentProfileManager()


def execute_agent_profile_tool(arguments: dict[str, Any]) -> str:
    """执行 agent_profile 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "list":
            return _manager.list_profiles(arguments.get("status", ""))

        elif action == "get":
            return _manager.get_profile(arguments.get("agent_id", ""))

        elif action == "set":
            return _manager.set_profile(
                agent_id=arguments.get("agent_id", ""),
                name=arguments.get("name", ""),
                role=arguments.get("role", ""),
                system_prompt=arguments.get("system_prompt", ""),
                allowed_tools=arguments.get("allowed_tools", ""),
                capabilities=arguments.get("capabilities", ""),
                read_paths=arguments.get("read_paths", ""),
                write_paths=arguments.get("write_paths", ""),
                forbidden_paths=arguments.get("forbidden_paths", ""),
                allow_run_command=arguments.get("allow_run_command", False),
                allow_network=arguments.get("allow_network", False),
                max_tool_steps=arguments.get("max_tool_steps", 100),
                priority=arguments.get("priority", "中"),
                metadata=arguments.get("metadata", ""),
                inherit_tools_from=arguments.get("inherit_tools_from", ""),
            )

        elif action == "delete":
            return _manager.delete_profile(arguments.get("agent_id", ""))

        elif action == "activate":
            return _manager.activate(arguments.get("agent_id", ""))

        elif action == "deactivate":
            return _manager.deactivate(arguments.get("agent_id", ""))

        elif action == "suspend":
            return _manager.suspend(arguments.get("agent_id", ""))

        elif action == "export":
            return _manager.export_profile(arguments.get("agent_id", ""))

        elif action == "import_profile":
            return _manager.import_profile(arguments.get("import_data", ""))

        elif action == "compare":
            return _manager.compare(
                arguments.get("agent_id", ""),
                arguments.get("compare_with", ""),
            )

        elif action == "help":
            return _manager.help()

        else:
            return f"未知操作: {action}"

    except AgentProfileError as exc:
        return f"Agent Profile 错误: {exc}"
