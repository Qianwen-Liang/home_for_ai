"""research_worker.py — 离线无人值守研究执行器（独立后台进程）

用户发出研究指令并指定"离线模式运行"后，Agent 1 生成任务包并启动本进程。
本进程独立于会话运行（通过 `start /b` 脱离），按阶段执行研究流水线，
每阶段写检查点（progress.json），完成后写 report.md 并沉淀知识库摘要。

启动方式（后台脱离）：
    start /b python research/research_worker.py --task <task_id>

任务包结构（memory/offline/<task_id>/task_pack.json）：
    {
      "task_id": "...", "theme": "...", "goal": "...", "task_type": "research",
      "phases": ["检索", "精读", "综合"],
      "phase_params": { "检索": {"query": "...", "max_sources": 5} }
    }
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent
OFFLINE_DIR = SANDBOX_DIR / "memory" / "offline"

# 模型与 API 地址以代码为准，.env 仅提供密钥
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"


# ─────────────────────────── LLM 客户端（简化版，独立于 agent1） ──

def llm_chat(messages: list[dict], timeout: int = 180, temperature: float = 0.3, max_tokens: int = 8000) -> str:
    """单次非流式 LLM 调用，返回文本内容。

    max_tokens：输出 token 上限。推理型模型（deepseek-v4-pro）会把思考过程
    计入输出，生成长文本（如论文）时需调大，否则 content 会被截断。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY，后台研究进程无法调用 LLM")

    body = json.dumps({
        "model": DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        DEFAULT_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"LLM 连接失败: {exc}") from exc

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应缺少消息: {data!r}") from exc

    content = message.get("content") if isinstance(message, dict) else None
    reasoning = message.get("reasoning_content", "") if isinstance(message, dict) else ""

    # 推理型模型（如 deepseek-v4-pro）可能在 reasoning_content 里"思考"后
    # 未输出最终答案，导致 content 为空。此时明确抛异常，便于上层重试。
    if not isinstance(content, str) or not content.strip():
        if reasoning and reasoning.strip():
            raise RuntimeError(
                f"LLM 返回空 content（reasoning_content 有 {len(reasoning)} 字符，"
                f"疑似推理模型未输出最终答案）"
            )
        raise RuntimeError("LLM 返回空 content")

    return content.strip()


# ─────────────────────────── 任务包与检查点 ──

def task_dir(task_id: str) -> Path:
    return OFFLINE_DIR / task_id


# 标准化研究工作区目录骨架（借鉴 ReasFlow End-to-End Research Workspace）
WORKSPACE_SKELETON = ["code", "document", "latex", "picture", "references", "scripts"]


def ensure_workspace(task_id: str) -> Path:
    """创建标准化研究工作区目录骨架，返回 task_dir。

    每个研究任务拥有固定的子目录结构，中间产物分门别类落盘，
    用户可随时检查、修改、回滚（配合 checkpoint 工具）。
    """
    base = task_dir(task_id)
    base.mkdir(parents=True, exist_ok=True)
    for sub in WORKSPACE_SKELETON:
        (base / sub).mkdir(parents=True, exist_ok=True)

    readme = base / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# 研究工作区\n\n"
            "标准化目录骨架（借鉴 ReasFlow End-to-End Research Workspace）\n\n"
            "| 目录 | 用途 |\n|------|------|\n"
            "| code/ | 代码实现 |\n"
            "| document/ | 设计文档、分析报告 |\n"
            "| latex/ | LaTeX 手稿 |\n"
            "| picture/ | 图表与可视化 |\n"
            "| references/ | 参考文献、知识卡片 |\n"
            "| scripts/ | 复现与辅助脚本 |\n",
            encoding="utf-8",
        )
    return base


def load_task(task_id: str) -> dict:
    p = task_dir(task_id) / "task_pack.json"
    return json.loads(p.read_text(encoding="utf-8"))


def load_progress(task_id: str) -> dict:
    p = task_dir(task_id) / "progress.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"done_phases": [], "results": {}, "status": "running", "started_at": datetime.now().isoformat()}


