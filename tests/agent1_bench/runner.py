"""Agent1-bench — 基准运行器

运行 tests/agent1_bench/tasks/ 下所有任务，自动评分，
输出通过率、分类通过率、六层维度统计。

评分方式：
  - 每个任务文件含 _test() 函数（一组 assert 断言）
  - 运行 _test() 无异常 → PASS；AssertionError → FAIL；其他 → ERROR
  - 通过率 = PASS 数 / 总任务数
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
TASKS_DIR = BENCH_DIR / "tasks"
RESULTS_FILE = BENCH_DIR / "results.json"


def _load_task_module(task_file: Path):
    """从文件加载任务模块。"""
    spec = importlib.util.spec_from_file_location(f"bench_{task_file.stem}", task_file)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # 注册到 sys.modules，供测试内 sys.modules[__name__] 访问
    spec.loader.exec_module(module)
    return module


def run_benchmark() -> dict[str, Any]:
    """运行所有任务并返回评分结果。"""
    task_files = sorted(TASKS_DIR.glob("t*.py"))
    if not task_files:
        return {"error": "无任务文件（tasks/ 目录为空）", "total": 0}

    results: list[dict[str, Any]] = []
    for tf in task_files:
        entry = {"task_id": tf.stem}
        try:
            module = _load_task_module(tf)
            entry["title"] = getattr(module, "TASK_TITLE", tf.stem)
            entry["dimension"] = getattr(module, "TASK_DIMENSION", "unknown")
            entry["difficulty"] = getattr(module, "TASK_DIFFICULTY", "unknown")
            test_fn = getattr(module, "_test", None)
            if test_fn is None:
                entry["status"] = "ERROR"
                entry["detail"] = "缺少 _test() 函数"
            else:
                test_fn()
                entry["status"] = "PASS"
                entry["detail"] = ""
        except AssertionError as exc:
            entry["status"] = "FAIL"
            entry["detail"] = f"断言失败: {exc}"
        except Exception as exc:
            entry["status"] = "ERROR"
            entry["detail"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errored = sum(1 for r in results if r["status"] == "ERROR")

    # 分类统计
    dim_stats: dict[str, dict[str, int]] = {}
    for r in results:
        dim = r.get("dimension", "unknown")
        d = dim_stats.setdefault(dim, {"total": 0, "pass": 0})
        d["total"] += 1
        if r["status"] == "PASS":
            d["pass"] += 1

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "dimensions": dim_stats,
        "results": results,
    }


def format_report(data: dict[str, Any]) -> str:
    """格式化基准报告。"""
    if "error" in data:
        return f"⚠️ {data['error']}"

    lines = [
        "🎯 Agent1-bench 基准报告",
        "=" * 50,
        f"时间: {data['timestamp']}",
        f"总任务: {data['total']} | ✅ 通过: {data['passed']} | "
        f"❌ 失败: {data['failed']} | ⚠️ 错误: {data['errored']}",
        f"通过率: {data['pass_rate']*100:.1f}%",
        "",
        "📊 能力维度统计:",
    ]

    for dim, stats in sorted(data["dimensions"].items()):
        rate = stats["pass"] / stats["total"] * 100 if stats["total"] else 0
        bar = "█" * int(rate / 10) + "░" * (10 - int(rate / 10))
        lines.append(f"  {dim:20s} {bar} {stats['pass']}/{stats['total']} ({rate:.0f}%)")

    lines.append("")
    lines.append("📋 详细结果:")
    for r in data["results"]:
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}.get(r["status"], "•")
        detail = f" — {r['detail'][:60]}" if r.get("detail") else ""
        lines.append(f"  {icon} [{r['task_id']}] {r.get('title','')} ({r.get('dimension','')}){detail}")

    return "\n".join(lines)


def main() -> int:
    data = run_benchmark()
    RESULTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(data))
    return 0 if data.get("pass_rate", 0) == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
