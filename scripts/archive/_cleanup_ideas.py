# -*- coding: utf-8 -*-
"""清理 improvement_ideas 历史重复数据：按 title 去重，保留时间戳最新的一条。"""
import json
from evolver.improvement_generator import _generator, IDEAS_DIR

ideas = _generator._ideas
before = len(ideas)

# 按 title 分组，保留 timestamp 最新的一条
best = {}
for iid, idea in ideas.items():
    title = idea.title
    if title not in best:
        best[title] = (iid, idea)
    else:
        # 保留 timestamp 更新的
        if idea.timestamp > best[title][1].timestamp:
            best[title] = (iid, idea)

cleaned = {iid: idea for iid, idea in best.values()}
after = len(cleaned)

# 写回
_generator._ideas = cleaned
# 恢复 counter
ids = [int(iid.split("-")[-1]) for iid in cleaned if iid.startswith("idea-") and iid.split("-")[-1].isdigit()]
_generator._counter = max(ids) if ids else 0
_generator._save()

print(f"清理完成: {before} -> {after} 个创意 (删除 {before - after} 个重复)")
print(f"counter 恢复为: {_generator._counter}")

# 验证文件大小
import os
fp = IDEAS_DIR / "improvement_ideas.json"
print(f"文件大小: {os.path.getsize(fp)} 字节")
