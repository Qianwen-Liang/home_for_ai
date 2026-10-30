"""沙箱命令时限分档管理（v1.0）。

以 120s 为基础档位，向下和向上设立若干档位，可在需要时自由切换。
当前档位持久化在 tools/timeout_tier.json，run_command 每次调用时动态读取，
因此切换档位后立即生效，无需重启进程。

档位表（秒）：
    向下 4 档：15, 30, 60, 90
    基础档   ：120
    向上 6 档：180, 300, 600, 900, 1800, 3600

用法（CLI）：
    python tools/timeout_tier.py            # 查看当前档位与全部档位
    python tools/timeout_tier.py list       # 同上
    python tools/timeout_tier.py 300        # 切换到 300s 档位
"""

from __future__ import annotations

import json
from pathlib import Path

TIER_FILE = Path(__file__).resolve().parent / "timeout_tier.json"

# 档位表（秒）：向下 + 基础 + 向上
TIERS: list[int] = [15, 30, 60, 90, 120, 180, 300, 600, 900, 1800, 3600]
BASE_TIER: int = 120
DEFAULT_TIER: int = 120


def _read_raw() -> int:
    """读取配置文件里的 current_tier，任何异常回退默认档。"""
    try:
        data = json.loads(TIER_FILE.read_text(encoding="utf-8"))
        return int(data.get("current_tier", DEFAULT_TIER))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return DEFAULT_TIER


def get_current_tier() -> int:
    """返回当前档位（秒）。非法档位回退默认档。"""
    tier = _read_raw()
    return tier if tier in TIERS else DEFAULT_TIER


def set_current_tier(seconds) -> str:
    """切换档位并返回提示信息。"""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return f"⚠️ 档位必须是整数秒，收到：{seconds!r}"
    if seconds not in TIERS:
        return (f"⚠️ 无效档位 {seconds}s。合法档位（秒）：{TIERS}。"
                f"基础档位为 {BASE_TIER}s。")
    data = {"current_tier": seconds, "base_tier": BASE_TIER, "tiers": TIERS}
    try:
        TIER_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        return f"⚠️ 写入配置文件失败：{exc}"
    return f"✅ 时限档位已切换为 {seconds}s"


def list_tiers() -> str:
    """列出全部档位，标注当前档位。"""
    cur = get_current_tier()
    marks = "  ".join(f"[{'●' if t == cur else ' '}{t}s]" for t in TIERS)
    return f"当前档位：{cur}s（基础档 {BASE_TIER}s）\n档位列表：{marks}"


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if not args or args[0] in ("list", "ls"):
        print(list_tiers())
    else:
        print(set_current_tier(args[0]))
