# -*- coding: utf-8 -*-
"""分析 memory/tasks.json 的任务分布，识别压力测试污染数据。"""
import json
from collections import Counter

d = json.load(open('memory/tasks.json', encoding='utf-8'))
print('TOTAL_KEYS', len(d))

# 看一个任务结构
k0 = list(d.keys())[0]
print('SAMPLE_KEY', k0)
print('SAMPLE_VALUE', json.dumps(d[k0], ensure_ascii=False)[:600])
print('SAMPLE_TYPE', type(d[k0]).__name__)
if isinstance(d[k0], dict):
    print('SAMPLE_FIELDS', list(d[k0].keys()))

# 统计标题模式
title_counter = Counter()
status_counter = Counter()
parent_ids = set()

def walk(obj):
    """收集所有任务的 title/status/parent 统计。"""
    if isinstance(obj, dict):
        t = obj.get('title') or obj.get('name') or ''
        title_counter[t] += 1
        s = obj.get('status') or obj.get('state') or ''
        status_counter[s] += 1
        p = obj.get('parent_id') or obj.get('parent') or ''
        if p:
            parent_ids.add(p)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                walk(v)
    elif isinstance(obj, list):
        for v in obj:
            walk(v)

for k, v in d.items():
    walk(v)

print('--- 标题出现次数 Top 20 ---')
for t, c in title_counter.most_common(20):
    print(c, repr(t[:60]))

print('--- status 分布 ---')
for s, c in status_counter.most_common(20):
    print(c, repr(s))

# 压力测试任务统计
stress = [t for t in title_counter if '压力测试' in t or '超长任务标题' in t]
stress_total = sum(title_counter[t] for t in stress)
print('--- 压力测试相关任务 ---')
print('种类数:', len(stress), '总数:', stress_total)

# 占位任务统计
placeholder = ['系统扩容计划', '完善监控体系', '集成安全网与监控']
for p in placeholder:
    print('占位符', repr(p), title_counter.get(p, 0))

# 有 parent 的任务（子任务）
print('--- 有 parent_id 的任务数 ---')
print(len(parent_ids))
