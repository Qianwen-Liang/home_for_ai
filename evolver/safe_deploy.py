"""
safe_deploy — 安全部署流水线 v1.0

Evolver 修改代码后自动运行受影响测试，失败则自动回滚。
借鉴 DSPy 的自动验证思想，建立"修改→测试→回滚"安全网。

工作流:
  1. pre_check()  — 记录当前状态
  2. affected_tests(modified_files) — 定位关联测试
  3. run_tests(test_list) — 运行测试
  4. rollback(original_state) — 失败时回滚
  5. deploy_report() — 生成部署报告
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ── 路径设置 ──────────────────────────────────────────────

EVOLVER_DIR = Path(__file__).resolve().parent
SANDBOX_DIR = EVOLVER_DIR.parent
sys.path.insert(0, str(SANDBOX_DIR))

BACKUP_DIR = EVOLVER_DIR / ".deploy_backups"
DEPLOY_LOG = EVOLVER_DIR / "deploy_history.json"

# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class DeployRecord:
    """单次部署记录。"""
    timestamp: str
    files_changed: list[str]
    tests_run: list[str]
    tests_passed: int
    tests_failed: int
    rolled_back: bool
    rollback_reason: str = ""
    backup_id: str = ""
    duration_sec: float = 0.0


# ── 安全部署引擎 ──────────────────────────────────────────


class SafeDeploy:
    """安全部署流水线 — 自动测试 + 失败回滚。"""

    def __init__(self):
        self._modified_files: list[str] = []
        self._backup_id: str = ""
        self._record: DeployRecord | None = None
        self._start_time: float = 0.0

    # ── 步骤 1: 部署前检查 ──────────────────────────────

    def pre_check(self, files: list[str]) -> dict[str, Any]:
        """记录部署前状态，创建备份。

        Args:
            files: 要修改的文件路径列表（相对或绝对路径）

        Returns:
            包含 backup_id 和备份文件映射的字典
        """
        self._start_time = time.time()
        self._modified_files = []
        backup_map = {}

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        self._backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        for file_path in files:
            # 支持相对路径
            p = Path(file_path)
            if not p.is_absolute():
                p = SANDBOX_DIR / p

            if not p.is_file():
                continue

            self._modified_files.append(str(p))

            # 计算文件哈希
            content = p.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()[:16]

            # 创建备份
            backup_name = f"{self._backup_id}_{p.name}"
            backup_path = BACKUP_DIR / backup_name
            shutil.copy2(str(p), str(backup_path))

            backup_map[str(p)] = {
                "backup_path": str(backup_path),
                "hash": file_hash,
                "size": len(content),
            }

        return {
            "backup_id": self._backup_id,
            "files_backed_up": len(backup_map),
            "backup_map": backup_map,
        }

    # ── 步骤 2: 定位受影响测试 ───────────────────────────

    def affected_tests(self, modified_files: list[str] | None = None) -> list[str]:
        """根据修改的文件定位可能受影响的测试。

        策略:
        1. 如果修改的是 tools/X.py，匹配 tests/test_X.py
        2. 如果修改的是 evolver/X.py，匹配 tests/test_evolver*.py
        3. grep 测试文件中对修改模块的引用

        Args:
            modified_files: 修改的文件列表，默认用 pre_check 中记录的文件

        Returns:
            匹配到的测试文件名列表（不含目录前缀）
        """
        files = modified_files or self._modified_files
        if not files:
            return []

        test_dir = SANDBOX_DIR / "tests"
        if not test_dir.is_dir():
            return []

        all_tests = sorted(test_dir.glob("test_*.py"))
        matched: set[str] = set()

        for mod_file in files:
            mod_path = Path(mod_file)
            stem = mod_path.stem  # 不含扩展名的文件名
            parent_dir = mod_path.parent.name if mod_path.parent != SANDBOX_DIR else ""

            # 策略 1: 直接匹配
            if stem.startswith("test_"):
                # 修改的是测试文件本身
                matched.add(mod_path.name)
                continue

            for test_file in all_tests:
                test_name = test_file.name

                # 精确匹配: tools/calculator.py → test_calculator.py
                if parent_dir == "tools":
                    if test_name == f"test_{stem}.py":
                        matched.add(test_name)

                # evolver 模块匹配
                if parent_dir == "evolver":
                    if "evolver" in test_name.lower() or stem in test_name:
                        matched.add(test_name)

                # 策略 2: grep 测试文件中的引用
                try:
                    content = test_file.read_text(encoding="utf-8")
                    # 检查是否 import 或引用被修改的模块
                    if stem in content or f"tools.{stem}" in content:
                        matched.add(test_name)
                except (OSError, UnicodeDecodeError):
                    pass

        # 如果匹配太多（可能是通用修改），至少运行基础测试
        if len(matched) > 10:
            # 优先精确匹配，限制数量
            exact = {t for t in matched if any(
                t == f"test_{Path(f).stem}.py" for f in files
            )}
            if exact:
                return sorted(exact)[:10]
            return sorted(matched)[:10]

        return sorted(matched)

    # ── 步骤 3: 运行测试 ────────────────────────────────

    def run_tests(self, test_list: list[str]) -> dict[str, Any]:
        """运行指定的测试文件列表。

        Args:
            test_list: 测试文件名列表（如 ['test_calculator.py', 'test_monitor.py']）

        Returns:
            {test_name: {passed: bool, output: str, duration: float}}
        """
        if not test_list:
            return {"status": "no_tests", "message": "没有匹配到测试"}

        results = {}
        import subprocess

        test_dir = SANDBOX_DIR / "tests"

        for test_name in test_list:
            test_path = test_dir / test_name
            if not test_path.is_file():
                results[test_name] = {
                    "passed": None,
                    "output": f"测试文件不存在: {test_name}",
                    "duration": 0,
                }
                continue

            t0 = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=short"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(SANDBOX_DIR),
                )
                duration = time.time() - t0
                passed = proc.returncode == 0
                output = proc.stdout[-500:] if proc.stdout else proc.stderr[-500:]

                results[test_name] = {
                    "passed": passed,
                    "output": output,
                    "duration": round(duration, 2),
                }
            except subprocess.TimeoutExpired:
                results[test_name] = {
                    "passed": False,
                    "output": "测试超时（30秒）",
                    "duration": 30.0,
                }
            except Exception as exc:
                results[test_name] = {
                    "passed": False,
                    "output": f"测试执行异常: {exc}",
                    "duration": time.time() - t0,
                }

        return results

    # ── 步骤 4: 回滚 ────────────────────────────────────

    def rollback(self) -> dict[str, Any]:
        """回滚所有修改的文件到备份状态。

        Returns:
            回滚结果摘要
        """
        if not self._backup_id:
            return {"status": "error", "message": "没有备份 ID，无法回滚"}

        restored = []
        failed = []

        for mod_file in self._modified_files:
            p = Path(mod_file)
            backup_name = f"{self._backup_id}_{p.name}"
            backup_path = BACKUP_DIR / backup_name

            if backup_path.is_file():
                try:
                    shutil.copy2(str(backup_path), str(p))
                    restored.append(str(p))
                except OSError as exc:
                    failed.append({"file": str(p), "error": str(exc)})
            else:
                failed.append({"file": str(p), "error": "备份文件不存在"})

        return {
            "status": "success" if not failed else "partial",
            "restored": len(restored),
            "failed": len(failed),
            "details": {"restored_files": restored, "failed_files": failed},
        }

    # ── 步骤 5: 部署报告 ────────────────────────────────

    def deploy_report(self) -> str:
        """生成部署结果报告。"""
        if not self._record:
            return "没有部署记录。请先执行 deploy()。"

        r = self._record
        status_icon = "✅" if not r.rolled_back else "🔄"
        result = "部署成功" if not r.rolled_back else f"已回滚: {r.rollback_reason}"

        lines = [
            f"{status_icon} 安全部署报告",
            f"{'='*50}",
            f"时间: {r.timestamp}",
            f"耗时: {r.duration_sec:.1f} 秒",
            f"备份 ID: {r.backup_id}",
            f"结果: {result}",
            "",
            f"## 修改文件 ({len(r.files_changed)} 个)",
        ]
        for f in r.files_changed:
            lines.append(f"  • {Path(f).name}")

        lines.append(f"\n## 测试执行 ({len(r.tests_run)} 个)")
        lines.append(f"  ✅ 通过: {r.tests_passed}")
        lines.append(f"  ❌ 失败: {r.tests_failed}")

        if r.rolled_back:
            lines.append(f"\n## 回滚")
            lines.append(f"  原因: {r.rollback_reason}")
            lines.append(f"  备份 ID: {r.backup_id}")

        return "\n".join(lines)

    # ── 一键部署 ────────────────────────────────────────

    def deploy(
        self,
        files: list[str],
        auto_rollback: bool = True,
        run_all_tests: bool = False,
        baseline_failures: list[str] | None = None,
    ) -> str:
        """一键安全部署: 备份 → 定位测试 → 运行 → 回滚(如需)。

        Args:
            files: 修改的文件列表
            auto_rollback: 测试失败时是否自动回滚
            run_all_tests: 是否运行全部测试（否则只运行受影响测试）
            baseline_failures: 部署前（未修改）的失败测试名集合。
                提供时，仅对"新引入的失败"（当前失败 - 基线失败）回滚，
                避免因预存在的失败而误回滚。缺省时保持保守（任何失败都回滚）。
        """
        # 1. 备份
        pre = self.pre_check(files)
        if pre["files_backed_up"] == 0:
            return "❌ 没有文件需要备份。请检查文件路径。"

        # 2. 定位测试
        if run_all_tests:
            test_dir = SANDBOX_DIR / "tests"
            test_list = sorted(
                [f.name for f in test_dir.glob("test_*.py")]
                if test_dir.is_dir() else []
            )
        else:
            test_list = self.affected_tests(files)

        # 3. 运行测试
        test_results = self.run_tests(test_list)

        # 4. 评估结果（基线对比：仅对"新引入的失败"回滚）
        passed = sum(1 for r in test_results.values() if r.get("passed"))
        failed_names = [n for n, r in test_results.items() if r.get("passed") is False]
        skipped = sum(1 for r in test_results.values() if r.get("passed") is None)

        baseline_set = set(baseline_failures or [])
        new_failed_names = [n for n in failed_names if n not in baseline_set]
        preexisting_failed = len(failed_names) - len(new_failed_names)

        rolled_back = False
        rollback_reason = ""

        if new_failed_names and auto_rollback:
            rollback_reason = (
                f"{len(new_failed_names)} 个新失败"
                f"（{preexisting_failed} 个预存在失败已忽略），自动回滚"
            )
            self.rollback()
            rolled_back = True
        elif failed_names and not baseline_set and auto_rollback:
            # 无基线数据：保守回滚（保持原有行为）
            rollback_reason = f"{len(failed_names)} 个测试失败，自动回滚"
            self.rollback()
            rolled_back = True

        # 5. 记录
        duration = time.time() - self._start_time
        self._record = DeployRecord(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            files_changed=[Path(f).name for f in self._modified_files],
            tests_run=test_list,
            tests_passed=passed,
            tests_failed=len(failed_names) + skipped,
            rolled_back=rolled_back,
            rollback_reason=rollback_reason,
            backup_id=self._backup_id,
            duration_sec=round(duration, 2),
        )

        self._save_record()
        return self.deploy_report()

    # ── 持久化 ──────────────────────────────────────────

    def _save_record(self) -> None:
        """保存部署记录到磁盘。"""
        if not self._record:
            return

        existing = []
        if DEPLOY_LOG.is_file():
            try:
                existing = json.loads(DEPLOY_LOG.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []

        from dataclasses import asdict
        existing.append(asdict(self._record))

        # 保留最近 50 条
        if len(existing) > 50:
            existing = existing[-50:]

        DEPLOY_LOG.parent.mkdir(parents=True, exist_ok=True)
        DEPLOY_LOG.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def history(self, limit: int = 10) -> str:
        """查看部署历史。"""
        if not DEPLOY_LOG.is_file():
            return "暂无部署记录。"

        try:
            records = json.loads(DEPLOY_LOG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "部署记录文件损坏。"

        if not records:
            return "暂无部署记录。"

        recent = records[-limit:]
        lines = [f"📋 最近 {len(recent)} 次部署\n"]

        for r in reversed(recent):
            icon = "✅" if not r.get("rolled_back") else "🔄"
            files = ", ".join(r.get("files_changed", []))
            lines.append(
                f"  {icon} [{r['timestamp']}] "
                f"{r['tests_passed']}/{r['tests_passed'] + r['tests_failed']} 通过 "
                f"({r['duration_sec']:.1f}s) "
                f"— {files}"
            )

        return "\n".join(lines)

    def cleanup_backups(self, max_age_days: int = 7) -> str:
        """清理过期备份。"""
        if not BACKUP_DIR.is_dir():
            return "备份目录不存在。"

        cutoff = time.time() - max_age_days * 86400
        cleaned = 0

        for backup_file in BACKUP_DIR.iterdir():
            if backup_file.is_file() and backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                cleaned += 1

        return f"已清理 {cleaned} 个过期备份文件。"


# ── 全局单例 ───────────────────────────────────────────────

_deployer = SafeDeploy()


# ── 工具函数 ──────────────────────────────────────────────


def execute_safe_deploy_tool(arguments: dict[str, Any]) -> str:
    """安全部署工具入口。"""
    action = arguments.get("action", "deploy")

    try:
        if action == "deploy":
            files = arguments.get("files", [])
            if isinstance(files, str):
                import json as _json
                files = _json.loads(files)
            if not files:
                return "❌ 错误: 请指定要部署的文件列表（files 参数）"
            auto_rollback = arguments.get("auto_rollback", True)
            run_all = arguments.get("run_all_tests", False)
            return _deployer.deploy(files, auto_rollback, run_all)

        elif action == "pre_check":
            files = arguments.get("files", [])
            if isinstance(files, str):
                import json as _json
                files = _json.loads(files)
            result = _deployer.pre_check(files)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "affected_tests":
            files = arguments.get("files", [])
            if isinstance(files, str):
                import json as _json
                files = _json.loads(files)
            tests = _deployer.affected_tests(files)
            return f"受影响测试 ({len(tests)} 个):\n" + "\n".join(f"  • {t}" for t in tests)

        elif action == "rollback":
            result = _deployer.rollback()
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "report":
            return _deployer.deploy_report()

        elif action == "history":
            limit = int(arguments.get("limit", 10))
            return _deployer.history(limit)

        elif action == "cleanup":
            max_days = int(arguments.get("max_age_days", 7))
            return _deployer.cleanup_backups(max_days)

        else:
            return f"❌ 未知操作: {action}。可用: deploy, pre_check, affected_tests, rollback, report, history, cleanup"

    except Exception as exc:
        return f"❌ 安全部署错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "safe_deploy",
        "description": (
            "安全部署流水线。Evolver 修改代码后自动运行受影响测试，"
            "失败则自动回滚。支持部署历史查看和备份清理。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "deploy", "pre_check", "affected_tests",
                        "rollback", "report", "history", "cleanup",
                    ],
                    "description": (
                        "操作类型：deploy — 一键安全部署；"
                        "pre_check — 仅备份；"
                        "affected_tests — 定位受影响测试；"
                        "rollback — 手动回滚；"
                        "report — 查看最近部署报告；"
                        "history — 部署历史；"
                        "cleanup — 清理过期备份"
                    ),
                    "default": "deploy",
                },
                "files": {
                    "type": "string",
                    "description": (
                        "修改的文件列表 JSON 数组，"
                        "如 '[\"tools/calculator.py\",\"evolver/health_dashboard.py\"]'"
                    ),
                    "default": "[]",
                },
                "auto_rollback": {
                    "type": "boolean",
                    "description": "测试失败时是否自动回滚，默认 True",
                    "default": True,
                },
                "run_all_tests": {
                    "type": "boolean",
                    "description": "是否运行全部测试而不仅是受影响测试",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "历史记录数量限制",
                    "default": 10,
                },
                "max_age_days": {
                    "type": "integer",
                    "description": "清理超过此天数的备份",
                    "default": 7,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

# ── 自测 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 演示: 检查受影响测试
    tests = _deployer.affected_tests(["tools/calculator.py"])
    print(f"Affected tests: {tests}")
    print(_deployer.history())