def save_progress(task_id: str, progress: dict) -> None:
    p = task_dir(task_id) / "progress.json"
    p.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def log(task_id: str, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"
    with (task_dir(task_id) / "worker.log").open("a", encoding="utf-8") as f:
        f.write(line)


# ─────────────────────────── 阶段实现 ──

def phase_search(task: dict) -> str:
    """检索阶段：联网搜索主题相关资料。"""
    query = task.get("phase_params", {}).get("检索", {}).get("query", task["theme"])
    max_sources = int(task.get("phase_params", {}).get("检索", {}).get("max_sources", 5))
    from tools.web_search import web_search
    return web_search(query, max_sources)


def phase_analyze(task: dict, search_result: str) -> str:
    """精读阶段：LLM 读检索结果，提炼要点。"""
    prompt = (
        f"你是研究分析师。以下是关于主题「{task['theme']}」的检索结果摘要：\n\n"
        f"{search_result[:6000]}\n\n"
        f"请提炼：1) 核心概念与术语；2) 主要观点/方法；3) 不同来源的共识与分歧；"
        f"4) 对目标「{task['goal']}」最有价值的洞察。用结构化列表输出，控制在 800 字内。"
    )
    return llm_chat([{"role": "user", "content": prompt}])


def phase_synthesize(task: dict, analysis: str) -> str:
    """综合阶段：LLM 写结构化初步报告（innovate 类型输出论文级初稿）。"""
    if task.get("task_type") == "innovate":
        prompt = (
            f"你是算法研究员。主题「{task['theme']}」，目标「{task['goal']}」。\n\n"
            f"研究材料（假设/推导/实验）：\n{analysis[:6000]}\n\n"
            f"请写一份论文级初稿，包含：## 摘要、## 相关工作、## 方法、## 实验、"
            f"## 结论与展望。控制在 1500 字内，客观、有依据，突出改进点与实验证据。"
        )
    else:
        prompt = (
            f"你是研究报告撰写者。主题「{task['theme']}」，目标「{task['goal']}」。\n\n"
            f"分析要点：\n{analysis[:6000]}\n\n"
            f"请写一份结构化 Markdown 初步报告，包含：## 摘要、## 核心发现、## 要点列表、"
            f"## 初步结论与下一步。控制在 1500 字内，客观、有依据。"
        )
    return llm_chat([{"role": "user", "content": prompt}])


def _extract_code_block(raw: str) -> str:
    """从 LLM 输出中鲁棒地提取 Python 代码块（多层 fallback，保证非空）。

    处理情况：
    1. ```python / ```py 包裹（大小写不敏感，非贪婪到第一个 ```）
    2. 任意语言标签或无标签的 ``` 代码块
    3. 代码内部含 ``` 的罕见情况（贪婪兜底）
    4. 无代码块标记的纯代码
    """
    import re
    if not raw or not raw.strip():
        return ""
    text = raw.strip()

    # 1) 优先非贪婪匹配 ```python / ```py 到「第一个」```（最常见的单代码块）
    m = re.search(r'```(?:python|py)\s*\n(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 2) 任意语言标签或无标签的代码块（非贪婪）
    m = re.search(r'```[a-zA-Z]*\s*\n(.*?)```', text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 3) 兜底：贪婪匹配（代码内部含 ``` 的罕见情况）
    m = re.search(r'```[a-zA-Z]*\s*\n(.*)```', text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 4) 最后兜底：去掉首尾可能残留的 ``` 标记
    code = re.sub(r'^```[a-zA-Z]*\s*\n?', '', text)
    code = re.sub(r'\n?\s*```$', '', code)
    return code.strip()


def phase_implement(task: dict, synthesis: str) -> str:
    """实现阶段：LLM 基于综合结论生成骨架代码（带重试 + 降级 prompt）。

    推理型模型（deepseek-v4-pro）在复杂 prompt 下可能"思考后未输出最终答案"，
    导致 content 为空。此处做多级降级重试，保证最终能产出代码。
    """
    import time
    prompts = [
        # 第一级：完整 prompt（含综合结论 + 使用说明）
        (
            f"你是资深软件架构师。主题「{task['theme']}」，目标「{task['goal']}」。\n\n"
            f"综合设计结论：\n{synthesis[:5000]}\n\n"
            f"请生成一个**可运行的 Python 骨架代码**，实现核心机制（如子智能体间自主对话循环）。"
            f"要求：1) 用 ```python ... ``` 包裹完整代码；2) 代码内用中文注释说明设计；"
            f"3) 尽量自包含（仅标准库）；4) 附 3-5 行使用说明。"
        ),
        # 第二级：去掉综合结论与使用说明，聚焦生成代码
        (
            f"你是资深软件架构师。请生成一个**可运行的 Python 骨架代码**，实现"
            f"「{task['theme']}」的核心机制。"
            f"要求：1) 用 ```python ... ``` 包裹完整代码；2) 代码内用中文注释；"
            f"3) 仅用标准库。直接输出代码，不要任何解释。"
        ),
        # 第三级：极简 prompt，最大化成功概率
        (
            f"请生成一个可运行的 Python 骨架代码，主题：{task['theme']}。"
            f"用 ```python 包裹完整代码，仅用标准库，直接输出代码。"
        ),
    ]

    last_error = ""
    for i, prompt in enumerate(prompts):
        try:
            raw = llm_chat([{"role": "user", "content": prompt}])
            code = _extract_code_block(raw)
            if code:
                return code
            last_error = "代码块提取为空"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if i < len(prompts) - 1:
            time.sleep(2)

    # 所有尝试失败，返回带原因的占位（不再落空文件）
    return f"# 代码生成失败：{last_error}"


def phase_hypothesize(task: dict, analysis: str) -> str:
    """假设阶段：LLM 基于精读结果提出改进假设（论文级创新）。"""
    prompt = (
        f"你是算法研究员。主题「{task['theme']}」，目标「{task['goal']}」。\n\n"
        f"精读分析：\n{analysis[:5000]}\n\n"
        f"请提出 1-2 个具体的改进假设（新算法变体/机制改进），每个假设说明："
        f"1) 假设内容；2) 改进动机；3) 预期效果；4) 可验证性。"
        f"用结构化列表输出，控制在 500 字内。"
    )
    return llm_chat([{"role": "user", "content": prompt}])


def phase_derive(task: dict, hypothesis: str) -> str:
    """推导阶段：LLM 对假设做数学推导。"""
    prompt = (
        f"你是算法研究员。主题「{task['theme']}」。\n\n"
        f"改进假设：\n{hypothesis[:4000]}\n\n"
        f"请对上述假设做数学推导：1) 更新规则；2) 收敛性分析（若有）；"
        f"3) 复杂度分析；4) 与现有方法的理论对比。"
        f"用 Markdown 输出（数学公式可用文字描述），控制在 800 字内。"
    )
    return llm_chat([{"role": "user", "content": prompt}])


def phase_experiment(task: dict, derivation: str) -> str:
    """实验阶段：LLM 生成 numpy 实验代码并本地执行，对比基线 vs 改进。"""
    import subprocess
    prompt = (
        f"你是算法研究员。主题「{task['theme']}」。\n\n"
        f"推导结论：\n{derivation[:4000]}\n\n"
        f"请生成一个 numpy 实验脚本，对比「基线方法 vs 改进方法」在 toy 函数上的优化效果。"
        f"要求：1) 用 ```python 包裹完整代码；2) 仅用 numpy + 标准库；"
        f"3) 输出最终 loss、迭代次数等可量化指标；4) 可独立运行。"
    )
    raw = llm_chat([{"role": "user", "content": prompt}])
    code = _extract_code_block(raw)
    if not code:
        return f"# 实验代码生成失败：{raw[:200]}"

    # 保存实验代码到 artifacts/
    art_dir = task_dir(task["task_id"]) / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "experiment.py").write_text(code, encoding="utf-8")

    # 本地执行实验代码，捕获输出
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(art_dir / "experiment.py")],
            capture_output=True, text=True, timeout=120,
            cwd=str(SANDBOX_DIR),
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode == 0:
            out = f"✅ 实验执行成功（exit 0）\n\n── 实验输出 ──\n{stdout[:2000]}"
            if stderr:
                out += f"\n── STDERR ──\n{stderr[:500]}"
            return out
        else:
            return (
                f"⚠️ 实验执行返回码 {proc.returncode}\n\n"
                f"── 输出 ──\n{stdout[:1000]}\n"
                f"── 错误 ──\n{stderr[:1000]}\n\n"
                f"实验代码已保存至 artifacts/experiment.py，可手动调试。"
            )
    except Exception as exc:
        return (
            f"⚠️ 实验执行异常: {type(exc).__name__}: {exc}\n"
            f"实验代码已保存至 artifacts/experiment.py。"
        )


