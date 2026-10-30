"""Restart manager for Agent 1.

Provides the ability to restart the agent process after modifying its code,
while preserving the full conversation history.  The design uses a temporary
swap file (RESTART_STATE_FILE) to persist the conversation, then calls
os.execv to replace the current process with a fresh one that loads the
saved state automatically.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
RESTART_STATE_FILE = SANDBOX_DIR / ".restart-state.json"


def save_restart_state(
    system_prompt: str,
    messages: list[dict[str, Any]],
) -> None:
    """Persist the conversation so the new process can restore it."""

    data: dict[str, Any] = {
        "system_prompt": system_prompt,
        "messages": messages,
    }
    temporary_file = RESTART_STATE_FILE.with_name(
        RESTART_STATE_FILE.name + ".tmp"
    )
    try:
        temporary_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_file, RESTART_STATE_FILE)
    except OSError:
        try:
            temporary_file.unlink()
        except OSError:
            pass
        raise


def load_restart_state() -> dict[str, Any] | None:
    """Load a previously saved restart state, if it exists."""

    if not RESTART_STATE_FILE.is_file():
        return None
    try:
        data = json.loads(RESTART_STATE_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("system_prompt"), str):
            return None
        messages = data.get("messages")
        if not isinstance(messages, list):
            return None
        if not all(isinstance(message, dict) for message in messages):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def clear_restart_state() -> bool:
    """Remove the restart state file after successfully loading it."""

    try:
        if RESTART_STATE_FILE.is_file():
            RESTART_STATE_FILE.unlink()
        return not RESTART_STATE_FILE.exists()
    except OSError:
        return False


def perform_restart(
    system_prompt: str,
    messages: list[dict[str, Any]],
) -> None:
    """Save the conversation and replace the current process.

    This function does NOT return — it replaces the process with a new
    interpreter that loads agent1.py (or the caller's __main__ module).
    """

    save_restart_state(system_prompt, messages)

    executable = sys.executable
    if not executable:
        executable = "python3"

    script = str(Path(sys.argv[0]).resolve())
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    os.execv(executable, [executable, script, *args])
