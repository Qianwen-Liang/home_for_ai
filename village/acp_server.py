"""village/acp_server.py — ACP Agent 适配层（阶段 A）
====================================================
把村民包装为 ACP（Agent Client Protocol）Agent，通过 stdio 与外部编辑器
（如 Zed）通信。这是智能体村"外部互联"的第一步：村民可被外部工具直接调用。

借鉴 ReasFlow 的 ACP 实现（acp/server.py），核心是 JSON-RPC 2.0 over stdio。
纯标准库实现，不引入新依赖。

支持的方法：
  - initialize      ：协议初始化，交换能力声明
  - session/new     ：创建新会话
  - session/prompt  ：发送 prompt，返回村民响应
  - session/load    ：加载会话（返回空会话）
  - session/cancel  ：取消会话

用法：
  python village/acp_server.py <villager_id>          # stdio 模式（供编辑器调用）
  python village/acp_server.py --self-test <villager_id>  # 自测模式
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
VILLAGERS_DIR = SANDBOX_DIR / "village" / "villagers"

# 支持的 ACP 协议版本
PROTOCOL_VERSION = 1


class ACPError(RuntimeError):
    """ACP 协议错误。"""


class ACPServer:
    """把单个村民暴露为 ACP Agent。"""

    def __init__(self, villager_id: str) -> None:
        if not villager_id or not villager_id.strip():
            raise ACPError("村民 ID 不能为空")
        self.villager_id = villager_id.strip()
        self.home = VILLAGERS_DIR / self.villager_id
        self.identity = self._load_identity()
        self.sessions: dict[str, list[dict[str, Any]]] = {}
        self._session_counter = 0

    def _load_identity(self) -> dict[str, str]:
        """从 identity.md 加载村民身份（能力、技能、边界）。"""
        identity_file = self.home / "identity.md"
        if not identity_file.is_file():
            return {
                "name": self.villager_id,
                "role": "（未定义身份）",
                "capabilities": [],
                "skills": [],
            }
        text = identity_file.read_text(encoding="utf-8")

        def extract_section(title: str) -> list[str]:
            import re
            pattern = rf"## {title}\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, text, re.DOTALL)
            if not m:
                return []
            items = []
            for line in m.group(1).splitlines():
                line = line.strip()
                if line.startswith("- "):
                    items.append(line[2:].strip().strip("`"))
            return items

        # 提取首行名称
        name = self.villager_id
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if first_line.startswith("# "):
            name = first_line[2:].split("（")[0].strip()

        return {
            "name": name,
            "role": self._extract_field(text, "身份"),
            "capabilities": extract_section("能力"),
            "skills": extract_section("技能（最小权限）"),
        }

    @staticmethod
    def _extract_field(text: str, title: str) -> str:
        import re
        m = re.search(rf"## {title}\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return ""

    # ── JSON-RPC 帧处理 ────────────────────────────────

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理一个 JSON-RPC 请求，返回响应。"""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "session/new":
                result = self._session_new(params)
            elif method == "session/prompt":
                result = self._session_prompt(params)
            elif method == "session/load":
                result = self._session_load(params)
            elif method == "session/cancel":
                result = self._session_cancel(params)
            else:
                return self._error(req_id, -32601, f"未知方法: {method}")

            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except ACPError as exc:
            return self._error(req_id, -32000, str(exc))
        except Exception as exc:
            return self._error(req_id, -32603, f"内部错误: {exc}")

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    # ── ACP 方法实现 ────────────────────────────────────

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """协议初始化，返回能力声明。"""
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": False,
                },
            },
            "agentInfo": {
                "id": self.villager_id,
                "name": self.identity.get("name", self.villager_id),
                "role": self.identity.get("role", ""),
                "capabilities": self.identity.get("capabilities", []),
                "skills": self.identity.get("skills", []),
            },
            "authMethods": [],
        }

    def _session_new(self, params: dict[str, Any]) -> dict[str, Any]:
        """创建新会话。"""
        self._session_counter += 1
        session_id = f"{self.villager_id}-session-{self._session_counter}"
        self.sessions[session_id] = []
        return {"sessionId": session_id}

    def _session_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 prompt，返回村民响应。"""
        session_id = params.get("sessionId", "")
        prompt = params.get("prompt", [])
        if not session_id or session_id not in self.sessions:
            # 未指定会话时自动创建
            new_resp = self._session_new({})
            session_id = new_resp["sessionId"]

        # 提取用户文本
        user_text = self._extract_prompt_text(prompt)
        if not user_text:
            raise ACPError("prompt 内容为空")

        # 村民响应：复用 VillagerStore 记录 + 生成回应
        response_text = self._respond(user_text)

        # 记录会话历史
        self.sessions.setdefault(session_id, [])
        self.sessions[session_id].append({"role": "user", "content": user_text})
        self.sessions[session_id].append({"role": "assistant", "content": response_text})

        return {
            "stopReason": "end_turn",
            "message": {"role": "assistant", "content": response_text},
        }

    def _session_load(self, params: dict[str, Any]) -> dict[str, Any]:
        """加载会话（当前为无状态实现）。"""
        session_id = params.get("sessionId", "")
        return {"sessionId": session_id, "messages": []}

    def _session_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """取消会话。"""
        return {"cancelled": True}

    # ── 辅助 ────────────────────────────────────────────

    @staticmethod
    def _extract_prompt_text(prompt: list[dict[str, Any]]) -> str:
        """从 prompt 数组中提取用户文本。"""
        parts = []
        for item in prompt:
            if not isinstance(item, dict):
                continue
            if item.get("role") == "user":
                content = item.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text", ""))
        return "\n".join(parts).strip()

    def _respond(self, user_text: str) -> str:
        """生成村民响应（基于身份与职责，记录到日记）。"""
        name = self.identity.get("name", self.villager_id)
        role = self.identity.get("role", "")
        caps = self.identity.get("capabilities", [])

        # 记录到村民日记（外部接入也是村民的一次工作）
        try:
            from tools.villager import VillagerStore
            store = VillagerStore(self.villager_id)
            store.append_journal(f"[ACP 外部接入] 收到 prompt: {user_text[:60]}")
        except Exception:
            pass

        cap_str = ", ".join(caps) if caps else "通用"
        return (
            f"我是 {name}，智能体村的村民。\n"
            f"职责：{role}\n"
            f"能力：{cap_str}\n\n"
            f"关于你的请求「{user_text[:100]}」：\n"
            f"我已收到，将按我的职责和能力范围处理。"
            f"（当前为 ACP 适配层阶段，返回身份确认响应）"
        )

    # ── stdio 主循环 ────────────────────────────────────

    def run(self) -> None:
        """stdio 模式：逐行读取 JSON-RPC 请求，写回响应。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                sys.stdout.write(json.dumps(
                    self._error(None, -32700, "解析错误：不是有效 JSON")
                ) + "\n")
                sys.stdout.flush()
                continue
            response = self.handle_request(request)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ── 自测 ──────────────────────────────────────────────────

