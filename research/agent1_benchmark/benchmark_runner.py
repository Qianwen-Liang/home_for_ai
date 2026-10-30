"""benchmark_runner — Agent 1 基准运行器 v1.0
============================================
让 research/agent1_benchmark/agent1_tasks.yaml 真正"跑起来"。

借鉴 ReasFlow benchmarks 的设计：提供两类能力：
  1. verify —— 校验任务集完整性（不调用模型，类比 ReasFlow 的离线 verify）
  2. check —— 对某任务的产物运行确定性检查（调用 artifact_validator / test_runner）

评估双轨制（对齐 TASK_PROVENANCE.yaml 的 eval_protocol）：
  - deterministic 检查：确定性、可自动验证（本运行器执行）
  - llm_scored 检查：需 LLM 评分（本运行器仅标注，不自动打分）

用法：
  python benchmark_runner.py verify                      # 校验任务集
  python benchmark_runner.py list                        # 列出所有任务
  python benchmark_runner.py check res_001 --content ...  # 检查某任务产物
  python benchmark_runner.py report                      # 生成能力覆盖报告
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent
BENCHMARK_DIR = Path(__file__).resolve().parent
TASKS_FILE = BENCHMARK_DIR / "agent1_tasks.yaml"

# deterministic key → 工具映射
DETERMINISTIC_TOOL_MAP = {
    "reference_traceable": "artifact_validator",
    "numeric_consistent": "artifact_validator",
    "section_complete": "artifact_validator",
    "execution_evidence": "artifact_validator",
    "test_pass": "test_runner",
    "coverage": "artifact_validator",
    "risk_listed": "artifact_validator",
    "bottleneck_identified": "artifact_validator",
    "anomaly_flagged": "artifact_validator",
    "terminology_consistent": "artifact_validator",
    "issue_detected": "artifact_validator",
    "review_precision": "artifact_validator",
    "interface_defined": "artifact_validator",
    "dependency_valid": "artifact_validator",
    "root_cause_correct": "artifact_validator",
    "snapshot_complete": "artifact_validator",
}


def _load_yaml(path: Path) -> dict:
    """加载 YAML，优先用 pyyaml，回退到简单解析。"""
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        raise RuntimeError("需要安装 pyyaml 才能解析任务集（pip install pyyaml）")


def load_tasks(tasks_file: Path | None = None) -> dict:
    """加载任务集。默认内部任务集，可指定外部任务集。"""
    path = tasks_file or TASKS_FILE
    if not path.is_file():
        raise RuntimeError(f"任务集文件不存在: {path}")
    return _load_yaml(path)


# ── verify：任务集完整性校验（不调模型）──────────────────

def verify(tasks_file: Path | None = None) -> str:
    """校验任务集完整性，返回报告文本。类比 ReasFlow 的离线 verify。"""
    data = load_tasks(tasks_file)
    lines = ["📋 任务集完整性校验", "=" * 40]

    issues: list[str] = []

    # 1. metadata
    meta = data.get("metadata", {})
    total_declared = meta.get("total", 0)
    tasks = data.get("tasks", [])
    if total_declared != len(tasks):
        issues.append(f"metadata.total({total_declared}) != 实际任务数({len(tasks)})")

    # 2. 任务必需字段
    required_fields = ["id", "capability", "domain", "title", "task", "goal", "eval_metric"]
    seen_ids = set()
    for t in tasks:
        tid = t.get("id", "?")
        for f in required_fields:
            if f not in t:
                issues.append(f"任务 [{tid}] 缺少字段: {f}")
        if tid in seen_ids:
            issues.append(f"任务 ID 重复: {tid}")
        seen_ids.add(tid)

        # eval_metric 结构
        for m in t.get("eval_metric", []):
            if "type" not in m or "key" not in m:
                issues.append(f"任务 [{tid}] eval_metric 缺少 type/key")

    # 3. 能力单元覆盖
    capabilities = {}
    for t in tasks:
        cap = t.get("capability", "unknown")
        capabilities[cap] = capabilities.get(cap, 0) + 1

    # 4. 任务群声明与实际一致性（仅对声明了 capability 的群检查）
    groups = data.get("task_groups", {})
    for gname, g in groups.items():
        declared = g.get("count", 0)
        cap = g.get("capability")
        if cap is None:
            # 无 capability 声明（如按来源分组的外部任务群），跳过能力计数检查
            continue
        actual = capabilities.get(cap, 0)
        if declared != actual:
            issues.append(f"任务群 [{gname}] 声明 {declared} 个，实际 {actual} 个")

    lines.append(f"任务总数: {len(tasks)}")
    lines.append(f"任务 ID 唯一: {'✅' if len(seen_ids) == len(tasks) else '❌'}")
    lines.append(f"能力单元覆盖:")
    for cap, cnt in sorted(capabilities.items(), key=lambda x: -x[1]):
        lines.append(f"  {cap}: {cnt} 个任务")

    if issues:
        lines.append(f"\n❌ 发现 {len(issues)} 个问题:")
        for i in issues:
            lines.append(f"  • {i}")
    else:
        lines.append(f"\n✅ 任务集完整性校验通过")

    return "\n".join(lines)


# ── list：列出所有任务 ──────────────────────────────────

def list_tasks(tasks_file: Path | None = None) -> str:
    data = load_tasks(tasks_file)
    tasks = data.get("tasks", [])
    lines = [f"📚 任务列表（共 {len(tasks)} 个）", "=" * 40]
    for t in tasks:
        lines.append(f"  [{t['id']}] ({t['capability']}) {t['title']}")
    return "\n".join(lines)


# ── check：对某任务产物运行确定性检查 ───────────────────

def check_task(task_id: str, content: str, artifact_type: str = "report", tasks_file: Path | None = None) -> str:
    """对某任务的产物运行确定性检查。"""
    data = load_tasks(tasks_file)
    task = next((t for t in data.get("tasks", []) if t.get("id") == task_id), None)
    if task is None:
        return f"❌ 未找到任务: {task_id}"

    lines = [f"🔍 任务 [{task_id}] 确定性检查", "=" * 40]
    lines.append(f"标题: {task['title']}")
    lines.append(f"能力: {task['capability']}")
    lines.append("")

    deterministic_checks = [
        m for m in task.get("eval_metric", []) if m.get("type") == "deterministic"
    ]
    llm_checks = [m for m in task.get("eval_metric", []) if m.get("type") == "llm_scored"]

    if not deterministic_checks:
        lines.append("该任务无确定性检查项，全部为 LLM 评分。")
    else:
        # 对所有 deterministic 检查项，统一用 artifact_validator 校验产物
        try:
            from tools.artifact_validator import _validator
            report = _validator.validate(content, artifact_type=artifact_type)
            lines.append(f"产物校验（artifact_validator）: {'✅ 通过' if report.passed else '❌ 未通过'}")
            if report.issues:
                for issue in report.issues:
                    tag = "🔴" if issue.level == "error" else "🟡"
                    lines.append(f"  {tag} [{issue.dimension}] {issue.message}")
            # 映射到任务的确定性检查项
            lines.append("")
            lines.append("确定性检查项覆盖情况:")
            for m in deterministic_checks:
                key = m.get("key", "")
                tool = DETERMINISTIC_TOOL_MAP.get(key, "unknown")
                if tool == "test_runner":
                    status = "需 test_runner 单独运行"
                else:
                    status = "已由 artifact_validator 覆盖检查"
                lines.append(f"  - {key} ({m.get('desc', '')}): {status}")
        except Exception as exc:
            lines.append(f"❌ 产物校验失败: {exc}")

    if llm_checks:
        lines.append("")
        lines.append(f"⚠️ LLM 评分项（{len(llm_checks)} 项，需另行评分）:")
        for m in llm_checks:
            lines.append(f"  - {m.get('key')}: {m.get('desc', '')}")

    return "\n".join(lines)


# ── report：能力覆盖报告 ────────────────────────────────

def report(tasks_file: Path | None = None) -> str:
    data = load_tasks(tasks_file)
    tasks = data.get("tasks", [])
    lines = ["📊 基准能力覆盖报告", "=" * 40]

    capabilities = {}
    det_count = 0
    llm_count = 0
    for t in tasks:
        cap = t.get("capability", "unknown")
        capabilities[cap] = capabilities.get(cap, 0) + 1
        for m in t.get("eval_metric", []):
            if m.get("type") == "deterministic":
                det_count += 1
            elif m.get("type") == "llm_scored":
                llm_count += 1

    lines.append(f"任务总数: {len(tasks)}")
    lines.append(f"能力单元数: {len(capabilities)}")
    lines.append(f"确定性检查项: {det_count} | LLM 评分项: {llm_count}")
    lines.append("")
    for cap, cnt in sorted(capabilities.items(), key=lambda x: -x[1]):
        lines.append(f"  {cap}: {cnt} 个任务")

    return "\n".join(lines)


# ── CLI 入口 ──────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 1 基准运行器")
    parser.add_argument("--tasks-file", default="", help="任务集文件路径（默认 agent1_tasks.yaml）")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("verify", help="校验任务集完整性")
    sub.add_parser("list", help="列出所有任务")
    sub.add_parser("report", help="生成能力覆盖报告")

    p_check = sub.add_parser("check", help="检查某任务产物")
    p_check.add_argument("task_id")
    p_check.add_argument("--content", default="", help="产物内容")
    p_check.add_argument("--artifact-type", default="report")
    p_check.add_argument("--content-file", default="", help="从文件读取产物内容")

    args = parser.parse_args()

    tasks_file = Path(args.tasks_file) if args.tasks_file else None

    if args.cmd == "verify":
        print(verify(tasks_file))
    elif args.cmd == "list":
        print(list_tasks(tasks_file))
    elif args.cmd == "report":
        print(report(tasks_file))
    elif args.cmd == "check":
        content = args.content
        if args.content_file:
            content = Path(args.content_file).read_text(encoding="utf-8")
        print(check_task(args.task_id, content, args.artifact_type, tasks_file))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
