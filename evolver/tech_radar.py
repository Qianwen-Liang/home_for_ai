"""
技术雷达扫描器 — TechRadar (E-B1)

环境感知子层 C：技术生态感知。
定期扫描 Python / AI Agent 生态关键动态，生成结构化技术雷达简报。

参考：Dependabot（自动依赖检测）的设计理念，但面向"技术趋势"而非仅"安全补丁"。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Optional

# ── 数据目录 ─────────────────────────────────────────────
RADAR_DIR = Path(__file__).resolve().parent.parent / "memory" / "tech_radar"
RADAR_DIR.mkdir(parents=True, exist_ok=True)


class RadarCategory(str, Enum):
    """扫描类别"""
    SECURITY   = "security"    # 安全公告 / CVE
    FRAMEWORK  = "framework"   # AI Agent 框架（LangChain, AutoGen, CrewAI, LangGraph…）
    TOOLCHAIN  = "toolchain"   # 开发工具链（pytest, mypy, ruff, black…）
    TREND      = "trend"       # 行业趋势 / 论文 / 最佳实践


class ImpactLevel(str, Enum):
    """影响等级"""
    CRITICAL = "critical"      # 必须立即响应（如严重安全漏洞）
    HIGH     = "high"          # 强烈建议跟进
    MEDIUM   = "medium"        # 值得关注
    LOW      = "low"           # 仅供参考


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class RadarEntry:
    """单条雷达条目"""
    title: str
    category: RadarCategory
    impact: ImpactLevel
    summary: str                          # 1-3 句摘要
    source_url: str                       # 来源链接
    recommendation: str                   # 对 agent1 的建议行动
    keywords: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["impact"] = self.impact.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RadarEntry":
        d["category"] = RadarCategory(d["category"])
        d["impact"] = ImpactLevel(d["impact"])
        return cls(**d)


@dataclass
class RadarBriefing:
    """一次扫描生成的简报"""
    briefing_id: str
    scan_time: str
    categories_covered: List[str]
    entries: List[RadarEntry]
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    executive_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "briefing_id": self.briefing_id,
            "scan_time": self.scan_time,
            "categories_covered": self.categories_covered,
            "entries": [e.to_dict() for e in self.entries],
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "executive_summary": self.executive_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RadarBriefing":
        entries = [RadarEntry.from_dict(e) for e in d["entries"]]
        return cls(
            briefing_id=d["briefing_id"],
            scan_time=d["scan_time"],
            categories_covered=d["categories_covered"],
            entries=entries,
            critical_count=d["critical_count"],
            high_count=d["high_count"],
            medium_count=d["medium_count"],
            low_count=d["low_count"],
            executive_summary=d["executive_summary"],
        )


# ── 影响评估规则 ──────────────────────────────────────────

def _assess_impact(title: str, summary: str, category: RadarCategory) -> ImpactLevel:
    """
    基于启发式规则评估影响等级。
    
    规则（按优先级）：
    1. 关键词 "critical" / "CVSS 9" / "remote code execution" → CRITICAL
    2. 安全类 + 涉及 Python 核心 / pickle / tarfile → HIGH
    3. 框架重大版本（如 LangChain 1.0）→ MEDIUM
    4. 工具链次要更新 → LOW
    """
    t = (title + " " + summary).lower()

    critical_keywords = ["critical", "cvss 9.", "remote code execution", "rce", "arbitrary code"]
    high_keywords = ["cve-", "path traversal", "pickle", "deserialization", "vulnerability",
                     "security fix", "python", "major release", "breaking change"]
    medium_keywords = ["new version", "release", "update", "deprecated", "langchain",
                       "autogen", "crewai", "langgraph"]
    
    if any(k in t for k in critical_keywords):
        return ImpactLevel.CRITICAL
    if category == RadarCategory.SECURITY and any(k in t for k in high_keywords):
        return ImpactLevel.HIGH
    if category == RadarCategory.FRAMEWORK and any(k in t for k in high_keywords):
        return ImpactLevel.HIGH
    if any(k in t for k in medium_keywords):
        return ImpactLevel.MEDIUM
    return ImpactLevel.LOW


# ── 主类 ──────────────────────────────────────────────────

class TechRadar:
    """
    技术雷达扫描器。
    
    用法：
        radar = TechRadar()
        briefing = radar.generate_briefing(search_results={
            RadarCategory.SECURITY: [...],
            ...
        })
        radar.archive(briefing)
    """

    ARCHIVE_FILE = RADAR_DIR / "briefings.json"
    MAX_ARCHIVE_ENTRIES = 50

    def __init__(self):
        self._briefings: List[RadarBriefing] = []
        self._load_archive()

    # ── 静态：条目构造 ──────────────────────────────────

    @staticmethod
    def make_entry(
        title: str,
        category: RadarCategory,
        summary: str,
        source_url: str,
        recommendation: str = "",
        keywords: Optional[List[str]] = None,
    ) -> RadarEntry:
        """创建一条雷达条目，自动评估影响等级。"""
        impact = _assess_impact(title, summary, category)
        if not recommendation:
            recommendation = TechRadar._default_recommendation(impact, category)
        return RadarEntry(
            title=title,
            category=category,
            impact=impact,
            summary=summary,
            source_url=source_url,
            recommendation=recommendation,
            keywords=keywords or [],
        )

    @staticmethod
    def _default_recommendation(impact: ImpactLevel, category: RadarCategory) -> str:
        if impact == ImpactLevel.CRITICAL:
            return "立即评估影响，若涉及 agent1 依赖则当日升级。"
        if impact == ImpactLevel.HIGH:
            return "本周内完成影响评估，制定升级/修复计划。"
        if category == RadarCategory.SECURITY:
            return "纳入安全监控，下次维护窗口处理。"
        if category == RadarCategory.FRAMEWORK:
            return "关注功能变更，评估是否引入新能力到 agent1。"
        if category == RadarCategory.TREND:
            return "归档为背景知识，月度回顾时参考。"
        return "记录即可，无需立即行动。"

    # ── 简报生成 ────────────────────────────────────────

    def generate_briefing(
        self,
        search_results: dict,
        categories_covered: Optional[List[str]] = None,
    ) -> RadarBriefing:
        """
        基于搜索原始结果生成结构化简报。

        Args:
            search_results: {RadarCategory: [{"title": ..., "summary": ..., "url": ...}, ...]}
            categories_covered: 本次覆盖的类别名称列表

        Returns:
            RadarBriefing 对象
        """
        entries: List[RadarEntry] = []
        for category, results in search_results.items():
            if isinstance(category, str):
                category = RadarCategory(category)
            for r in results:
                entry = self.make_entry(
                    title=r.get("title", ""),
                    category=category,
                    summary=r.get("summary", ""),
                    source_url=r.get("url", r.get("source_url", "")),
                    recommendation=r.get("recommendation", ""),
                    keywords=r.get("keywords", []),
                )
                entries.append(entry)

        # 统计
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for e in entries:
            counts[e.impact.value] += 1

        # 执行摘要
        exec_parts = []
        if counts["critical"]:
            exec_parts.append(f"🔴 {counts['critical']} 条 CRITICAL 警报需立即处理")
        if counts["high"]:
            exec_parts.append(f"🟠 {counts['high']} 条 HIGH 级别建议本周跟进")
        if counts["medium"]:
            exec_parts.append(f"🟡 {counts['medium']} 条 MEDIUM 值得关注")
        if counts["low"]:
            exec_parts.append(f"🟢 {counts['low']} 条 LOW 仅供参考")

        briefing_id = f"radar-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        return RadarBriefing(
            briefing_id=briefing_id,
            scan_time=datetime.now().isoformat(),
            categories_covered=categories_covered
            or [c.value for c in search_results],
            entries=entries,
            critical_count=counts["critical"],
            high_count=counts["high"],
            medium_count=counts["medium"],
            low_count=counts["low"],
            executive_summary="；".join(exec_parts) if exec_parts else "本次扫描未发现需关注事项。",
        )

    # ── 归档 ────────────────────────────────────────────

    def archive(self, briefing: RadarBriefing) -> str:
        """归档简报到磁盘，返回简报 ID。"""
        self._briefings.append(briefing)
        # 限制条目数
        if len(self._briefings) > self.MAX_ARCHIVE_ENTRIES:
            self._briefings = self._briefings[-self.MAX_ARCHIVE_ENTRIES:]
        self._save_archive()
        return briefing.briefing_id

    # ── 查询 ────────────────────────────────────────────

    def latest(self) -> Optional[RadarBriefing]:
        """获取最新简报。"""
        return self._briefings[-1] if self._briefings else None

    def list_recent(self, n: int = 5) -> List[RadarBriefing]:
        """列出最近 n 份简报。"""
        return self._briefings[-n:]

    def entries_by_impact(self, level: ImpactLevel) -> List[RadarEntry]:
        """获取指定影响等级的所有条目（从最新简报）。"""
        latest = self.latest()
        if not latest:
            return []
        return [e for e in latest.entries if e.impact == level]

    def entries_by_category(self, category: RadarCategory) -> List[RadarEntry]:
        """获取指定类别的所有条目（从最新简报）。"""
        latest = self.latest()
        if not latest:
            return []
        return [e for e in latest.entries if e.category == category]

    # ── 格式化输出 ──────────────────────────────────────

    def format_briefing(self, briefing: Optional[RadarBriefing] = None) -> str:
        """生成 Markdown 格式的简报。"""
        b = briefing or self.latest()
        if not b:
            return "⚠️ 暂无技术雷达简报。请先执行扫描。"

        lines = [
            f"# 📡 技术雷达简报",
            f"**简报 ID**：{b.briefing_id}",
            f"**扫描时间**：{b.scan_time}",
            f"**覆盖类别**：{', '.join(b.categories_covered)}",
            f"",
            f"## 执行摘要",
            f"{b.executive_summary}",
            f"",
            f"| 等级 | 数量 |",
            f"|------|------|",
            f"| 🔴 CRITICAL | {b.critical_count} |",
            f"| 🟠 HIGH     | {b.high_count} |",
            f"| 🟡 MEDIUM   | {b.medium_count} |",
            f"| 🟢 LOW      | {b.low_count} |",
            f"",
        ]

        # 按等级分组
        for level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM, ImpactLevel.LOW]:
            level_entries = [e for e in b.entries if e.impact == level]
            if not level_entries:
                continue
            lines.append(f"## {level.value.upper()} 条目")
            lines.append("")
            for e in level_entries:
                lines.append(f"### {e.title}")
                lines.append(f"- **类别**：{e.category.value}")
                lines.append(f"- **摘要**：{e.summary}")
                lines.append(f"- **建议**：{e.recommendation}")
                lines.append(f"- **来源**：{e.source_url}")
                if e.keywords:
                    lines.append(f"- **标签**：{', '.join(e.keywords)}")
                lines.append("")

        lines.append("---")
        lines.append(f"*简报由 TechRadar 自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        return "\n".join(lines)

    # ── 持久化 ──────────────────────────────────────────

    def _load_archive(self):
        if self.ARCHIVE_FILE.exists():
            try:
                data = json.loads(self.ARCHIVE_FILE.read_text(encoding="utf-8"))
                self._briefings = [RadarBriefing.from_dict(d) for d in data]
            except (json.JSONDecodeError, KeyError):
                self._briefings = []

    def _save_archive(self):
        data = [b.to_dict() for b in self._briefings]
        self.ARCHIVE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 版本对比工具 ────────────────────────────────────

    @staticmethod
    def compare_versions(current: str, latest: str) -> str:
        """
        简易版本对比。如果 latest > current，建议升级。
        
        示例：
            compare_versions("3.10", "3.12") → "建议从 3.10 升级到 3.12"
        """
        try:
            cur_parts = [int(x) for x in current.replace("v", "").split(".")]
            lat_parts = [int(x) for x in latest.replace("v", "").split(".")]
            # 补齐长度
            while len(cur_parts) < len(lat_parts):
                cur_parts.append(0)
            while len(lat_parts) < len(cur_parts):
                lat_parts.append(0)

            if lat_parts > cur_parts:
                return f"📈 建议从 {current} 升级到 {latest}（已有新版本）"
            elif lat_parts < cur_parts:
                return f"✅ 当前版本 {current} 已是最新（比 {latest} 新）"
            else:
                return f"✅ 当前版本 {current} 已是最新"
        except (ValueError, AttributeError):
            return f"⚠️ 无法比较版本：current={current}, latest={latest}"


# ── 便捷函数 ──────────────────────────────────────────────

def run_tech_radar(search_results: dict) -> RadarBriefing:
    """
    便捷入口：基于搜索原始结果生成并归档简报。
    """
    radar = TechRadar()
    briefing = radar.generate_briefing(search_results)
    radar.archive(briefing)
    return briefing


# ── 全局单例 ───────────────────────────────────────────────

_radar = TechRadar()


# ── 工具函数 ──────────────────────────────────────────────

def execute_tech_radar_tool(arguments: dict) -> str:
    """技术雷达工具入口。"""
    action = arguments.get("action", "latest")

    try:
        if action == "latest":
            briefing = _radar.latest()
            if not briefing:
                return "⚠️ 暂无技术雷达简报。请先使用 web_search 搜索最新技术动态，然后调用 action='scan' 录入。"
            return _radar.format_briefing(briefing)

        elif action == "scan":
            # scan 需要 search_results 参数（来自 web_search 的结果）
            search_results = arguments.get("search_results")
            if not search_results:
                return (
                    "⚠️ 请提供 search_results 参数。\n"
                    "用法: 先用 web_search 搜索各领域最新动态，将结果传给 tech_radar scan。\n"
                    "search_results 格式: {\"security\": [{...}], \"framework\": [{...}], ...}"
                )
            if isinstance(search_results, str):
                import json as _json
                search_results = _json.loads(search_results)
            categories = arguments.get("categories")
            if isinstance(categories, str):
                import json as _json
                categories = _json.loads(categories)
            briefing = _radar.generate_briefing(search_results, categories)
            _radar.archive(briefing)
            return f"✅ 简报已生成并归档。\n{_radar.format_briefing(briefing)}"

        elif action == "list":
            limit = int(arguments.get("limit", 5))
            briefings = _radar.list_recent(limit)
            if not briefings:
                return "暂无历史简报。"
            lines = [f"📡 最近 {len(briefings)} 份技术雷达简报:"]
            for b in briefings:
                lines.append(
                    f"  • {b.briefing_id} ({b.scan_time[:10]}) — "
                    f"🔴{b.critical_count} 🟠{b.high_count} 🟡{b.medium_count} 🟢{b.low_count}"
                )
            return "\n".join(lines)

        elif action == "compare_versions":
            current = arguments.get("current", "")
            latest = arguments.get("latest", "")
            if not current or not latest:
                return "请提供 current 和 latest 两个版本号参数。"
            return TechRadar.compare_versions(current, latest)

        elif action == "format":
            briefing_id = arguments.get("briefing_id", "")
            if briefing_id:
                for b in _radar._briefings:
                    if b.briefing_id == briefing_id:
                        return _radar.format_briefing(b)
                return f"未找到简报: {briefing_id}"
            return _radar.format_briefing()

        else:
            return f"未知操作: {action}。可用: latest, scan, list, compare_versions, format"

    except Exception as exc:
        return f"技术雷达错误: {exc}"


# ── TOOL DEFINITION ────────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "tech_radar",
        "description": (
            "技术雷达扫描器。扫描 Python/AI Agent 生态最新动态（安全公告、框架更新、工具链变更），"
            "生成结构化雷达简报。支持与 web_search 配合使用：先用 web_search 搜索，然后将结果传入 scan。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["latest", "scan", "list", "compare_versions", "format"],
                    "description": (
                        "操作类型：latest — 查看最新简报；"
                        "scan — 基于搜索原始结果生成简报；"
                        "list — 列出历史简报；"
                        "compare_versions — 版本对比；"
                        "format — 格式化指定简报"
                    ),
                    "default": "latest",
                },
                "search_results": {
                    "type": "string",
                    "description": (
                        "搜索原始结果 JSON，格式 {\"security\": [{title, summary, url}, ...], "
                        "\"framework\": [...], \"toolchain\": [...], \"trend\": [...]}"
                    ),
                    "default": "",
                },
                "categories": {
                    "type": "string",
                    "description": "覆盖的类别列表 JSON，如 [\"security\", \"framework\"]",
                    "default": "",
                },
                "current": {
                    "type": "string",
                    "description": "当前版本号（用于 compare_versions）",
                    "default": "",
                },
                "latest": {
                    "type": "string",
                    "description": "最新版本号（用于 compare_versions）",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "历史简报数量限制",
                    "default": 5,
                },
                "briefing_id": {
                    "type": "string",
                    "description": "简报 ID（用于 format）",
                    "default": "",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}
