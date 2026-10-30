"""capsule — 长周期任务的上下文胶囊（P3 架构治理）

设计动机（一手调研）：
  - aigent-os：context 达 80% 时写入 verified capsule → /clear → 新 session 恢复，
    避免"摘要的摘要"逐轮失真。
  - Anthropic Effective harnesses for long-running agents：initializer agent 建环境，
    coding agent 每会话增量推进并留下干净状态；两个典型失败模式是
    ① 试图 one-shot 导致上下文耗尽 ② 后到会话看到有进展就误判完成。

本模块不注册为 LLM 工具（遵循 P0 工具集收敛原则），而是：
  - 提供确定性 API 供会话流程/脚本调用；
  - 与 knowledge 工具联动：capsule 以 kind="procedural"、category="capsule" 沉淀，
    需要时可被检索到。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent.parent
CAPSULE_DIR = SANDBOX / "memory" / "capsule"


class CapsuleError(RuntimeError):
    """胶囊操作错误。"""


def _path(task_id: str) -> Path:
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in task_id)
    if not safe:
        raise CapsuleError("task_id 不能为空")
    return CAPSULE_DIR / f"{safe}.json"


def save_capsule(task_id: str, state: dict, note: str = "") -> str:
    """写入（或覆盖）任务胶囊。

    state 建议字段：
      goal        任务目标（一句话）
      done        已完成事项（列表）
      doing       进行中事项（列表）
      todo        待办事项（列表）
      decisions   关键决策与理由（列表）
      files       涉及文件及其当前状态（字典）
      blockers    阻塞点（列表）
    """
    if not isinstance(state, dict):
        raise CapsuleError("state 必须是字典")
    CAPSULE_DIR.mkdir(parents=True, exist_ok=True)
    caps = {
        "task_id": task_id,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": _next_version(task_id),
        "note": note,
        "state": state,
    }
    p = _path(task_id)
    p.write_text(json.dumps(caps, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"✅ 胶囊已保存：{p.name}（v{caps['version']}，{caps['updated_at']}）"


def _next_version(task_id: str) -> int:
    try:
        old = json.loads(_path(task_id).read_text(encoding="utf-8"))
        return int(old.get("version", 0)) + 1
    except Exception:
        return 1


def load_capsule(task_id: str) -> dict | None:
    """读取任务胶囊，不存在返回 None。"""
    p = _path(task_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapsuleError(f"胶囊读取失败: {exc}") from exc


def list_capsules() -> list[dict]:
    """列出全部胶囊摘要（按更新时间倒序）。"""
    if not CAPSULE_DIR.is_dir():
        return []
    out = []
    for f in CAPSULE_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "task_id": d.get("task_id", f.stem),
                "version": d.get("version", 0),
                "updated_at": d.get("updated_at", ""),
                "goal": (d.get("state") or {}).get("goal", ""),
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["updated_at"], reverse=True)
    return out


def render_capsule(capsule: dict) -> str:
    """把胶囊渲染为可直接注入上下文的紧凑文本。"""
    s = capsule.get("state") or {}
    lines = [
        f"🧷 任务胶囊 [{capsule.get('task_id')}] v{capsule.get('version')} "
        f"（{capsule.get('updated_at')}）",
    ]
    if s.get("goal"):
        lines.append(f"🎯 目标：{s['goal']}")
    for key, icon in (("done", "✅"), ("doing", "🔄"), ("todo", "⬜"),
                      ("decisions", "🧭"), ("blockers", "⛔")):
        items = s.get(key) or []
        if items:
            lines.append(f"{icon} {key}:")
            lines.extend(f"   - {str(i)[:160]}" for i in items[:12])
    files = s.get("files") or {}
    if files:
        lines.append("📁 文件状态:")
        for k, v in list(files.items())[:12]:
            lines.append(f"   - {k}: {str(v)[:80]}")
    return "\n".join(lines)


def should_checkpoint(message_count: int, threshold: int = 120) -> bool:
    """是否应触发胶囊写入（近似 aigent-os 的 80% 上下文阈值思路）。

    这里用消息条数作为上下文占用的廉价代理指标。
    """
    return message_count >= threshold