def self_test(villager_id: str) -> None:
    """自测模式：模拟一个 ACP 客户端，验证协议正确性。"""
    server = ACPServer(villager_id)
    print(f"=== ACP 自测: 村民 [{villager_id}] ===\n")

    # 1. initialize
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    print("1. initialize:")
    print("   协议版本:", resp["result"]["protocolVersion"])
    print("   村民:", resp["result"]["agentInfo"]["name"], "-", resp["result"]["agentInfo"]["role"])
    print("   能力:", resp["result"]["agentInfo"]["capabilities"])
    print()

    # 2. session/new
    resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}})
    session_id = resp["result"]["sessionId"]
    print("2. session/new:")
    print("   会话:", session_id)
    print()

    # 3. session/prompt
    resp = server.handle_request({
        "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"role": "user", "content": [{"type": "text", "text": "你好，介绍一下你自己"}]}],
        },
    })
    print("3. session/prompt:")
    print("   stopReason:", resp["result"]["stopReason"])
    print("   响应:", resp["result"]["message"]["content"][:100])
    print()

    # 4. 未知方法
    resp = server.handle_request({"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}})
    print("4. 未知方法:")
    print("   错误码:", resp["error"]["code"], "-", resp["error"]["message"])
    print()

    print("=== ACP 自测通过 ===")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    elif len(sys.argv) >= 2:
        ACPServer(sys.argv[1]).run()
    else:
        print("用法: python village/acp_server.py <villager_id>")
        print("      python village/acp_server.py --self-test <villager_id>")
        sys.exit(1)
