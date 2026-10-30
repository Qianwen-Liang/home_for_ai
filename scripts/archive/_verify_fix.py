# -*- coding: utf-8 -*-
"""验证 self_improver / improvement_generator 修复效果"""
from collections import Counter

from evolver.improvement_generator import _generator

# 1. 历史创意状态分布
status_counter = Counter(getattr(i, "status", "proposed") for i in _generator._ideas.values())
title_counter = Counter(i.title for i in _generator._ideas.values())
print("=== 历史创意状态分布 ===")
for s, c in status_counter.most_common():
    print(f"  {s}: {c}")
print(f"  创意总数: {len(_generator._ideas)}")
print(f"  唯一 title 数: {len(title_counter)}")
print(f"  重复 title 数: {sum(1 for t, c in title_counter.items() if c > 1)}")
print()

# 2. generate_all 去重效果
ideas = _generator.generate_all(limit=30)
titles = [i.title for i in ideas]
print(f"=== generate_all 返回 {len(ideas)} 个创意 ===")
print(f"  唯一 title 数: {len(set(titles))} (去重后应等于返回数)")
for i in ideas[:10]:
    print(f"  [{i.priority_score:.3f}] {i.status:12s} {i.title}  ({i.improvement_type.value})")
print()

# 3. 测试状态标记 + 排除已尝试
if ideas:
    test_idea = ideas[0]
    print(f"=== 测试 _mark_idea_status 标记 '{test_idea.title}' ===")
    from evolver.self_improver import SelfImprover
    imp = SelfImprover()
    ok = imp._mark_idea_status(test_idea.idea_id, "rejected")
    print(f"  标记 rejected 结果: {ok}")
    # 重新生成，该 title 应被排除
    ideas2 = _generator.generate_all(limit=30)
    titles2 = [i.title for i in ideas2]
    excluded = test_idea.title not in titles2
    print(f"  重新 generate_all 后该创意是否被排除: {excluded}")
    # 还原状态为 proposed，避免影响后续
    imp._mark_idea_status(test_idea.idea_id, "proposed")
    print("  (已还原为 proposed)")
