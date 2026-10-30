"""
共享黑板 — Blackboard（E-C1）

多 Agent 协作的共享工作内存。
借鉴 MetaGPT 的"共享消息池"设计，为所有 Agent 提供可读写的中间产物空间。
"""

from .blackboard_manager import Blackboard, BoardItem, ItemType, ItemStatus

__all__ = ["Blackboard", "BoardItem", "ItemType", "ItemStatus"]
