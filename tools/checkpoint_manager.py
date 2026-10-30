"""
checkpoint_manager — 工作流级检查点管理（v2.0）
==============================================
受 ARIS (Auto-Research-In-Sleep) 启发，为长周期离线任务提供
主动式检查点机制 —— 每完成一个阶段自动保存状态，支持中断恢复和回滚。

v2.0 新增：
  - 可插拔存储后端（FileBackend / SQLiteBackend）
  - 策略模式切换，零代码改动即可从文件迁移到 SQLite
  - 向后兼容：默认使用 FileBackend

与 Debugger snapshot 的区别：
  - Debugger snapshot：异常级快照，崩溃时被动保存现场
  - Checkpoint：工作流级主动保存，每步完成后自动触发

设计原则：
  - 轻量：纯 Python 标准库，无外部依赖
  - 可插拔：文件/SQLite 后端自由切换
  - 可追溯：检查点记录创建时间、阶段、关联任务
  - 可回滚：支持恢复到历史任意检查点

使用方式：
  # 默认文件后端
  cm = CheckpointManager()
  
  # SQLite 后端（并发安全）
  from tools.checkpoint_backend import SQLiteBackend
  cm = CheckpointManager(backend=SQLiteBackend("memory/checkpoints.db"))
  
  cm.save(task_id="T001", phase="文献调研", state={...})
  state = cm.load("cp_T001_20260723_020000")
  state = cm.rollback("T001", "文献调研")
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .checkpoint_backend import FileBackend, StorageBackend

SANDBOX_DIR = Path(__file__).resolve().parent.parent


class CheckpointError(RuntimeError):
    """检查点管理错误。"""


class CheckpointManager:
    """
    工作流级检查点管理器。
    
    管理离线任务的阶段性状态保存和恢复。
    
    v2.0: 支持可插拔存储后端（FileBackend 默认 / SQLiteBackend 可选）。
    """

    def __init__(self, backend: StorageBackend | None = None) -> None:
        """
        初始化检查点管理器。
        
        Args:
            backend: 存储后端实例。默认 FileBackend（向后兼容）。
                     使用 SQLiteBackend("path.db") 可获得并发安全+查询性能。
        """
        self._backend = backend if backend is not None else FileBackend()
        # 保留目录属性用于向后兼容（部分旧代码可能直接访问）
        if isinstance(self._backend, FileBackend):
            self._checkpoint_dir = self._backend._dir
        else:
            self._checkpoint_dir = SANDBOX_DIR / "memory" / "checkpoints"

    # ── 公共 API ──────────────────────────────────────────

    def save(
        self,
        task_id: str,
        phase: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        保存一个检查点。
        
        参数：
          task_id: 关联的任务 ID
          phase:   当前阶段名称，如 "文献调研"
          state:   要保存的状态数据（任务进度、中间结果等）
          metadata: 额外元数据（可选）
        
        返回：检查点 ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 用 uuid 保证唯一性（Windows 上 datetime/time_ns 精度不足，快速连续 save 会时间戳冲突）
        checkpoint_id = f"cp_{task_id}_{timestamp}_{uuid.uuid4().hex[:8]}"

        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "phase": phase,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata or {},
            "state": state,
        }

        try:
            self._backend.save(checkpoint)
        except (IOError, OSError) as exc:
            raise CheckpointError(f"检查点保存失败: {exc}") from exc

        # 清理旧检查点（每个任务保留最近 10 个）
        self._backend.cleanup_task(task_id, keep=10)

        return checkpoint_id

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        """
        加载一个检查点。
        
        参数：
          checkpoint_id: 检查点 ID
        
        返回：检查点完整数据
        """
        try:
            return self._backend.load(checkpoint_id)
        except KeyError as exc:
            raise CheckpointError(f"检查点不存在: {checkpoint_id}") from exc
        except (IOError, OSError) as exc:
            raise CheckpointError(f"检查点加载失败: {exc}") from exc

    def list(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """
        列出检查点。
        
        参数：
          task_id: 可选，按任务 ID 筛选
        
        返回：检查点摘要列表（按时间倒序）
        """
        try:
            return self._backend.list(task_id=task_id)
        except (IOError, OSError) as exc:
            raise CheckpointError(f"列出检查点失败: {exc}") from exc

    def rollback(
        self,
        task_id: str,
        target_phase: str,
    ) -> dict[str, Any]:
        """
        回滚到指定阶段的最新检查点。
        
        参数：
          task_id:     任务 ID
          target_phase: 目标阶段名称
        
        返回：该阶段的状态数据
        
        如果找不到目标阶段的检查点，抛出 CheckpointError。
        """
        # 查找该任务所有检查点
        all_cps = self.list(task_id)
        if not all_cps:
            raise CheckpointError(f"任务 '{task_id}' 没有检查点可回滚")

        # 找到目标阶段的最新检查点
        target_cps = [
            cp for cp in all_cps
            if cp["phase"] == target_phase
        ]
        if not target_cps:
            available_phases = sorted(set(cp["phase"] for cp in all_cps))
            raise CheckpointError(
                f"未找到阶段 '{target_phase}' 的检查点。"
                f"可用阶段: {available_phases}"
            )

        # 取最新的（已按时间倒序排列）
        latest = target_cps[0]
        full_data = self.load(latest["checkpoint_id"])
        return full_data.get("state", {})

    def delete_task(self, task_id: str) -> int:
        """
        删除某个任务的所有检查点。
        
        返回：删除的记录数
        """
        try:
            return self._backend.delete_task(task_id)
        except (IOError, OSError) as exc:
            raise CheckpointError(f"删除检查点失败: {exc}") from exc

    def clean_all(self, max_age_days: int = 30) -> int:
        """
        清理超过指定天数的所有检查点。
        
        返回：清理的记录数
        """
        try:
            return self._backend.clean_old(max_age_days)
        except (IOError, OSError) as exc:
            raise CheckpointError(f"清理检查点失败: {exc}") from exc

    # ── 内部方法 ──────────────────────────────────────────

    def _cleanup(self, task_id: str, keep: int = 10) -> None:
        """清理某个任务的旧检查点，只保留最近的 keep 个。"""
        try:
            self._backend.cleanup_task(task_id, keep)
        except (IOError, OSError) as exc:
            raise CheckpointError(f"清理旧检查点失败: {exc}") from exc


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "checkpoint",
        "description": (
            "工作流级检查点管理。支持保存阶段性状态、"
            "加载检查点、回滚到指定阶段、列出和清理检查点。"
            "适用于长周期离线任务的进度管理。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "save", "load", "list",
                        "rollback", "delete_task", "clean_all",
                    ],
                    "description": (
                        "操作类型："
                        "save — 保存当前阶段状态；"
                        "load — 加载指定检查点；"
                        "list — 列出检查点（可按任务筛选）；"
                        "rollback — 回滚到指定阶段；"
                        "delete_task — 删除某任务的所有检查点；"
                        "clean_all — 清理过期检查点。"
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": "关联的任务 ID",
                    "default": "",
                },
                "phase": {
                    "type": "string",
                    "description": "当前阶段名称（save/rollback 时需要）",
                    "default": "",
                },
                "state": {
                    "type": "string",
                    "description": "要保存的状态 JSON（save 时需要）",
                    "default": "{}",
                },
                "checkpoint_id": {
                    "type": "string",
                    "description": "检查点 ID（load 时需要）",
                    "default": "",
                },
                "target_phase": {
                    "type": "string",
                    "description": "目标阶段名称（rollback 时需要）",
                    "default": "",
                },
                "max_age_days": {
                    "type": "integer",
                    "description": "清理超过此天数的检查点（clean_all 时需要）",
                    "default": 30,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 全局实例 ──────────────────────────────────────────────

_manager = CheckpointManager()


def execute_checkpoint_tool(arguments: dict[str, Any]) -> str:
    """执行 checkpoint 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "save":
            task_id = arguments.get("task_id", "")
            phase = arguments.get("phase", "")
            state_str = arguments.get("state", "{}")

            if not task_id or not phase:
                return "请提供 task_id 和 phase"

            try:
                state = json.loads(state_str)
            except json.JSONDecodeError as exc:
                return f"state JSON 解析错误: {exc}"

            cp_id = _manager.save(task_id, phase, state)
            return f"✅ 检查点已保存 [ID: {cp_id}]（任务: {task_id}, 阶段: {phase}）"

        elif action == "load":
            cp_id = arguments.get("checkpoint_id", "")
            if not cp_id:
                return "请提供 checkpoint_id"

            data = _manager.load(cp_id)
            state = data.get("state", {})
            return (
                f"📂 检查点: {cp_id}\n"
                f"   任务: {data.get('task_id', '?')}\n"
                f"   阶段: {data.get('phase', '?')}\n"
                f"   时间: {data.get('created_at', '?')}\n"
                f"   状态数据项数: {len(state)}"
            )

        elif action == "list":
            task_id = arguments.get("task_id", "")
            cps = _manager.list(task_id=task_id or None)

            if not cps:
                return "暂无检查点。"

            lines = ["📋 检查点列表:\n"]
            for cp in cps:
                lines.append(
                    f"  🏷️  {cp['checkpoint_id']}\n"
                    f"     任务: {cp['task_id']} | 阶段: {cp['phase']}\n"
                    f"     时间: {cp['created_at']} | 数据: {cp['state_size']}B\n"
                )

            return "\n".join(lines)

        elif action == "rollback":
            task_id = arguments.get("task_id", "")
            target = arguments.get("target_phase", "")
            if not task_id or not target:
                return "请提供 task_id 和 target_phase"

            state = _manager.rollback(task_id, target)
            return (
                f"⏪ 已回滚到任务 '{task_id}' 的阶段 '{target}'\n"
                f"   恢复的状态数据项数: {len(state)}"
            )

        elif action == "delete_task":
            task_id = arguments.get("task_id", "")
            if not task_id:
                return "请提供 task_id"

            deleted = _manager.delete_task(task_id)
            return f"🗑️ 已删除任务 '{task_id}' 的 {deleted} 个检查点"

        elif action == "clean_all":
            days = arguments.get("max_age_days", 30)
            cleaned = _manager.clean_all(max_age_days=days)
            return f"🧹 已清理 {cleaned} 个超过 {days} 天的检查点"

        else:
            return f"未知操作: {action}"

    except CheckpointError as exc:
        return f"检查点错误: {exc}"
