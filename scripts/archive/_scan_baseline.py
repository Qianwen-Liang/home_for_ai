# -*- coding: utf-8 -*-
"""根目录全量扫描 —— 生成“初始标准状态”档案（日期 20260819）"""
import os
import json
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "初始标准状态_20260819.md"

EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".backups", "node_modules"}

def fmt_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024

# ---- 遍历收集 ----
files = []          # (path, size, mtime)
dirs = []
ext_stats = defaultdict(lambda: [0, 0])   # ext -> [count, size]
subdir_stats = defaultdict(lambda: [0, 0, 0])  # subdir -> [files, dirs, size]

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for d in dirnames:
        dirs.append(os.path.join(dirpath, d))
    for f in filenames:
        fp = os.path.join(dirpath, f)
        try:
            sz = os.path.getsize(fp)
        except OSError:
            sz = 0
        mt = os.path.getmtime(fp)
        files.append((fp, sz, mt))
        ext = os.path.splitext(f)[1].lower() or "(无扩展名)"
        ext_stats[ext][0] += 1
        ext_stats[ext][1] += sz
        # 子目录归集
        rel = os.path.relpath(dirpath, ROOT)
        top = rel.split(os.sep)[0] if rel != "." else "."
        subdir_stats[top][0] += 1
        subdir_stats[top][1] += 0
        subdir_stats[top][2] += sz

# 目录计数单独统计
for d in dirs:
    rel = os.path.relpath(d, ROOT)
    top = rel.split(os.sep)[0] if rel != "." else "."
    subdir_stats[top][1] += 1

total_size = sum(s for _, s, _ in files)
sizes = sorted(s for _, s, _ in files)
median = sizes[len(sizes) // 2] if sizes else 0

# ---- 顶层条目 ----
top_entries = []
for entry in sorted(ROOT.iterdir(), key=lambda p: p.name.lower()):
    if entry.name in EXCLUDE_DIRS:
        continue
    if entry.is_dir():
        n_files = subdir_stats.get(entry.name, [0, 0, 0])[0]
        n_dirs = subdir_stats.get(entry.name, [0, 0, 0])[1]
        sz = subdir_stats.get(entry.name, [0, 0, 0])[2]
        top_entries.append((entry.name, "dir", sz, n_files, n_dirs))
    else:
        try:
            sz = entry.stat().st_size
        except OSError:
            sz = 0
        top_entries.append((entry.name, "file", sz, 1, 0))

# ---- 生成报告 ----
lines = []
lines.append("# 初始标准状态（根目录全量扫描）")
lines.append("")
lines.append("- **档案名称**：初始标准状态")
lines.append("- **档案日期**：20260819")
lines.append("- **扫描生成时间**：" + time.strftime("%Y-%m-%d %H:%M:%S"))
lines.append("- **扫描范围**：" + str(ROOT))
lines.append("- **扫描方式**：Python 3.11 递归全量遍历（排除 .git / __pycache__ / .pytest_cache / .backups / node_modules）")
lines.append("")
lines.append("## 一、总体概览")
lines.append("")
lines.append("| 指标 | 数值 |")
lines.append("| --- | --- |")
lines.append(f"| 文件总数 | {len(files)} 个 |")
lines.append(f"| 目录总数 | {len(dirs)} 个 |")
lines.append(f"| 总占用 | {fmt_size(total_size)} |")
lines.append(f"| 平均文件大小 | {fmt_size(total_size/len(files)) if files else '0 B'} |")
lines.append(f"| 中位数大小 | {fmt_size(median)} |")
lines.append(f"| 文件类型数 | {len(ext_stats)} 种 |")
lines.append("")
lines.append("## 二、顶层目录 / 文件清单")
lines.append("")
lines.append("| 名称 | 类型 | 大小 | 文件数 | 子目录数 |")
lines.append("| --- | --- | --- | --- | --- |")
for name, typ, sz, nf, nd in sorted(top_entries, key=lambda x: (-(x[1] == "dir"), x[2]), reverse=False):
    pass
# 先目录后文件、各自按大小降序
dirs_sorted = sorted([e for e in top_entries if e[1] == "dir"], key=lambda x: -x[2])
files_sorted = sorted([e for e in top_entries if e[1] == "file"], key=lambda x: -x[2])
for name, typ, sz, nf, nd in dirs_sorted:
    lines.append(f"| `{name}/` | 目录 | {fmt_size(sz)} | {nf} | {nd} |")
for name, typ, sz, nf, nd in files_sorted:
    lines.append(f"| `{name}` | 文件 | {fmt_size(sz)} | {nf} | {nd} |")
lines.append("")
lines.append("## 三、文件类型分布")
lines.append("")
lines.append("| 扩展名 | 数量 | 大小 |")
lines.append("| --- | --- | --- |")
for ext, (cnt, sz) in sorted(ext_stats.items(), key=lambda x: -x[1][1]):
    lines.append(f"| `{ext}` | {cnt} | {fmt_size(sz)} |")
lines.append("")
lines.append("## 四、最大文件 Top 30")
lines.append("")
lines.append("| 文件 | 大小 |")
lines.append("| --- | --- |")
for fp, sz, _ in sorted(files, key=lambda x: -x[1])[:30]:
    rel = os.path.relpath(fp, ROOT).replace(os.sep, "/")
    lines.append(f"| `{rel}` | {fmt_size(sz)} |")
lines.append("")
lines.append("## 五、最近修改文件 Top 30")
lines.append("")
lines.append("| 文件 | 修改时间 | 大小 |")
lines.append("| --- | --- | --- |")
for fp, sz, mt in sorted(files, key=lambda x: -x[2])[:30]:
    rel = os.path.relpath(fp, ROOT).replace(os.sep, "/")
    lines.append(f"| `{rel}` | {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))} | {fmt_size(sz)} |")
lines.append("")
lines.append("## 六、大小分布")
lines.append("")
buckets = [("< 1KB", 0, 1024), ("1KB~10KB", 1024, 10240), ("10KB~100KB", 10240, 102400), (">= 100KB", 102400, float("inf"))]
lines.append("| 区间 | 数量 |")
lines.append("| --- | --- |")
for label, lo, hi in buckets:
    cnt = sum(1 for _, s, _ in files if lo <= s < hi)
    lines.append(f"| {label} | {cnt} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("*本档案由 Agent 1 自动扫描生成，作为 20260819 的初始标准状态基准。*")
lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")

# 控制台摘要
print(f"扫描完成：{len(files)} 文件 / {len(dirs)} 目录 / {fmt_size(total_size)}")
print(f"报告已写入：{OUT.name}")
print(json.dumps({
    "files": len(files),
    "dirs": len(dirs),
    "total_size": total_size,
    "median": median,
    "ext_count": len(ext_stats),
    "top_entries": [(n, t, sz) for n, t, sz, _, _ in top_entries],
}, ensure_ascii=False, indent=2))
