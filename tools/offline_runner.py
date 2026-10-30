"""
offline_runner — 离线任务管理器（v1.0）
=======================================
受 ARIS (Auto-Research-In-Sleep) 启发，为 Agent 1 提供
"无人值守"的任务执行模式。

设计理念：
  - 任务包：将任务描述 + 所需工具调用封装为一个可离线执行的单元
  - 检查点：每完成一个步骤自动保存进度，支持中断恢复
  - 异步执行：提交任务后即可关闭终端，稍后回来查看结果
  - 报告驱动：每个任务执行完成后自动生成结构化报告

使用场景：
  1. 晚上提交任务包，早上查看结果（ARIS 的 "While You Sleep" 模式）
  2. 长时间的数据处理和文件分析
  3. 批量代码审查和质量检查

使用方式：
  offline action=submit task="扫描工作区" params='{"target":"tools"}' 
  offline action=status task_id="T001"
  offline action=list
  offline action=report task_id="T001"
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .checkpoint_manager import CheckpointManager

SANDBOX_DIR = Path(__file__).resolve().parent.parent
OFFLINE_DIR = SANDBOX_DIR / "memory" / "offline"


# ── 错误类型 ──────────────────────────────────────────────


class OfflineError(RuntimeError):
    """离线任务错误。"""


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class OfflineTask:
    """离线任务包。"""
    task_id: str
    title: str
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | running | paused | done | failed
    progress: float = 0.0    # 0.0 ~ 1.0
    current_phase: str = ""
    phases: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    checkpoint_ids: list[str] = field(default_factory=list)
    idempotency_key: str = ""  # E9: 幂等键，防止重复提交
    webhook_url: str = ""  # E10: 任务完成/失败时的回调 URL


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "offline",
        "description": (
            "离线任务管理器。提交任务后可在无人值守的后台执行，"
            "支持检查点保存、中断恢复和结果报告。"
            "适合长时间运行的任务，如工作区扫描、代码分析等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "submit", "execute", "status",
                        "list", "report", "pause",
                        "resume", "cancel", "recover",
                    ],
                    "description": (
                        "操作类型："
                        "submit — 提交一个新的离线任务；"
                        "execute — 执行已提交的离线任务；"
                        "status — 查看任务状态；"
                        "list — 列出所有离线任务；"
                        "report — 生成任务执行报告；"
                        "pause — 暂停正在执行的任务；"
                        "resume — 恢复暂停的任务；"
                        "cancel — 取消任务；"
                        "recover — 恢复僵尸/失败任务（从最近检查点）。"
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": "任务 ID",
                    "default": "",
                },
                "title": {
                    "type": "string",
                    "description": "任务标题（submit 时需要）",
                    "default": "",
                },
                "description": {
                    "type": "string",
                    "description": "任务描述",
                    "default": "",
                },
                "params": {
                    "type": "string",
                    "description": "任务参数 JSON 字符串",
                    "default": "{}",
                },
                "phases": {
                    "type": "string",
                    "description": "执行阶段列表 JSON，如 '[\"扫描\",\"分析\",\"报告\"]'",
                    "default": "",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": (
                        "幂等键（可选）。相同幂等键的重复提交会被检测并拒绝，"
                        "返回已存在任务的 ID。防止网络重试导致的重复提交。"
                        "例如：'scan-tools-20250101'"
                    ),
                    "default": "",
                },
                "webhook_url": {
                    "type": "string",
                    "description": (
                        "Webhook 回调 URL（可选）。任务完成或失败时发送 HTTP POST 通知。"
                        "Payload: {\"task_id\":..., \"status\":..., \"result\":...}"
                    ),
                    "default": "",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 离线任务管理器 ────────────────────────────────────────


class OfflineTaskManager:
    """
    离线任务管理器。
    
    管理离线任务的提交、执行、状态追踪和报告生成。
    """

    # 僵尸任务超时阈值（秒）：运行超过此时间视为僵死
    ZOMBIE_TIMEOUT_SECONDS = 3600  # 1 小时

    def __init__(self, auto_recover: bool = False) -> None:
        self._checkpoint = CheckpointManager()
        self._tasks: dict[str, OfflineTask] = {}
        self._tasks_dir = OFFLINE_DIR
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._auto_recover = auto_recover
        self._recovery_log: list[str] = []
        self._idempotency_map: dict[str, str] = {}  # E9: idempotency_key → task_id
        self._load()
        self._recover_zombies()

    # ── 持久化 ──────────────────────────────────────────

    def _save_task(self, task: OfflineTask) -> None:
        """保存单个任务到文件。"""
        task_file = self._tasks_dir / f"{task.task_id}.json"
        task_file.write_text(
            json.dumps({
                "task_id": task.task_id,
                "title": task.title,
                "description": task.description,
                "params": task.params,
                "status": task.status,
                "progress": task.progress,
                "current_phase": task.current_phase,
                "phases": task.phases,
                "result": task.result,
                "error": task.error,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "completed_at": task.completed_at,
                "checkpoint_ids": task.checkpoint_ids,
                "idempotency_key": task.idempotency_key,  # E9
                "webhook_url": task.webhook_url,  # E10
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        """从文件加载所有任务。"""
        if not self._tasks_dir.is_dir():
            return
        for task_file in sorted(self._tasks_dir.glob("*.json")):
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                task = OfflineTask(
                    task_id=data.get("task_id", task_file.stem),
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    params=data.get("params", {}),
                    status=data.get("status", "pending"),
                    progress=data.get("progress", 0.0),
                    current_phase=data.get("current_phase", ""),
                    phases=data.get("phases", []),
                    result=data.get("result", {}),
                    error=data.get("error", ""),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    completed_at=data.get("completed_at", ""),
                    checkpoint_ids=data.get("checkpoint_ids", []),
                    idempotency_key=data.get("idempotency_key", ""),  # E9
                    webhook_url=data.get("webhook_url", ""),  # E10
                )
                self._tasks[task.task_id] = task
                # E9: 重建幂等键映射表
                if task.idempotency_key:
                    self._idempotency_map[task.idempotency_key] = task.task_id
            except (json.JSONDecodeError, OSError):
                continue

    # ── 自动恢复 ──────────────────────────────────────────

    def _recover_zombies(self) -> None:
        """
        启动时检测并处理僵尸任务（状态为 running 但实际已僵死）。
        
        僵尸判断标准：
          1. 状态为 "running"
          2. updated_at 距离当前时间超过 ZOMBIE_TIMEOUT_SECONDS
        
        处理策略：
          - 如果 auto_recover=True：自动将僵尸任务标记为 paused，
            保留当前进度，等待手动恢复
          - 如果 auto_recover=False：仅记录日志，不修改状态
        
        参考：Temporal.io 的 sticky execution 恢复机制
        """
        now = datetime.now()

        for task_id, task in list(self._tasks.items()):
            if task.status != "running":
                continue

            # 解析更新时间
            try:
                updated = datetime.strptime(task.updated_at, "%Y-%m-%d %H:%M:%S")
                elapsed = (now - updated).total_seconds()
            except (ValueError, TypeError):
                # 无法解析时间，保守处理：不自动恢复
                self._recovery_log.append(
                    f"[{now:%Y-%m-%d %H:%M:%S}] ⚠️ 无法解析任务 '{task_id}' 的更新时间，跳过"
                )
                continue

            if elapsed < self.ZOMBIE_TIMEOUT_SECONDS:
                # 仍在合理运行时间内，可能是正常运行的长时间任务
                self._recovery_log.append(
                    f"[{now:%Y-%m-%d %H:%M:%S}] ℹ️ 任务 '{task_id}' "
                    f"已运行 {elapsed:.0f}s（未超 {self.ZOMBIE_TIMEOUT_SECONDS}s 阈值），保留 running 状态"
                )
                continue

            # 确认僵尸任务
            log_msg = (
                f"[{now:%Y-%m-%d %H:%M:%S}] ⚠️ 检测到僵尸任务 '{task_id}' "
                f"（已运行 {elapsed:.0f}s，超过 {self.ZOMBIE_TIMEOUT_SECONDS}s 阈值）"
            )
            self._recovery_log.append(log_msg)

            if self._auto_recover:
                # 自动恢复：标记为 paused，保留进度
                task.status = "paused"
                task.error = (
                    f"[AutoRecovery] 任务僵死自动暂停（运行 {elapsed:.0f}s 后无响应）"
                )
                task.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")
                self._save_task(task)
                self._recovery_log.append(
                    f"[{now:%Y-%m-%d %H:%M:%S}] 🔧 已自动将任务 '{task_id}' "
                    f"状态从 running 改为 paused（进度 {task.progress:.0%}）"
                )
            else:
                # 仅记录
                self._recovery_log.append(
                    f"[{now:%Y-%m-%d %H:%M:%S}] 💡 提示: 使用 recover('{task_id}') 手动恢复，"
                    f"或设置 auto_recover=True 启用自动恢复"
                )

    def recover(self, task_id: str) -> str:
        """
        手动恢复一个僵尸/失败任务。
        
        恢复策略：
          1. 如果有检查点：从最后一个检查点之后的阶段继续
          2. 如果无检查点：重置为 pending 从头执行
          3. 如果任务已完成：不做任何操作
        
        Args:
            task_id: 要恢复的任务 ID
        
        Returns:
            恢复结果描述
        
        Raises:
            OfflineError: 任务不存在
        """
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        if task.status == "done":
            return f"✅ 任务 '{task_id}' 已完成，无需恢复"

        if task.status == "running":
            return (
                f"⚠️ 任务 '{task_id}' 正在运行中\n"
                f"   如确认已僵死，请等待 {self.ZOMBIE_TIMEOUT_SECONDS}s 超时后自动检测，"
                f"或手动 cancel 后再 recover"
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 优先以任务自身记录的 checkpoint_ids 为准（避免磁盘残留污染）
        has_checkpoints = bool(task.checkpoint_ids)
        checkpoints: list[dict[str, Any]] = []

        if has_checkpoints:
            # 从磁盘加载实际检查点数据
            checkpoints = self._checkpoint.list(task_id=task_id)

        if has_checkpoints and checkpoints:
            # 有检查点：找到最后一个成功的阶段
            last_cp = checkpoints[-1]
            last_phase = last_cp.get("phase", "")
            last_state = last_cp.get("state", {})

            # 恢复进度
            task.progress = last_state.get("progress", task.progress)
            task.current_phase = last_phase
            task.result = last_state.get("results", task.result)
            task.status = "paused"  # 恢复后暂停，等待手动 execute
            task.error = f"[Recovery] 从检查点恢复（最后阶段: {last_phase}）"
            task.updated_at = now
            self._save_task(task)

            return (
                f"🔧 任务 '{task_id}' 已从检查点恢复\n"
                f"{'─'*40}\n"
                f"最后阶段: {last_phase}\n"
                f"进度:      {task.progress:.0%}\n"
                f"状态:      paused（使用 execute 继续执行）\n"
                f"\n使用 offline action=execute task_id={task_id} 继续执行"
            )
        else:
            # 无检查点：从头开始
            task.status = "pending"
            task.progress = 0.0
            task.current_phase = ""
            task.result = {}
            task.error = ""
            task.updated_at = now
            self._save_task(task)

            return (
                f"🔧 任务 '{task_id}' 已重置（无检查点可恢复）\n"
                f"{'─'*40}\n"
                f"状态: pending\n"
                f"\n使用 offline action=execute task_id={task_id} 重新执行"
            )

    def get_recovery_log(self) -> str:
        """获取自动恢复日志。"""
        if not self._recovery_log:
            return "📋 恢复日志为空（未检测到僵尸任务）"

        lines = ["📋 自动恢复日志:", f"{'─'*40}"]
        lines.extend(self._recovery_log)
        return "\n".join(lines)

    # ── E10: Webhook 通知 ─────────────────────────────────

    def _send_webhook(self, task: OfflineTask) -> None:
        """
        发送 Webhook 通知（fire-and-forget，不阻塞任务执行）。

        向 task.webhook_url 发送 HTTP POST，Payload:
          {"task_id": ..., "title": ..., "status": ..., "progress": ...,
           "result": ..., "error": ..., "completed_at": ...}

        失败时静默忽略（不影响任务状态）。
        """
        url = task.webhook_url.strip()
        if not url:
            return

        payload = json.dumps({
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
            "completed_at": task.completed_at,
            "event": f"task_{task.status}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Agent1-OfflineRunner/1.0",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            # fire-and-forget: 静默忽略所有网络错误
            pass

    # ── 公共 API ──────────────────────────────────────────

    def submit(
        self,
        title: str,
        description: str = "",
        params: dict[str, Any] | None = None,
        phases: list[str] | None = None,
        idempotency_key: str = "",
        webhook_url: str = "",  # E10
    ) -> str:
        """提交一个离线任务。

        Args:
            title: 任务标题
            description: 任务描述
            params: 任务参数
            phases: 执行阶段列表
            idempotency_key: 幂等键（可选），相同幂等键的重复提交返回已存在任务 ID

        Returns:
            提交结果描述

        Raises:
            OfflineError: 标题为空时抛出
        """
        if not title.strip():
            raise OfflineError("任务标题不能为空")

        # E9: 幂等键去重检查
        if idempotency_key.strip():
            existing_task_id = self._idempotency_map.get(idempotency_key.strip())
            if existing_task_id:
                existing_task = self._tasks.get(existing_task_id)
                if existing_task:
                    return (
                        f"🔁 幂等检测: 任务已存在（幂等键: '{idempotency_key.strip()}'）\n"
                        f"{'─'*40}\n"
                        f"已有任务ID: {existing_task_id}\n"
                        f"标题:       {existing_task.title}\n"
                        f"状态:       {existing_task.status}\n"
                        f"进度:       {existing_task.progress:.0%}\n"
                        f"\n使用 offline action=status task_id={existing_task_id} 查看详情"
                    )

        task_id = f"OT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        task = OfflineTask(
            task_id=task_id,
            title=title.strip(),
            description=description.strip(),
            params=params or {},
            status="pending",
            progress=0.0,
            phases=phases or [],
            created_at=timestamp,
            updated_at=timestamp,
            idempotency_key=idempotency_key.strip(),  # E9
            webhook_url=webhook_url.strip(),  # E10
        )

        # E9: 注册幂等键映射
        if task.idempotency_key:
            self._idempotency_map[task.idempotency_key] = task_id

        self._tasks[task_id] = task
        self._save_task(task)

        result = (
            f"📦 离线任务已提交\n"
            f"{'─'*40}\n"
            f"任务ID:   {task_id}\n"
            f"标题:     {title}\n"
            f"描述:     {description or '无'}\n"
            f"阶段数:   {len(task.phases)}\n"
            f"状态:     pending"
        )
        if task.idempotency_key:
            result += f"\n幂等键:   {task.idempotency_key}"
        result += f"\n\n使用 offline action=execute task_id={task_id} 开始执行"
        return result

    def execute(
        self,
        task_id: str,
        phase_executor: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> str:
        """
        执行离线任务。
        
        phase_executor 是一个回调函数，接受 (task_id, phase, params) 参数，
        返回执行结果字典。如果不提供，则只做模拟执行。
        """
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        if task.status == "running":
            return f"⚠️ 任务 '{task_id}' 正在执行中"

        task.status = "running"
        task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_task(task)

        phases = task.phases if task.phases else ["执行"]
        total_phases = len(phases)
        completed_phases = 0

        results: dict[str, Any] = {}

        try:
            for i, phase in enumerate(phases):
                # 检查是否被暂停
                if self._tasks.get(task_id) and self._tasks[task_id].status == "paused":
                    return f"⏸️ 任务 '{task_id}' 已暂停（阶段: {phase}）"

                task.current_phase = phase
                task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_task(task)

                # 执行阶段
                phase_result: dict[str, Any] = {}
                if phase_executor:
                    try:
                        phase_result = phase_executor(task_id, phase, task.params)
                    except Exception as exc:
                        phase_result = {
                            "error": str(exc),
                            "phase": phase,
                            "status": "failed",
                        }

                results[phase] = phase_result

                # 检测阶段失败：phase_executor 抛异常或返回失败状态
                if isinstance(phase_result, dict) and phase_result.get("status") == "failed":
                    raise OfflineError(
                        f"阶段 '{phase}' 失败: {phase_result.get('error', '未知错误')}"
                    )

                completed_phases += 1

                # 更新进度
                task.progress = completed_phases / total_phases

                # 保存检查点
                cp_id = self._checkpoint.save(
                    task_id=task_id,
                    phase=phase,
                    state={
                        "progress": task.progress,
                        "current_phase": phase,
                        "results": results,
                        "params": task.params,
                    },
                )
                task.checkpoint_ids.append(cp_id)

                task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_task(task)

            # 任务完成
            task.status = "done"
            task.progress = 1.0
            task.result = results
            task.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.updated_at = task.completed_at
            self._save_task(task)
            self._send_webhook(task)  # E10

            return (
                f"✅ 离线任务 '{task_id}' 已完成！\n"
                f"{'─'*40}\n"
                f"标题:     {task.title}\n"
                f"阶段:     {completed_phases}/{total_phases}\n"
                f"检查点:   {len(task.checkpoint_ids)}\n"
                f"完成时间: {task.completed_at}\n"
                f"\n使用 offline action=report task_id={task_id} 查看详细报告"
            )

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 失败时也保存检查点
            self._checkpoint.save(
                task_id=task_id,
                phase=f"{task.current_phase}_failed",
                state={
                    "progress": task.progress,
                    "error": str(exc),
                    "results": results,
                },
                metadata={"error": str(exc)},
            )

            self._save_task(task)
            self._send_webhook(task)  # E10
            return (
                f"❌ 离线任务 '{task_id}' 执行失败\n"
                f"{'─'*40}\n"
                f"阶段:     {task.current_phase}\n"
                f"错误:     {exc}\n"
                f"\n修复后可尝试重新执行"
            )

    def get_status(self, task_id: str) -> str:
        """查看任务状态。"""
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        status_icon = {
            "pending": "📦",
            "running": "🔄",
            "paused": "⏸️",
            "done": "✅",
            "failed": "❌",
        }.get(task.status, "❓")

        lines = [
            f"{status_icon} 离线任务状态: '{task_id}'",
            f"{'─'*40}",
            f"标题:     {task.title}",
            f"状态:     {task.status}",
            f"进度:     {task.progress:.0%}",
        ]

        if task.current_phase:
            lines.append(f"当前阶段: {task.current_phase}")
        if task.phases:
            lines.append(f"总阶段数: {len(task.phases)}")
        if task.checkpoint_ids:
            lines.append(f"检查点数: {len(task.checkpoint_ids)}")
        if task.created_at:
            lines.append(f"创建时间: {task.created_at}")
        if task.completed_at:
            lines.append(f"完成时间: {task.completed_at}")
        if task.error:
            lines.append(f"错误:     {task.error}")

        # 进度条
        bar_len = 20
        filled = int(task.progress * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        lines.append(f"\n进度: [{bar}] {task.progress:.0%}")

        return "\n".join(lines)

    def list_tasks(self) -> str:
        """列出所有离线任务。"""
        if not self._tasks:
            return "暂无离线任务。"

        lines = ["📋 离线任务列表:\n"]
        for task_id in sorted(self._tasks.keys(), reverse=True):
            task = self._tasks[task_id]
            status_icon = {
                "pending": "📦",
                "running": "🔄",
                "paused": "⏸️",
                "done": "✅",
                "failed": "❌",
            }.get(task.status, "❓")
            lines.append(
                f"  {status_icon} [{task_id}] {task.title[:40]}\n"
                f"     状态: {task.status} | 进度: {task.progress:.0%} | "
                f"阶段: {task.current_phase or '无'}"
            )

        return "\n".join(lines)

    def generate_report(self, task_id: str) -> str:
        """生成任务执行报告。"""
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        status_icon = {
            "pending": "📦",
            "running": "🔄",
            "paused": "⏸️",
            "done": "✅",
            "failed": "❌",
        }.get(task.status, "❓")

        lines = [
            f"{status_icon} 离线任务执行报告",
            f"{'='*50}",
            f"",
            f"📋 基本信息",
            f"  任务ID:   {task.task_id}",
            f"  标题:     {task.title}",
            f"  描述:     {task.description or '无'}",
            f"  状态:     {task.status}",
            f"  进度:     {task.progress:.0%}",
            f"",
            f"⏱️ 时间线",
        ]

        if task.created_at:
            lines.append(f"  创建: {task.created_at}")
        if task.completed_at:
            lines.append(f"  完成: {task.completed_at}")

        lines.append(f"")
        lines.append(f"📊 执行详情")
        lines.append(f"  总阶段数:  {len(task.phases)}")
        lines.append(f"  检查点数:  {len(task.checkpoint_ids)}")

        if task.result:
            lines.append(f"")
            lines.append(f"📈 各阶段结果:")
            for phase, result in task.result.items():
                status = result.get("status", "done") if isinstance(result, dict) else "done"
                icon = "✅" if status == "done" else "❌"
                summary = str(result)[:80] if result else "无输出"
                lines.append(f"  {icon} {phase}: {summary}")

        if task.error:
            lines.append(f"")
            lines.append(f"❌ 错误信息")
            lines.append(f"  {task.error}")

        return "\n".join(lines)

    def pause(self, task_id: str) -> str:
        """暂停任务。"""
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        if task.status != "running":
            return f"⚠️ 任务 '{task_id}' 状态为 '{task.status}'，无法暂停"

        task.status = "paused"
        task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_task(task)

        return f"⏸️ 任务 '{task_id}' 已暂停（阶段: {task.current_phase}）"

    def resume(self, task_id: str) -> str:
        """恢复任务。"""
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        if task.status != "paused":
            return f"⚠️ 任务 '{task_id}' 状态为 '{task.status}'，无法恢复"

        task.status = "running"
        task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_task(task)

        return (
            f"▶️ 任务 '{task_id}' 已恢复\n"
            f"   当前阶段: {task.current_phase}\n"
            f"   使用 offline action=execute task_id={task_id} 继续执行"
        )

    def cancel(self, task_id: str) -> str:
        """取消任务。"""
        task = self._tasks.get(task_id)
        if not task:
            raise OfflineError(f"未找到任务: '{task_id}'")

        if task.status == "done":
            return f"⚠️ 任务 '{task_id}' 已完成，无法取消"

        task.status = "paused"
        self._save_task(task)
        return f"🛑 任务 '{task_id}' 已取消"


# ── 全局实例 ──────────────────────────────────────────────

_manager = OfflineTaskManager()


def execute_offline_tool(arguments: dict[str, Any]) -> str:
    """执行 offline 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "submit":
            phases_str = arguments.get("phases", "")
            phases: list[str] = []
            if phases_str:
                try:
                    phases = json.loads(phases_str)
                    if not isinstance(phases, list):
                        return "phases 必须是 JSON 数组"
                except json.JSONDecodeError as exc:
                    return f"phases JSON 解析错误: {exc}"

            params_str = arguments.get("params", "{}")
            try:
                params = json.loads(params_str)
            except json.JSONDecodeError as exc:
                return f"params JSON 解析错误: {exc}"

            return _manager.submit(
                title=arguments.get("title", ""),
                description=arguments.get("description", ""),
                params=params,
                phases=phases,
                idempotency_key=arguments.get("idempotency_key", ""),
                webhook_url=arguments.get("webhook_url", ""),
            )

        elif action == "execute":
            return _manager.execute(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "status":
            return _manager.get_status(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "list":
            return _manager.list_tasks()

        elif action == "report":
            return _manager.generate_report(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "pause":
            return _manager.pause(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "resume":
            return _manager.resume(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "cancel":
            return _manager.cancel(
                task_id=arguments.get("task_id", ""),
            )

        elif action == "recover":
            return _manager.recover(
                task_id=arguments.get("task_id", ""),
            )

        else:
            return f"未知操作: {action}"

    except OfflineError as exc:
        return f"离线任务错误: {exc}"