# ─────────────────────────── 主流程 ──

def run(task_id: str) -> dict:
    # 建立标准化研究工作区（借鉴 ReasFlow End-to-End Research Workspace）
    ensure_workspace(task_id)
    task = load_task(task_id)
    progress = load_progress(task_id)

    # 防重入：若另一个实例正在运行（status=running 且最近 5 分钟内有更新），本实例退出
    if progress.get("status") == "running":
        updated = progress.get("updated_at", "")
        if updated:
            try:
                last = datetime.fromisoformat(updated)
                if (datetime.now() - last).total_seconds() < 300:
                    log(task_id, "检测到另一实例正在运行，本实例退出（防重入）")
                    return progress
            except ValueError:
                pass

    progress["status"] = "running"
    progress["updated_at"] = datetime.now().isoformat()
    save_progress(task_id, progress)

    log(task_id, f"启动研究任务: {task['theme']}")
    phases = task["phases"]

    for phase in phases:
        if phase in progress["done_phases"]:
            log(task_id, f"阶段 [{phase}] 已完成（检查点恢复，跳过）")
            continue

        log(task_id, f"开始阶段 [{phase}]")
        try:
            if phase == "检索":
                result = phase_search(task)
            elif phase == "精读":
                result = phase_analyze(task, progress["results"].get("检索", ""))
            elif phase == "假设":
                result = phase_hypothesize(task, progress["results"].get("精读", ""))
            elif phase == "推导":
                result = phase_derive(task, progress["results"].get("假设", ""))
            elif phase == "实验":
                result = phase_experiment(task, progress["results"].get("推导", ""))
            elif phase == "综合":
                if task.get("task_type") == "innovate":
                    # 论文级综合：整合假设+推导+实验
                    context = (
                        f"改进假设：\n{progress['results'].get('假设', '')}\n\n"
                        f"数学推导：\n{progress['results'].get('推导', '')}\n\n"
                        f"实验结果：\n{progress['results'].get('实验', '')}"
                    )
                    result = phase_synthesize(task, context)
                else:
                    result = phase_synthesize(task, progress["results"].get("精读", ""))
            elif phase == "实现":
                result = phase_implement(task, progress["results"].get("综合", ""))
                # 代码落盘到 artifacts/
                art_dir = task_dir(task_id) / "artifacts"
                art_dir.mkdir(parents=True, exist_ok=True)
                (art_dir / "agent_loop.py").write_text(result, encoding="utf-8")
                log(task_id, f"阶段 [实现] 代码已写入 artifacts/agent_loop.py")
            else:
                result = f"[阶段 '{phase}' 无对应实现，已跳过]"

            progress["results"][phase] = result
            progress["done_phases"].append(phase)
            progress["updated_at"] = datetime.now().isoformat()
            save_progress(task_id, progress)
            log(task_id, f"阶段 [{phase}] 完成（{len(result)} 字符）")
        except Exception as exc:
            progress["status"] = "failed"
            progress["failed_phase"] = phase
            progress["error"] = f"{type(exc).__name__}: {exc}"
            progress["error_trace"] = traceback.format_exc()[-2000:]
            progress["updated_at"] = datetime.now().isoformat()
            save_progress(task_id, progress)
            log(task_id, f"阶段 [{phase}] 失败: {exc}")
            return progress

    # 全部阶段完成 → 写报告
    report_body = progress["results"].get("综合", "")
    transparency = (
        f"\n\n---\n\n"
        f"## 透明度声明\n\n"
        f"> 本报告由离线研究流水线**自动生成**，信息分三类：\n"
        f"> - ✅ **已验证事实**：直接引自检索结果原文\n"
        f"> - ⚠️ **高置信推断**：基于多来源检索结果的归纳分析\n"
        f"> - ❓ **未验证推断**：LLM 综合生成的结论，未经人工核实\n\n"
        f"> 请在使用前对关键结论进行人工核验。生成时间："
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    report = (
        f"# 离线研究初步报告：{task['theme']}\n\n"
        f"> 目标：{task['goal']}\n"
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{report_body}\n\n---\n\n"
        f"## 附录：检索结果\n\n{progress['results'].get('检索', '')[:2000]}\n"
        f"{transparency}"
    )
    (task_dir(task_id) / "report.md").write_text(report, encoding="utf-8")
    # 同步一份到 document/ 目录（标准化工作区）
    (task_dir(task_id) / "document" / "report.md").write_text(report, encoding="utf-8")

    progress["status"] = "done"
    progress["completed_at"] = datetime.now().isoformat()
    save_progress(task_id, progress)
    log(task_id, "任务完成，report.md 已生成")

    # 沉淀知识库摘要
    try:
        from tools.knowledge_store import _store
        _store.store(
            title=f"离线研究: {task['theme']}",
            content=report_body[:2000],
            category="research",
            tags=["offline", "research", task.get("task_type", "")],
        )
        log(task_id, "知识库摘要已存储")
    except Exception:
        pass

    return progress


if __name__ == "__main__":
    if "--task" in sys.argv:
        task_id = sys.argv[sys.argv.index("--task") + 1]
    elif len(sys.argv) > 1:
        task_id = sys.argv[1]
    else:
        print("用法: python research_worker.py --task <task_id>")
        sys.exit(1)
    run(task_id)
