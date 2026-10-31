"""测试完整性审计（T2798 / P0-②）。

存在理由
--------
CI 首次全绿时，results job 只用了 18 秒就跑完 600 个用例，而本地需要 70 秒。
这种"快得不合理"可能是 Linux 确实更快，也可能意味着测试根本没跑——
一个"因为没跑所以通过"的 CI 比没有 CI 更危险，它给出虚假的安全感。

本脚本把"这次绿灯到底有没有意义"变成可执行的硬断言：
  1. 收集数下限  —— 防止 conftest 报错/配置错误导致测试静默消失
  2. 通过数下限  —— 防止大范围 skip 伪装成通过
  3. 跳过数上限  —— 防止 skip 泛滥
  4. 失败数上限  —— 失败必须为零（已登记在册的除外）

已知失败从 eval/governance/known_test_failures.json 读取，不在本文件硬编码，
保证"CI 排除的用例"与"正式登记的用例"永远是同一份清单。

用法：
    python scripts/test_audit.py                  # 全量审计
    python scripts/test_audit.py --quick          # 仅统计收集数（约 2 秒）
    python scripts/test_audit.py --json
退出码：0 通过；1 审计失败；2 执行异常
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWN_FAILURES = ROOT / "eval" / "governance" / "known_test_failures.json"

# 阈值：低于/高于即视为异常。基线为 602 个用例（2026-10-30 实测）。
MIN_COLLECTED = 550
MIN_PASSED = 540
MAX_SKIPPED = 15
MAX_FAILED = 0


def _allowed_deselects() -> list[str]:
    """从已知失败登记表生成 --deselect 参数（单一事实来源）。"""
    if not KNOWN_FAILURES.is_file():
        return []
    try:
        data = json.loads(KNOWN_FAILURES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for item in data.get("known_failures", []):
        if item.get("status") in ("accepted", "open"):
            test = item.get("test", "").strip()
            if test:
                out.append(f"--deselect={test}")
    return out


def _run_pytest(extra: list[str]) -> tuple[str, float]:
    cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header",
           "-p", "no:cacheprovider", *extra]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, errors="replace")
    return (proc.stdout or "") + (proc.stderr or ""), time.perf_counter() - t0


def _parse_counts(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in ("passed", "failed", "skipped", "error", "errors", "deselected", "xfailed", "xpassed"):
        m = re.search(rf"(\d+)\s+{key}\b", output)
        if m:
            counts["error" if key == "errors" else key] = int(m.group(1))
    m = re.search(r"(\d+)\s+tests?\s+collected", output)
    if m:
        counts["collected"] = int(m.group(1))
    return counts


def _judge(counts: dict[str, int], quick: bool) -> list[str]:
    """判定统计是否满足完整性要求，返回问题列表（空 = 通过）。

    抽成纯函数以便自检套件直接验证判定逻辑（该红时必红），
    无需真的让测试消失。
    """
    problems: list[str] = []
    if quick:
        collected = counts.get("collected", 0)
        if collected < MIN_COLLECTED:
            problems.append(f"收集数过低: {collected} < {MIN_COLLECTED}（测试可能未被收集）")
        return problems

    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0) + counts.get("error", 0)
    skipped = counts.get("skipped", 0)

    if passed < MIN_PASSED:
        problems.append(f"通过数过低: {passed} < {MIN_PASSED}（疑似测试未真正执行）")
    if failed > MAX_FAILED:
        problems.append(f"失败数超限: {failed} > {MAX_FAILED}")
    total_seen = passed + failed + skipped
    if total_seen < MIN_COLLECTED:
        problems.append(f"执行用例总数过低: {total_seen} < {MIN_COLLECTED}")
    if skipped > MAX_SKIPPED:
        problems.append(f"跳过数过多: {skipped} > {MAX_SKIPPED}（疑似大范围 skip 伪装通过）")
    return problems


def main() -> int:
    argv = sys.argv[1:]
    quick = "--quick" in argv
    as_json = "--json" in argv

    deselects = _allowed_deselects()

    try:
        if quick:
            out, elapsed = _run_pytest(["--collect-only", *deselects])
            counts = _parse_counts(out)
            checks = {
                "collected": (counts.get("collected", 0), MIN_COLLECTED),
            }
        else:
            out, elapsed = _run_pytest(deselects)
            counts = _parse_counts(out)
            checks = {
                "collected": (counts.get("collected", 0), MIN_COLLECTED) if "collected" in counts else None,
                "passed": (counts.get("passed", 0), MIN_PASSED),
            }
    except Exception as exc:  # noqa: BLE001
        print(f"审计执行异常: {type(exc).__name__}: {exc}")
        return 2

    problems: list[str] = _judge(counts, quick)

    result = {
        "mode": "quick" if quick else "full",
        "elapsed_s": round(elapsed, 1),
        "counts": counts,
        "deselected_known_failures": deselects,
        "thresholds": {
            "min_collected": MIN_COLLECTED, "min_passed": MIN_PASSED,
            "max_skipped": MAX_SKIPPED, "max_failed": MAX_FAILED,
        },
        "passed": not problems,
        "problems": problems,
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print("测试完整性审计")
        print("=" * 66)
        print(f"模式      : {result['mode']}   耗时 {result['elapsed_s']}s")
        print(f"统计      : {counts or '未解析到任何统计'}")
        if deselects:
            print(f"已登记排除: {len(deselects)} 项（来自 known_test_failures.json）")
        print("-" * 66)
        if problems:
            for p in problems:
                print(f"  ❌ {p}")
        else:
            print("  ✅ 测试完整性校验通过")
        print("=" * 66)

    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
