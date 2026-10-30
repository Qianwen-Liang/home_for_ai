"""
experience_learner — 自适应学习机制（v1.0）
=========================================
受 AutoGPT 的反思机制和 LangChain 的经验回放启发，
为 Agent 1 提供自动化的经验提取和学习能力。

核心功能：
  1. 工具调用成功后自动提取经验并存入 knowledge_store
  2. 工具调用失败后自动记录教训
  3. 定期回顾经验，强化记忆
  4. 相似场景自动推荐历史经验

设计原则：
  - 轻量级：全部使用 Python 标准库
  - 非侵入式：不修改现有工具的调用逻辑
  - 渐进式：从每次交互中一点点学习
"""

from __future__ import annotations

import json
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SANDBOX_DIR = Path(__file__).resolve().parent.parent
LEARNER_FILE = SANDBOX_DIR / "memory" / "experience_learner.json"
KNOWLEDGE_DIR = SANDBOX_DIR / "knowledge"


# ── 错误类型 ──────────────────────────────────────────────


class ExperienceLearnerError(RuntimeError):
    """经验学习器错误。"""


# ── TOOL DEFINITION ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "experience_learner",
        "description": (
            "自适应学习机制。自动从工具调用中提取经验，"
            "成功存入知识库，失败记录教训。支持经验回顾和推荐。"
            "从 AutoGPT 的反思机制学习而来。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "record_success",
                        "record_failure",
                        "review",
                        "recommend",
                        "stats",
                        "recent",
                        "reset",
                    ],
                    "description": (
                        "操作类型："
                        "record_success — 记录一次成功经验；"
                        "record_failure — 记录一次失败教训；"
                        "review — 回顾和总结近期经验；"
                        "recommend — 为当前任务推荐相关经验；"
                        "stats — 查看学习统计；"
                        "recent — 查看最近的经验记录；"
                        "reset — 重置学习数据。"
                    ),
                },
                "tool_name": {
                    "type": "string",
                    "description": "工具名称（success/failure 操作）",
                    "default": "",
                },
                "task": {
                    "type": "string",
                    "description": "任务描述（success/failure/recommend 操作）",
                    "default": "",
                },
                "result": {
                    "type": "string",
                    "description": "执行结果（success/failure 操作）",
                    "default": "",
                },
                "lesson": {
                    "type": "string",
                    "description": "经验教训总结（success/failure 操作）",
                    "default": "",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量限制",
                    "default": 10,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


# ── 经验学习引擎 ──────────────────────────────────────────


class ExperienceLearner:
    """
    自适应学习引擎。
    
    自动从每次工具调用中学习，不断积累经验。
    """

    def __init__(self) -> None:
        self._experiences: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """从文件加载经验数据。"""
        if LEARNER_FILE.is_file():
            try:
                self._experiences = json.loads(LEARNER_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._experiences = []

    def _save(self) -> None:
        """保存经验数据到文件。"""
        LEARNER_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEARNER_FILE.write_text(
            json.dumps(self._experiences, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _generate_id(self) -> str:
        return f"EXP-{int(time.time())}"

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词（v2.0 使用 jieba 中文分词）。"""
        if not text:
            return []
        
        # 尝试使用 jieba 做中文分词
        try:
            import jieba
            # 添加自定义词典
            for word in ['智能体', '大语言模型', '工作流', '语义搜索', 
                         '向量检索', '自适应', '知识库', '任务追踪',
                         '参数验证', '错误恢复', '思维切换']:
                jieba.add_word(word)
            words = list(jieba.cut(text.lower()))
        except ImportError:
            # 回退：按空格和常见分隔符拆分
            import re
            words = re.split(r'[\s,，。；;：:！!？?()（）\[\]【】{}""''、/\\|_\-]+', text.lower())
        
        # 过滤短词和常见停用词
        stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
            '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些',
            '这个', '那个', '什么', '怎么', '为什么', '因为', '所以', '但是',
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
            'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
            'this', 'that', 'these', 'those', 'it', 'its', 'and', 'or', 'but',
            'not', 'no', 'so', 'if', 'then', 'than', 'too', 'very', 'just', 'about',
        }
        
        # 使用 numpy 做词频统计（如果可用）
        result = [w for w in words if len(w) >= 2 and w not in stop_words]
        
        try:
            import numpy as np
            from collections import Counter
            # 按词频排序，保留高频词
            if result:
                counter = Counter(result)
                # 保留出现次数 >= 平均值的词
                counts = np.array(list(counter.values()))
                mean_count = float(np.mean(counts))
                result = [w for w in counter if counter[w] >= mean_count * 0.5]
        except ImportError:
            pass
        
        return result[:20]  # 最多返回20个关键词

    # ── 核心接口 ────────────────────────────────────────

    def record_success(
        self,
        tool_name: str = "",
        task: str = "",
        result: str = "",
        lesson: str = "",
    ) -> str:
        """记录一次成功经验，并自动存入知识库。"""
        now = self._now()
        exp_id = self._generate_id()

        # 构建经验条目
        entry = {
            "id": exp_id,
            "type": "success",
            "tool": tool_name,
            "task": task,
            "result": result[:500] if result else "",
            "lesson": lesson,
            "keywords": self._extract_keywords(f"{tool_name} {task} {lesson}"),
            "timestamp": now,
            "stored_to_knowledge": False,
        }

        self._experiences.append(entry)
        self._save()

        # 自动存入 knowledge_store（如果 lesson 足够详细）
        knowledge_stored = False
        if len(lesson) >= 20:
            try:
                # 尝试直接写入 knowledge_store 的 JSON 文件
                knowledge_file = KNOWLEDGE_DIR / "knowledge_store.json"
                if knowledge_file.is_file():
                    kdata = json.loads(knowledge_file.read_text(encoding="utf-8"))
                else:
                    kdata = {}

                kid = f"K{int(time.time())}"
                kdata[kid] = {
                    "id": kid,
                    "title": f"[经验] {tool_name}: {task[:60]}" if task else f"[经验] {tool_name} 成功",
                    "content": f"## 成功经验\n\n工具: {tool_name}\n任务: {task}\n结果: {result[:200]}\n经验: {lesson}",
                    "category": "experience",
                    "tags": [tool_name] + entry["keywords"][:5],
                    "created_at": time.time(),
                    "updated_at": time.time(),
                    "version": 1,
                }
                KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
                knowledge_file.write_text(
                    json.dumps(kdata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                knowledge_stored = True
                entry["stored_to_knowledge"] = True
                self._save()
            except Exception:
                pass  # 知识库存储失败不影响主流程

        result = (
            f"✅ 成功经验已记录 [{exp_id}]\n"
            f"   工具: {tool_name} | 任务: {task[:60] if task else '无'}\n"
        )
        if knowledge_stored:
            result += f"   📚 已自动存入知识库\n"
        if lesson:
            result += f"   💡 经验: {lesson[:100]}"

        return result

    def record_failure(
        self,
        tool_name: str = "",
        task: str = "",
        result: str = "",
        lesson: str = "",
    ) -> str:
        """记录一次失败教训。"""
        now = self._now()
        exp_id = self._generate_id()

        entry = {
            "id": exp_id,
            "type": "failure",
            "tool": tool_name,
            "task": task,
            "result": result[:500] if result else "",
            "lesson": lesson,
            "keywords": self._extract_keywords(f"{tool_name} {task} {lesson} 失败 错误"),
            "timestamp": now,
            "stored_to_knowledge": False,
        }

        self._experiences.append(entry)
        self._save()

        # 失败教训自动存入知识库
        knowledge_stored = False
        if len(lesson) >= 20:
            try:
                knowledge_file = KNOWLEDGE_DIR / "knowledge_store.json"
                if knowledge_file.is_file():
                    kdata = json.loads(knowledge_file.read_text(encoding="utf-8"))
                else:
                    kdata = {}

                kid = f"K{int(time.time())}"
                kdata[kid] = {
                    "id": kid,
                    "title": f"[教训] {tool_name}: {task[:60]}" if task else f"[教训] {tool_name} 失败",
                    "content": f"## 失败教训\n\n工具: {tool_name}\n任务: {task}\n错误: {result[:200]}\n教训: {lesson}\n\n避免重复犯同样的错误。",
                    "category": "lesson",
                    "tags": [tool_name, "教训"] + entry["keywords"][:3],
                    "created_at": time.time(),
                    "updated_at": time.time(),
                    "version": 1,
                }
                KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
                knowledge_file.write_text(
                    json.dumps(kdata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                knowledge_stored = True
                entry["stored_to_knowledge"] = True
                self._save()
            except Exception:
                pass

        result = (
            f"⚠️ 失败教训已记录 [{exp_id}]\n"
            f"   工具: {tool_name} | 任务: {task[:60] if task else '无'}\n"
        )
        if knowledge_stored:
            result += f"   📚 已自动存入知识库（避免重复犯错）\n"
        if lesson:
            result += f"   💡 教训: {lesson[:100]}"

        return result

    def review(self, max_results: int = 10) -> str:
        """回顾和总结近期经验。"""
        if not self._experiences:
            return "暂无经验记录。开始使用工具后会自动积累经验。"

        recent = self._experiences[-max_results:]

        # 统计
        total = len(self._experiences)
        successes = sum(1 for e in self._experiences if e["type"] == "success")
        failures = sum(1 for e in self._experiences if e["type"] == "failure")
        success_rate = successes * 100 / total if total else 0

        # 常用工具
        tool_counts = Counter(e["tool"] for e in self._experiences if e["tool"])

        lines = [
            f"📊 经验回顾",
            f"{'='*50}",
            f"总经验: {total} | ✅ 成功: {successes} | ⚠️ 教训: {failures}",
            f"成功率: {success_rate:.1f}%",
            f"",
            f"常用工具:",
        ]

        for tool, count in tool_counts.most_common(8):
            lines.append(f"  • {tool}: {count} 次")

        lines.append(f"\n最近 {len(recent)} 条记录:\n")

        for entry in reversed(recent):
            icon = "✅" if entry["type"] == "success" else "⚠️"
            tool_info = f"[{entry['tool']}]" if entry["tool"] else ""
            lines.append(
                f"  {icon} {entry['id']} {tool_info} "
                f"{entry['task'][:60] if entry['task'] else '无任务'}"
            )
            if entry["lesson"]:
                lines.append(f"       {entry['lesson'][:80]}")

        return "\n".join(lines)

    def recommend(self, task: str = "", max_results: int = 5) -> str:
        """为当前任务推荐相关经验。"""
        if not self._experiences:
            return "暂无经验可推荐。"

        if not task.strip():
            # 如果没有任务描述，返回最近的经验
            recent = self._experiences[-max_results:]
            lines = [f"💡 最近 {len(recent)} 条经验（供参考）:\n"]
            for entry in reversed(recent):
                icon = "✅" if entry["type"] == "success" else "⚠️"
                lines.append(f"  {icon} [{entry['tool']}] {entry['task'][:60]}")
                if entry["lesson"]:
                    lines.append(f"      {entry['lesson'][:80]}")
            return "\n".join(lines)

        # 关键词匹配推荐
        task_keywords = set(self._extract_keywords(task))
        if not task_keywords:
            return "无法从任务描述中提取关键词。"

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._experiences:
            entry_keywords = set(entry.get("keywords", []))
            if entry_keywords:
                overlap = len(task_keywords & entry_keywords)
                if overlap > 0:
                    score = overlap / len(task_keywords)  # 覆盖率
                    scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])

        if not scored:
            return f"未找到与当前任务相关的历史经验。\n任务关键词: {', '.join(list(task_keywords)[:8])}"

        lines = [f"💡 为当前任务推荐 {len(scored)} 条相关经验:\n"]
        for score, entry in scored[:max_results]:
            icon = "✅" if entry["type"] == "success" else "⚠️"
            relevance = f"相关度: {score:.0%}"
            lines.append(
                f"  {icon} [{entry['tool']}] ({relevance})"
            )
            lines.append(f"      {entry['task'][:80] if entry['task'] else '无描述'}")
            if entry["lesson"]:
                lines.append(f"      💡 {entry['lesson'][:100]}")

        return "\n".join(lines)

    def recent(self, max_results: int = 10) -> str:
        """查看最近的经验记录。"""
        if not self._experiences:
            return "暂无经验记录。"

        recent = self._experiences[-max_results:]
        lines = [f"📋 最近 {len(recent)} 条经验记录:\n"]
        for entry in reversed(recent):
            icon = "✅" if entry["type"] == "success" else "⚠️"
            stored = " 📚" if entry.get("stored_to_knowledge") else ""
            lines.append(
                f"  {icon} [{entry['id']}]{stored} "
                f"[{entry['tool']}] {entry['timestamp']}"
            )
            lines.append(f"      任务: {entry['task'][:80] if entry['task'] else '无'}")
            if entry["lesson"]:
                lines.append(f"      经验: {entry['lesson'][:100]}")
            lines.append("")

        return "\n".join(lines)

    def stats(self) -> str:
        """查看学习统计。"""
        if not self._experiences:
            return "暂无学习数据。开始使用工具后会自动积累。"

        total = len(self._experiences)
        successes = sum(1 for e in self._experiences if e["type"] == "success")
        failures = sum(1 for e in self._experiences if e["type"] == "failure")
        stored = sum(1 for e in self._experiences if e.get("stored_to_knowledge"))

        # 按工具统计
        tool_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"success": 0, "failure": 0}
        )
        for entry in self._experiences:
            tool = entry["tool"] or "unknown"
            tool_stats[tool][entry["type"]] += 1

        lines = [
            f"📊 学习统计\n{'='*35}",
            f"总经验: {total}",
            f"✅ 成功: {successes} ({successes*100//total if total else 0}%)",
            f"⚠️ 教训: {failures} ({failures*100//total if total else 0}%)",
            f"📚 已存入知识库: {stored}",
        ]

        if tool_stats:
            lines.append(f"\n按工具统计:")
            for tool in sorted(tool_stats.keys()):
                s = tool_stats[tool]["success"]
                f_cnt = tool_stats[tool]["failure"]
                rate = s * 100 // (s + f_cnt) if (s + f_cnt) > 0 else 0
                lines.append(f"  • {tool}: ✅{s} ⚠️{f_cnt} (成功率{rate}%)")

        return "\n".join(lines)

    def reset(self) -> str:
        """重置学习数据。"""
        self._experiences = []
        self._save()
        return "🔄 学习数据已重置。"


# ── 全局实例 ──────────────────────────────────────────────

_learner = ExperienceLearner()


def execute_experience_learner_tool(arguments: dict[str, Any]) -> str:
    """执行 experience_learner 工具。"""
    action = arguments.get("action", "")

    try:
        if action == "record_success":
            return _learner.record_success(
                tool_name=arguments.get("tool_name", ""),
                task=arguments.get("task", ""),
                result=arguments.get("result", ""),
                lesson=arguments.get("lesson", ""),
            )

        elif action == "record_failure":
            return _learner.record_failure(
                tool_name=arguments.get("tool_name", ""),
                task=arguments.get("task", ""),
                result=arguments.get("result", ""),
                lesson=arguments.get("lesson", ""),
            )

        elif action == "review":
            return _learner.review(
                max_results=int(arguments.get("max_results", 10))
            )

        elif action == "recommend":
            return _learner.recommend(
                task=arguments.get("task", ""),
                max_results=int(arguments.get("max_results", 5)),
            )

        elif action == "recent":
            return _learner.recent(
                max_results=int(arguments.get("max_results", 10))
            )

        elif action == "stats":
            return _learner.stats()

        elif action == "reset":
            return _learner.reset()

        else:
            return f"未知操作: {action}"

    except ExperienceLearnerError as exc:
        return f"经验学习器错误: {exc}"
