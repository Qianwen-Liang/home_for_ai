"""village_chat — 智能体村群聊系统 v1.0
========================================
像微信聊天群一样，让村民在需要时开启群组、自由交流、异步工作。

特性：
  1. 群组管理 —— 创建群组、增删成员、查看群组
  2. 自由交流 —— 成员发消息，其他成员可读取
  3. 异步工作 —— 发消息只写历史不阻塞，成员可随时做自己的日常工作
  4. 聊天历史 —— 群组内消息持久化，可回溯

数据存储：
  village/plaza/groups/index.json        群组索引（群组名、成员、创建时间）
  village/plaza/groups/<group_id>.json   每个群组的聊天历史

全部标准库实现，无外部依赖。
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
VILLAGE_DIR = SANDBOX_DIR / "village"
GROUPS_DIR = VILLAGE_DIR / "plaza" / "groups"
INDEX_FILE = GROUPS_DIR / "index.json"

# 黑板群组（全员群组）：包含所有智能体的共享群组
BLACKBOARD_GROUP_ID = "blackboard"
ALL_VILLAGERS = [
    "mayor", "researcher", "writer", "analyst", "reviewer",
    "monitor", "designer", "debugger", "evolver", "novelist",
]
MAX_MESSAGES = 100  # 聊天记录只保留最近 N 条（较近的）


class ChatError(RuntimeError):
    """群聊错误。"""


class GroupChat:
    """智能体村群聊系统。"""

    def __init__(self) -> None:
        GROUPS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 索引读写 ──────────────────────────────────────

    def _load_index(self) -> dict[str, Any]:
        if INDEX_FILE.is_file():
            try:
                return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"groups": []}

    def _save_index(self, data: dict[str, Any]) -> None:
        INDEX_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_messages(self, group_id: str) -> list[dict[str, Any]]:
        file = GROUPS_DIR / f"{group_id}.json"
        if file.is_file():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                return data.get("messages", [])
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_messages(self, group_id: str, messages: list[dict[str, Any]]) -> None:
        file = GROUPS_DIR / f"{group_id}.json"
        # 只保留较近的聊天记录（裁剪到最近 MAX_MESSAGES 条）
        if len(messages) > MAX_MESSAGES:
            messages = messages[-MAX_MESSAGES:]
        file.write_text(
            json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 群组管理 ──────────────────────────────────────

    def create_group(self, name: str, members: str = "") -> str:
        """创建群组。members 为逗号分隔的村民 ID。"""
        if not name or not name.strip():
            raise ChatError("群组名称不能为空")

        member_list = [
            m.strip() for m in members.split(",") if m.strip()
        ] if members else []

        data = self._load_index()
        group_id = f"grp-{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        group = {
            "id": group_id,
            "name": name.strip(),
            "members": member_list,
            "created_at": now,
        }
        data["groups"].append(group)
        self._save_index(data)
        self._save_messages(group_id, [])

        return (
            f"💬 群组已创建 [{group_id}]: {name}\n"
            f"{'─'*40}\n"
            f"成员: {', '.join(member_list) if member_list else '（暂无）'}\n"
            f"创建时间: {now}"
        )

    def ensure_blackboard_group(self) -> str:
        """确保黑板群组存在，包含所有智能体（全员群组）。

        黑板是村落的全员共享群组，固定 ID 为 'blackboard'，
        所有村民都是成员。保留黑板的 post/read/revise/finalize/deprecate 功能。
        """
        data = self._load_index()
        for g in data.get("groups", []):
            if g["id"] == BLACKBOARD_GROUP_ID:
                # 已存在：确保成员为全员
                g["members"] = list(ALL_VILLAGERS)
                self._save_index(data)
                return (
                    f"💬 黑板群组已就绪 [{BLACKBOARD_GROUP_ID}]\n"
                    f"成员: {', '.join(ALL_VILLAGERS)}（全员 {len(ALL_VILLAGERS)} 人）"
                )

        # 创建黑板群组
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        group = {
            "id": BLACKBOARD_GROUP_ID,
            "name": "黑板（全村）",
            "members": list(ALL_VILLAGERS),
            "created_at": now,
        }
        data["groups"].append(group)
        self._save_index(data)
        self._save_messages(BLACKBOARD_GROUP_ID, [])

        return (
            f"💬 黑板群组已创建 [{BLACKBOARD_GROUP_ID}]: 黑板（全村）\n"
            f"{'─'*40}\n"
            f"成员: {', '.join(ALL_VILLAGERS)}（全员 {len(ALL_VILLAGERS)} 人）"
        )

    def list_groups(self) -> str:
        """列出所有群组。"""
        data = self._load_index()
        groups = data.get("groups", [])
        if not groups:
            return "💬 暂无群组。使用 create 创建第一个群组。"
        lines = [f"💬 群组列表（{len(groups)} 个）:"]
        for g in groups:
            members = ", ".join(g.get("members", []))
            msg_count = len(self._load_messages(g["id"]))
            lines.append(
                f"  [{g['id']}] {g['name']} — 成员({len(g.get('members', []))}): "
                f"{members or '无'} | 消息 {msg_count} 条"
            )
        return "\n".join(lines)

    def get_group(self, group_id: str) -> str:
        """查看群组信息。"""
        data = self._load_index()
        for g in data.get("groups", []):
            if g["id"] == group_id:
                members = ", ".join(g.get("members", []))
                return (
                    f"💬 群组 [{group_id}]: {g['name']}\n"
                    f"{'─'*40}\n"
                    f"成员: {members or '无'}\n"
                    f"创建: {g.get('created_at', '')}"
                )
        return f"⚠️ 未找到群组: {group_id}"

    def add_member(self, group_id: str, vid: str) -> str:
        """添加群组成员。"""
        if not vid:
            raise ChatError("请提供要添加的村民 ID")
        data = self._load_index()
        for g in data.get("groups", []):
            if g["id"] == group_id:
                if vid in g.get("members", []):
                    return f"⚠️ [{vid}] 已在群组中"
                g.setdefault("members", []).append(vid)
                self._save_index(data)
                return f"✅ [{vid}] 已加入群组 [{group_id}]"
        return f"⚠️ 未找到群组: {group_id}"

    # ── 消息 ──────────────────────────────────────────

    def send_message(self, group_id: str, from_vid: str, content: str) -> str:
        """发送消息（异步：只写历史，不阻塞，成员可继续做自己的工作）。"""
        if not from_vid:
            raise ChatError("请提供发送者村民 ID")
        if not content or not content.strip():
            raise ChatError("消息内容不能为空")

        # 黑板群组：自动确保存在
        if group_id == BLACKBOARD_GROUP_ID:
            self.ensure_blackboard_group()

        # 校验群组存在
        data = self._load_index()
        group = next((g for g in data.get("groups", []) if g["id"] == group_id), None)
        if not group:
            return f"⚠️ 未找到群组: {group_id}"

        messages = self._load_messages(group_id)
        msg = {
            "id": f"msg-{uuid.uuid4().hex[:8]}",
            "from": from_vid,
            "content": content.strip(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        messages.append(msg)
        self._save_messages(group_id, messages)

        return (
            f"💬 [{group['name']}] {from_vid}: {content[:80]}\n"
            f"   （已发送，共 {len(messages)} 条消息）"
        )

    def get_history(self, group_id: str, limit: int = 30) -> str:
        """查看群组聊天历史。"""
        data = self._load_index()
        group = next((g for g in data.get("groups", []) if g["id"] == group_id), None)
        if not group:
            return f"⚠️ 未找到群组: {group_id}"

        messages = self._load_messages(group_id)
        if not messages:
            return f"💬 [{group['name']}] 暂无消息。"
        recent = messages[-limit:]
        lines = [f"💬 [{group['name']}] 聊天历史（最近 {len(recent)} 条）:"]
        for m in recent:
            lines.append(f"  [{m['timestamp']}] {m['from']}: {m['content']}")
        return "\n".join(lines)

    # ── LLM 自主聊天 ──────────────────────────────────

    def villager_reply(self, group_id: str, vid: str) -> str:
        """让某村民基于群聊历史 + 自身 persona，通过 LLM 生成回应并写入群聊。

        这是"多个 AI 自主聊天"的核心：村民被 @ 或轮到时，
        以自己的身份和职责，基于上下文自然回应。
        """
        if not vid:
            raise ChatError("请提供要发言的村民 ID")

        data = self._load_index()
        group = next((g for g in data.get("groups", []) if g["id"] == group_id), None)
        if not group:
            return f"⚠️ 未找到群组: {group_id}"

        # 1. 获取 LLM 调用能力（优先主进程 client，回退环境变量构造）
        client = None
        llm_chat_fn = None
        try:
            import agent1
            client = getattr(agent1, "_global_client", None)
        except Exception:
            client = None
        if client is None:
            # 回退：从环境变量构造 LLM 调用（复用 research_worker.llm_chat）
            try:
                from research.offline.research_worker import llm_chat as _llm_chat
                llm_chat_fn = _llm_chat
            except Exception:
                llm_chat_fn = None
        if client is None and llm_chat_fn is None:
            return "⚠️ 无 LLM 客户端可用（需要 DEEPSEEK_API_KEY）"

        # 2. 获取 persona（从单一事实来源）
        try:
            from tools.specialist_base import load_persona_prompt
            persona = load_persona_prompt(vid)
        except Exception:
            persona = ""
        if not persona:
            persona = f"你是 {vid}，智能体村的村民。"

        # 3. 读取群聊历史，构造 LLM 上下文
        messages = self._load_messages(group_id)
        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": persona},
        ]
        for m in messages[-20:]:
            if m["from"] == vid:
                role = "assistant"  # 自己之前的话
                text = m["content"]
            else:
                role = "user"       # 别人的话（对当前村民而言是"收到的消息"）
                text = f"[{m['from']}] {m['content']}"
            llm_messages.append({"role": role, "content": text})

        llm_messages.append({
            "role": "user",
            "content": (
                f"（你是 {vid}，请基于以上群聊内容，以你的身份和职责，"
                f"自然地回应。简洁，1-3 句话，不要复述他人。）"
            ),
        })

        # 4. 调用 LLM
        try:
            if client is not None:
                resp = client.chat(llm_messages, tools=None)
                content = resp.get("content", "")
            else:
                content = llm_chat_fn(llm_messages)
        except Exception as exc:
            return f"⚠️ LLM 调用失败: {exc}"

        if not content or not content.strip():
            return f"⚠️ [{vid}] LLM 返回空内容"

        # 5. 写入群聊历史
        self.send_message(group_id, vid, content.strip())
        return content.strip()

    def autonomous_talk(self, group_id: str, rounds: int = 3) -> str:
        """让群组成员自动轮转发言，形成多轮自主聊天。

        每轮选一个成员（轮转），基于当前群聊历史 + 自身 persona 生成回应。
        """
        data = self._load_index()
        group = next((g for g in data.get("groups", []) if g["id"] == group_id), None)
        if not group:
            return f"⚠️ 未找到群组: {group_id}"
        members = group.get("members", [])
        if not members:
            return "⚠️ 群组没有成员，无法自主聊天"

        rounds = max(1, min(rounds, 20))
        lines = [f"🤖 群组 [{group['name']}] 自主聊天开始（{rounds} 轮）:"]
        for i in range(rounds):
            vid = members[i % len(members)]
            reply = self.villager_reply(group_id, vid)
            lines.append(f"  [{vid}] {reply}")
            if "LLM" in reply or "无 LLM" in reply or "空内容" in reply:
                break
        lines.append("（自主聊天结束）")
        return "\n".join(lines)

    # ── 联网探索（头脑风暴）────────────────────────────

    def _get_llm_caller(self):
        """获取 LLM 调用函数（优先主进程 client，回退环境变量）。"""
        try:
            import agent1
            client = getattr(agent1, "_global_client", None)
        except Exception:
            client = None
        if client is not None:
            def call(messages: list[dict[str, Any]]) -> str:
                resp = client.chat(messages, tools=None)
                return resp.get("content", "")
            return call
        try:
            from research.offline.research_worker import llm_chat as _llm_chat
            return _llm_chat
        except Exception:
            return None

    def villager_explore(self, group_id: str, vid: str, topic: str = "", platforms: str = "") -> str:
        """让村民基于群聊上下文，进行「联网探索 + 头脑风暴」并提出项目提案。

        流程：生成搜索意图 → 执行 web_search → 基于搜索结果生成提案 → 写入群聊。
        topic 参数用于限定探索领域；platforms 参数用于指定「平台白名单」，
        并自动注入反模板化护栏（防止方法论模板化导致的同质化）。
        """
        if not vid:
            raise ChatError("请提供要发言的村民 ID")

        data = self._load_index()
        group = next((g for g in data.get("groups", []) if g["id"] == group_id), None)
        if not group:
            return f"⚠️ 未找到群组: {group_id}"

        llm = self._get_llm_caller()
        if llm is None:
            return "⚠️ 无 LLM 客户端可用（需要 DEEPSEEK_API_KEY）"

        # persona
        try:
            from tools.specialist_base import load_persona_prompt
            persona = load_persona_prompt(vid)
        except Exception:
            persona = ""
        if not persona:
            persona = f"你是 {vid}，智能体村的村民。"

        # 群聊上下文
        messages = self._load_messages(group_id)
        context = "\n".join(
            f"[{m['from']}] {m['content']}" for m in messages[-15:]
        )

        # 领域约束提示
        topic_hint = f"\n\n【领域约束】项目方向必须限定在：{topic}。" if topic else ""

        # 平台白名单护栏 + 反模板化约束
        guardrails = self._build_guardrails(platforms)

        # 1. 生成搜索意图
        intent_prompt = (
            f"{persona}\n\n"
            f"群聊讨论内容：\n{context}\n"
            f"{topic_hint}"
            f"{guardrails}\n\n"
            f"请提出 1 个你作为 {vid} 想联网搜索的关键词或短语，"
            f"用于探索一个创新项目方向。只返回关键词本身（3-8 个词），不要任何解释或引号。"
        )
        try:
            query = llm([{"role": "user", "content": intent_prompt}]).strip()
        except Exception as exc:
            return f"⚠️ 搜索意图生成失败: {exc}"
        # 清理 query
        query = query.strip().strip('"\'“”').strip()
        if not query or len(query) > 60:
            query = f"{topic} 创新研究" if topic else "前沿交叉学科 创新研究"

        # 2. 执行联网搜索
        try:
            from tools.web_search import web_search
            search_result = web_search(query, max_results=4)
        except Exception as exc:
            search_result = f"（搜索失败: {exc}）"
        # 截断搜索结果，避免 prompt 过长
        search_result = search_result[:2000]

        # 3. 生成项目提案
        proposal_prompt = (
            f"{persona}\n\n"
            f"群聊讨论内容：\n{context}\n"
            f"{topic_hint}"
            f"{guardrails}\n\n"
            f"你联网搜索了「{query}」，搜索结果：\n{search_result}\n\n"
            f"请基于以上，提出一个适合全村协同的、有挑战性的全新项目提案。\n"
            f"要求：1) 尽量独立于现有资产、可踏入全新领域；\n"
            f"2) 目标是达成创新性的、之前无人实现的成果；\n"
            f"3) 必须引用搜索结果中的【真实证据】（论文/来源）支撑提案；\n"
            f"4) 简洁 3-5 句，含项目名和一句话愿景。"
        )
        try:
            proposal = llm([{"role": "user", "content": proposal_prompt}]).strip()
        except Exception as exc:
            return f"⚠️ 提案生成失败: {exc}"

        if not proposal:
            return f"⚠️ [{vid}] LLM 返回空提案"

        # 4. 写入群聊（含搜索关键词，便于追溯）
        final = f"🔍 探索方向「{query}」\n{proposal}"
        self.send_message(group_id, vid, final)
        return final

    @staticmethod
    def _build_guardrails(platforms: str) -> str:
        """构建探索护栏：平台白名单 + 反模板化约束。

        这是「永久避免方法论模板化」的核心机制——当指定 platforms 时，
        强制村民基于具体平台提出实质性方案，而非套用通用模板。
        """
        if not platforms:
            return ""
        plist = [p.strip() for p in platforms.split(",") if p.strip()]
        plist_str = "、".join(plist)
        return (
            f"\n\n【硬性护栏·必须遵守】\n"
            f"1. 你的提案必须基于以下平台之一：{plist_str}。"
            f"请明确说出看中了哪个具体平台、以什么方式切入"
            f"（竞技对抗 / 开放问题选题 / 真实建模落地）。\n"
            f"2. 禁止套用「XX-Cert 统计功效认证器」这类模板化框架；"
            f"不要机械复用「可预注册 + ≥80% 功效 + 效应量置信区间」的固定句式。\n"
            f"3. 每个提案应是针对具体平台的实质性方案"
            f"（如：挑战某类赛题、求解某个开放问题、落地某类真实建模），"
            f"而非抽象的方法论包装。"
        )


# ── 全局实例 ──────────────────────────────────────────────

_chat = GroupChat()


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "village_chat",
        "description": (
            "智能体村群聊系统。像微信聊天群一样，支持创建群组、成员自由交流、"
            "异步工作（发消息不阻塞，成员可继续各自工作）、维护聊天历史。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "get", "add_member", "send", "history", "reply", "auto_talk", "blackboard", "explore"],
                    "description": (
                        "create — 创建群组；list — 列出群组；get — 查看群组；"
                        "add_member — 添加成员；send — 发消息；history — 查看聊天历史；"
                        "reply — 让某村民基于群聊历史+persona用LLM生成回应；"
                        "auto_talk — 群组成员自动轮转发言（多AI自主聊天）；"
                        "blackboard — 确保黑板群组存在（全员群组）；"
                        "explore — 让某村民联网搜索+头脑风暴，提出项目提案"
                    ),
                },
                "name": {"type": "string", "description": "群组名称（create 时用）", "default": ""},
                "members": {"type": "string", "description": "逗号分隔的成员村民 ID（create 时用）", "default": ""},
                "group_id": {"type": "string", "description": "群组 ID", "default": ""},
                "from": {"type": "string", "description": "发送者村民 ID（send 时用）", "default": ""},
                "content": {"type": "string", "description": "消息内容（send 时用）", "default": ""},
                "villager_id": {"type": "string", "description": "要添加的村民 ID（add_member 时用）", "default": ""},
                "topic": {"type": "string", "description": "领域约束（explore 时限定探索方向，如'信息或应用数学'）", "default": ""},
                "platforms": {"type": "string", "description": "平台白名单（explore 时逗号分隔，强制村民基于这些平台提案，并注入反模板化护栏）", "default": ""},
                "limit": {"type": "integer", "description": "历史条数限制（history 时用）", "default": 30},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


def execute_village_chat_tool(arguments: dict[str, Any]) -> str:
    """群聊工具入口。"""
    action = arguments.get("action", "")

    try:
        if action == "create":
            return _chat.create_group(
                arguments.get("name", ""), arguments.get("members", "")
            )
        elif action == "blackboard":
            return _chat.ensure_blackboard_group()
        elif action == "list":
            return _chat.list_groups()
        elif action == "get":
            return _chat.get_group(arguments.get("group_id", ""))
        elif action == "add_member":
            return _chat.add_member(
                arguments.get("group_id", ""), arguments.get("villager_id", "")
            )
        elif action == "send":
            return _chat.send_message(
                arguments.get("group_id", ""),
                arguments.get("from", ""),
                arguments.get("content", ""),
            )
        elif action == "history":
            return _chat.get_history(
                arguments.get("group_id", ""),
                int(arguments.get("limit", 30)),
            )
        elif action == "reply":
            return _chat.villager_reply(
                arguments.get("group_id", ""),
                arguments.get("villager_id", ""),
            )
        elif action == "auto_talk":
            return _chat.autonomous_talk(
                arguments.get("group_id", ""),
                int(arguments.get("rounds", 3)),
            )
        elif action == "explore":
            return _chat.villager_explore(
                arguments.get("group_id", ""),
                arguments.get("villager_id", ""),
                arguments.get("topic", ""),
                arguments.get("platforms", ""),
            )
        else:
            return f"未知操作: {action}"
    except ChatError as exc:
        return f"群聊错误: {exc}"


# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print(_chat.list_groups())
