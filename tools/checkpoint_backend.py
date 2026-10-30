"""
checkpoint_backend — 检查点存储后端抽象层（v1.0）
================================================
为 CheckpointManager 提供可插拔的存储后端，支持文件（JSON）和 SQLite。

参考：
  - LangGraph SqliteSaver / PostgresSaver 的多后端模式
  - 策略模式（Strategy Pattern）实现后端切换

设计原则：
  - 零外部依赖（SQLite 使用 Python 标准库 sqlite3）
  - 接口一致：FileBackend 和 SQLiteBackend 实现相同 API
  - 向后兼容：默认 FileBackend 保持原有行为
  - 并发安全：SQLiteBackend 使用 WAL 模式 + 重试

使用方式：
  from tools.checkpoint_backend import FileBackend, SQLiteBackend
  
  # 文件后端（默认，向后兼容）
  cm = CheckpointManager(backend=FileBackend())
  
  # SQLite 后端（并发安全，查询更快）
  cm = CheckpointManager(backend=SQLiteBackend("memory/checkpoints.db"))
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any
_JSON_CACHE: dict = {}

def _read_json_cached(path, encoding="utf-8"):
    """带 mtime 缓存的 JSON 读取，等价于 json.loads(path.read_text(encoding=...))。

    文件 mtime 未变时返回缓存，变化则重新加载；解析失败重新抛出 json.JSONDecodeError。
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise
    key = str(path)
    entry = _JSON_CACHE.get(key)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    data = json.loads(path.read_text(encoding=encoding))
    _JSON_CACHE[key] = (mtime, data)
    return data


SANDBOX_DIR = Path(__file__).resolve().parent.parent


# ── 抽象基类 ──────────────────────────────────────────────


