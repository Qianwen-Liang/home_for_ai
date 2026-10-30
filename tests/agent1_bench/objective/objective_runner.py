"""objective_runner.py — Agent1-bench 客观评测器

基于 QuixBugs（外部公开程序修复基准）的客观评测：
  1. 加载 Agent 1 现场作答（agent_answers.py）
  2. 加载 QuixBugs 官方 JSON 测试用例（research/QuixBugs/json_testcases/）
  3. 客观验证：运行答案函数，比对输出与期望值
  4. 统计真实通过率（区别于原 bench 的"预置答案 100%"）

口径对齐 QuixBugs 官方 pytest 测试（python_testcases/*.py）：
  - 跳过官方标记为"慢"的用例（pytest.skip）：knapsack 大容量、levenshtein 长串
  - hanoi：期望输出转元组（官方 test_hanoi.py 的 [tuple(x) for x in out]）
  - sqrt：近似比较（官方 test_sqrt.py 的 pytest.approx(expected, abs=epsilon)）

用法：
    python -X utf8 tests/agent1_bench/objective/objective_runner.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = BENCH_DIR.parent.parent.parent  # agent-sandbox
QUIXBUGS_DIR = SANDBOX_DIR / "research" / "QuixBugs"
RESULTS_FILE = BENCH_DIR / "results.json"

# 31 个 json 任务（QuixBugs 全部非图算法任务）
TASKS = [
    "gcd",
    "quicksort",
    "flatten",
    "powerset",
    "lcs_length",
    "find_first_in_sorted",
    "next_palindrome",
    "mergesort",
    "bitcount",
    "bucketsort",
    "find_in_sorted",
    "get_factors",
    "hanoi",
    "is_valid_parenthesization",
    "kheapsort",
    "knapsack",
    "kth",
    "levenshtein",
    "lis",
    "longest_common_subsequence",
    "max_sublist_sum",
    "next_permutation",
    "pascal",
    "possible_change",
    "rpn_eval",
    "shunting_yard",
    "sieve",
    "sqrt",
    "subsequences",
    "to_base",
    "wrap",
]

# 官方 python_testcases 中标记为 pytest.skip 的"慢"用例（超出合理运行时间）。
# 跳过它们以对齐官方评测口径，避免挂起。
SLOW_CASES = {
    "knapsack": lambda inp: inp[0] == 6404180,
    "levenshtein": lambda inp: inp == [
        "amanaplanacanalpanama",
        "docnoteidissentafastneverpreventsafatnessidietoncod",
    ],
}


def load_answers():
    """加载 Agent 1 现场作答模块。"""
    spec = importlib.util.spec_from_file_location(
        "agent_answers", BENCH_DIR / "agent_answers.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_testcases(name: str) -> list[list[Any]]:
    """加载 QuixBugs 官方 JSON 测试用例（每行 [输入参数列表, 期望输出]）。"""
    path = QUIXBUGS_DIR / "json_testcases" / f"{name}.json"
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def normalize(actual: Any) -> Any:
    """将生成器等可迭代对象转为 list，便于与期望值比较。"""
    if hasattr(actual, "__iter__") and not isinstance(
        actual, (list, tuple, str, dict, int, float, bool, type(None))
    ):
        return list(actual)
    return actual


def is_equal(name: str, input_args: list, actual: Any, expected: Any) -> bool:
    """按官方测试口径比较结果（hanoi 转元组、sqrt 近似比较，其余精确相等）。"""
    if name == "hanoi":
        # 官方 test_hanoi.py: testdata = [[inp, [tuple(x) for x in out]] ...]
        expected = [tuple(x) for x in expected]
    elif name == "sqrt":
        # 官方 test_sqrt.py: sqrt(...) == pytest.approx(expected, abs=epsilon)
        epsilon = input_args[-1]
        return abs(actual - expected) <= epsilon
    return actual == expected


def run_objective() -> dict[str, Any]:
    answers = load_answers()
    results: list[dict[str, Any]] = []

    for name in TASKS:
        fn = getattr(answers, name, None)
        if fn is None:
            results.append({"task": name, "status": "ERROR", "detail": "缺少作答函数"})
            continue

        testcases = load_testcases(name)
        slow_skip = SLOW_CASES.get(name)
        passed = 0
        total = 0
        skipped = 0
        failed_details: list[str] = []
        for idx, (input_args, expected) in enumerate(testcases):
            if not isinstance(input_args, list):
                input_args = [input_args]
            if slow_skip is not None and slow_skip(input_args):
                skipped += 1
                continue
            total += 1
            try:
                actual = normalize(fn(*input_args))
                if is_equal(name, input_args, actual, expected):
                    passed += 1
                else:
                    failed_details.append(
                        f"case{idx}: 期望 {expected!r} != 实际 {actual!r}"
                    )
            except Exception as exc:
                failed_details.append(
                    f"case{idx}: 异常 {type(exc).__name__}: {exc}"
                )

        if skipped:
            failed_details.append(f"跳过 {skipped} 个官方慢用例")
        results.append({
            "task": name,
            "status": "PASS" if passed == total else "FAIL",
            "passed": passed,
            "total": total,
            "skipped": skipped,
            "detail": "; ".join(failed_details[:3]),
        })

    total_tasks = len(results)
    passed_tasks = sum(1 for r in results if r["status"] == "PASS")
    total_cases = sum(r.get("total", 0) for r in results)
    passed_cases = sum(r.get("passed", 0) for r in results)
    skipped_cases = sum(r.get("skipped", 0) for r in results)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "QuixBugs (external public benchmark)",
        "total_tasks": total_tasks,
        "passed_tasks": passed_tasks,
        "task_pass_rate": round(passed_tasks / total_tasks, 4) if total_tasks else 0.0,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": round(passed_cases / total_cases, 4) if total_cases else 0.0,
        "skipped_cases": skipped_cases,
        "results": results,
    }


def format_report(data: dict[str, Any]) -> str:
    lines = [
        "🎯 Agent1-bench 客观评测报告（QuixBugs 非图算法）",
        "=" * 56,
        f"时间: {data['timestamp']}",
        f"数据源: {data['source']}",
        f"任务通过率: {data['task_pass_rate']*100:.1f}% "
        f"({data['passed_tasks']}/{data['total_tasks']})",
        f"用例通过率: {data['case_pass_rate']*100:.1f}% "
        f"({data['passed_cases']}/{data['total_cases']})",
        f"跳过官方慢用例: {data['skipped_cases']}",
        "",
        "📋 逐任务结果:",
    ]
    for r in data["results"]:
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}.get(r["status"], "•")
        line = f"  {icon} {r['task']:22s} {r.get('passed',0)}/{r.get('total',0)}"
        if r.get("skipped"):
            line += f" (跳过{r['skipped']})"
        if r.get("detail"):
            line += f"  — {r['detail'][:80]}"
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    data = run_objective()
    RESULTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