class StorageBackend(ABC):
    """检查点存储后端抽象基类。"""

    @abstractmethod
    def save(self, checkpoint: dict[str, Any]) -> str:
        """
        保存检查点。
        
        Args:
            checkpoint: 检查点数据，包含 checkpoint_id, task_id, phase, state 等
        
        Returns:
            检查点 ID
        """
        ...

    @abstractmethod
    def load(self, checkpoint_id: str) -> dict[str, Any]:
        """
        加载检查点。
        
        Args:
            checkpoint_id: 检查点 ID
        
        Returns:
            检查点完整数据
        
        Raises:
            KeyError: 检查点不存在
        """
        ...

    @abstractmethod
    def list(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """
        列出检查点摘要。
        
        Args:
            task_id: 可选，按任务 ID 筛选
        
        Returns:
            检查点摘要列表（按时间倒序）
        """
        ...

    @abstractmethod
    def delete_task(self, task_id: str) -> int:
        """
        删除某任务的所有检查点。
        
        Returns:
            删除的记录数
        """
        ...

    @abstractmethod
    def clean_old(self, max_age_days: int) -> int:
        """
        清理超过指定天数的检查点。
        
        Returns:
            清理的记录数
        """
        ...

    @abstractmethod
    def cleanup_task(self, task_id: str, keep: int) -> None:
        """
        清理某任务的旧检查点，只保留最近 keep 个。
        """
        ...

    @abstractmethod
    def count(self, task_id: str | None = None) -> int:
        """统计检查点数量。"""
        ...


# ── 文件后端 ──────────────────────────────────────────────


class FileBackend(StorageBackend):
    """
    JSON 文件存储后端（默认，向后兼容）。
    
    每个检查点一个独立 JSON 文件，存储在 memory/checkpoints/ 目录。
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        if directory is None:
            self._dir = SANDBOX_DIR / "memory" / "checkpoints"
        else:
            self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """把 checkpoint_id 中的非法文件名字符替换为下划线。

        Windows 文件名不允许 <>:"/\\|?* 等字符；task_id（如 "wf:WF-xxx"）含冒号时，
        直接作为文件名会导致写入失败。统一替换保证跨平台可用。
        """
        return re.sub(r'[<>:"/\\|?*]', '_', name)

    def save(self, checkpoint: dict[str, Any]) -> str:
        cp_id = checkpoint["checkpoint_id"]
        cp_file = self._dir / f"{self._safe_filename(cp_id)}.json"
        try:
            cp_file.write_text(
                json.dumps(checkpoint, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (OSError, UnicodeError) as exc:
            raise IOError(f"检查点保存失败: {exc}") from exc
        return cp_id

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        cp_file = self._dir / f"{self._safe_filename(checkpoint_id)}.json"
        if not cp_file.is_file():
            raise KeyError(f"检查点不存在: {checkpoint_id}")
        try:
            return _read_json_cached(cp_file)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise IOError(f"检查点加载失败: {exc}") from exc

    def list(self, task_id: str | None = None) -> list[dict[str, Any]]:
        if not self._dir.is_dir():
            return []

        checkpoints = []
        for cp_file in sorted(
            self._dir.glob("cp_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = _read_json_cached(cp_file)
                if task_id and data.get("task_id") != task_id:
                    continue
                checkpoints.append({
                    "checkpoint_id": data.get("checkpoint_id", cp_file.stem),
                    "task_id": data.get("task_id", ""),
                    "phase": data.get("phase", ""),
                    "created_at": data.get("created_at", ""),
                    "state_size": len(json.dumps(data.get("state", {}))),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return checkpoints

    def delete_task(self, task_id: str) -> int:
        deleted = 0
        # 文件名按 checkpoint_id 命名，无法用 task_id 前缀匹配；
        # 改为读文件内容判断 task_id（与 list() 一致）
        for cp_file in self._dir.glob("cp_*.json"):
            try:
                data = _read_json_cached(cp_file)
                if data.get("task_id") == task_id:
                    cp_file.unlink()
                    deleted += 1
            except (json.JSONDecodeError, OSError, UnicodeError):
                continue
        return deleted

    def clean_old(self, max_age_days: int) -> int:
        now = time.time()
        cleaned = 0
        for cp_file in self._dir.glob("cp_*.json"):
            try:
                age_days = (now - cp_file.stat().st_mtime) / 86400
                # max_age_days <= 0 表示清理全部；
                # 否则清理 age >= max_age_days（容忍文件系统时间戳精度导致的极小负 age）
                if max_age_days <= 0 or age_days >= max_age_days:
                    cp_file.unlink()
                    cleaned += 1
            except OSError:
                continue
        return cleaned

    def cleanup_task(self, task_id: str, keep: int) -> None:
        # 读文件内容筛选 task_id（与 list() 一致），按 mtime 倒序保留最近 keep 个
        task_cps: list[tuple[Path, float]] = []
        for cp_file in self._dir.glob("cp_*.json"):
            try:
                data = _read_json_cached(cp_file)
                if data.get("task_id") == task_id:
                    task_cps.append((cp_file, cp_file.stat().st_mtime))
            except (json.JSONDecodeError, OSError, UnicodeError):
                continue
        task_cps.sort(key=lambda x: x[1], reverse=True)
        for cp_file, _ in task_cps[keep:]:
            try:
                cp_file.unlink()
            except OSError:
                continue

    def count(self, task_id: str | None = None) -> int:
        if not task_id:
            return len(list(self._dir.glob("cp_*.json")))
        total = 0
        for cp_file in self._dir.glob("cp_*.json"):
            try:
                data = _read_json_cached(cp_file)
                if data.get("task_id") == task_id:
                    total += 1
            except (json.JSONDecodeError, OSError, UnicodeError):
                continue
        return total


# ── SQLite 后端 ───────────────────────────────────────────


class SQLiteBackend(StorageBackend):
    """
    SQLite 存储后端。
    
    特性：
      - WAL 模式：支持并发读（写仍串行）
      - 索引优化：task_id、phase、created_at 建立索引
      - 自动建表：首次使用时创建
      - 事务保护：save/delete 在事务中执行
    
    参考：LangGraph SqliteSaver 的实现模式
    
    Schema:
      CREATE TABLE checkpoints (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          checkpoint_id TEXT UNIQUE NOT NULL,
          task_id TEXT NOT NULL,
          phase TEXT NOT NULL,
          created_at TEXT NOT NULL,
          metadata_json TEXT DEFAULT '{}',
          state_json TEXT DEFAULT '{}'
      );
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL 模式提升并发读取性能
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")  # 5 秒忙等待
        self._create_table()

    def _create_table(self) -> None:
        """创建检查点表及索引。"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT UNIQUE NOT NULL,
                task_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                state_json TEXT DEFAULT '{}'
            );
        """)
        # 索引
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cp_task_id ON checkpoints(task_id);"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cp_phase ON checkpoints(phase);"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cp_created ON checkpoints(created_at);"
        )
        self._conn.commit()

    def _retry_on_lock(self, func, *args, max_retries: int = 3) -> Any:
        """SQLite 忙等待时的自动重试。"""
        last_error = None
        for attempt in range(max_retries):
            try:
                return func(*args)
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "database is locked" in str(exc).lower() and attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
        raise last_error  # type: ignore[misc]

    # ── StorageBackend 接口实现 ───────────────────────────

    def save(self, checkpoint: dict[str, Any]) -> str:
        cp_id = checkpoint["checkpoint_id"]
        task_id = checkpoint.get("task_id", "")
        phase = checkpoint.get("phase", "")
        created_at = checkpoint.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        metadata_json = json.dumps(checkpoint.get("metadata", {}), ensure_ascii=False)
        state_json = json.dumps(checkpoint.get("state", {}), ensure_ascii=False)

        def _do_save() -> str:
            self._conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (checkpoint_id, task_id, phase, created_at, metadata_json, state_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cp_id, task_id, phase, created_at, metadata_json, state_json),
            )
            self._conn.commit()
            return cp_id

        return self._retry_on_lock(_do_save)

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        def _do_load() -> dict[str, Any]:
            row = self._conn.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"检查点不存在: {checkpoint_id}")

            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                metadata = {}
            try:
                state = json.loads(row["state_json"])
            except json.JSONDecodeError:
                state = {}

            return {
                "checkpoint_id": row["checkpoint_id"],
                "task_id": row["task_id"],
                "phase": row["phase"],
                "created_at": row["created_at"],
                "metadata": metadata,
                "state": state,
            }

        return self._retry_on_lock(_do_load)

    def list(self, task_id: str | None = None) -> list[dict[str, Any]]:
        def _do_list() -> list[dict[str, Any]]:
            if task_id:
                rows = self._conn.execute(
                    """SELECT checkpoint_id, task_id, phase, created_at, state_json
                       FROM checkpoints WHERE task_id = ?
                       ORDER BY created_at DESC""",
                    (task_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT checkpoint_id, task_id, phase, created_at, state_json
                       FROM checkpoints
                       ORDER BY created_at DESC""",
                ).fetchall()

            results = []
            for row in rows:
                try:
                    state_size = len(row["state_json"])
                except Exception:
                    state_size = 0
                results.append({
                    "checkpoint_id": row["checkpoint_id"],
                    "task_id": row["task_id"],
                    "phase": row["phase"],
                    "created_at": row["created_at"],
                    "state_size": state_size,
                })
            return results

        return self._retry_on_lock(_do_list)

    def delete_task(self, task_id: str) -> int:
        def _do_delete() -> int:
            cursor = self._conn.execute(
                "DELETE FROM checkpoints WHERE task_id = ?",
                (task_id,),
            )
            self._conn.commit()
            return cursor.rowcount

        return self._retry_on_lock(_do_delete)

    def clean_old(self, max_age_days: int) -> int:
        def _do_clean() -> int:
            cursor = self._conn.execute(
                """DELETE FROM checkpoints
                   WHERE created_at < datetime('now', ? || ' days')""",
                (f"-{max_age_days}",),
            )
            self._conn.commit()
            return cursor.rowcount

        return self._retry_on_lock(_do_clean)

    def cleanup_task(self, task_id: str, keep: int) -> None:
        def _do_cleanup() -> None:
            # 查找需要删除的检查点（保留最近 keep 个）
            rows = self._conn.execute(
                """SELECT checkpoint_id FROM checkpoints
                   WHERE task_id = ?
                   ORDER BY created_at DESC
                   LIMIT -1 OFFSET ?""",
                (task_id, keep),
            ).fetchall()
            for row in rows:
                self._conn.execute(
                    "DELETE FROM checkpoints WHERE checkpoint_id = ?",
                    (row["checkpoint_id"],),
                )
            self._conn.commit()

        self._retry_on_lock(_do_cleanup)

    def count(self, task_id: str | None = None) -> int:
        if task_id:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM checkpoints WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM checkpoints",
            ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()

    def vacuum(self) -> None:
        """清理数据库碎片空间。"""
        self._conn.execute("VACUUM;")


# ── 后端工厂 ──────────────────────────────────────────────


def create_backend(
    backend_type: str = "file",
    path: str | None = None,
) -> StorageBackend:
    """
    创建存储后端实例。
    
    Args:
        backend_type: "file" 或 "sqlite"
        path: 存储路径（文件后端用目录，SQLite 用 .db 文件路径）
    
    Returns:
        StorageBackend 实例
    """
    if backend_type == "sqlite":
        db_path = path or str(SANDBOX_DIR / "memory" / "checkpoints.db")
        return SQLiteBackend(db_path)
    else:
        directory = path or str(SANDBOX_DIR / "memory" / "checkpoints")
        return FileBackend(directory)
