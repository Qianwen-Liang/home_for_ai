#!/usr/bin/env python3
"""
《星陨天穹》章节写作工作流
用法：
  python chapter_workflow.py <章号> [当前战气] [--brief]

示例：
  python chapter_workflow.py 3             # 第三章完整检查清单
  python chapter_workflow.py 3 500         # 指定主角当前战气
  python chapter_workflow.py 3 --brief     # 仅输出快速卡片
"""

import sys
import math

# ============================================================
# 曲线参数（与 clean_numbers_design.py 保持一致）
# ============================================================
ALPHA = 1.35
TIERS = {
    1: {"name": "凡人境", "threshold": 500,    "ch_range": (1, 35)},
    2: {"name": "超凡境", "threshold": 10000,  "ch_range": (30, 80)},
    3: {"name": "通灵境", "threshold": 200000, "ch_range": (70, 150)},
    4: {"name": "宗师境", "threshold": 5000000,"ch_range": (130, 250)},
    5: {"name": "王者境", "threshold": 1e8,    "ch_range": (220, 400)},
    6: {"name": "圣者境", "threshold": 2e9,    "ch_range": (350, 600)},
    7: {"name": "帝境",   "threshold": 5e10,   "ch_range": (550, 900)},
    8: {"name": "神境",   "threshold": 1e12,   "ch_range": (800, 1200)},
}

# ============================================================
# 知识库条目映射（供 AI 调用，脚本中仅作引用）
# ============================================================
KB_ENTRIES = {
    "八境体系":     "K1785302902",
    "林缺设定":     "K1785302918",
    "创作规范":     "K1785302959",
    "太虚引星诀":   "K1785302925",
    "名词体系":     "K1785305099",
    "配角群":       "K1785304548",
    "第一章摘要":   "K1785302934",
    "第二章摘要":   "K1785302942",
    "工作流":       "K1785305230",
}

# ============================================================
# 名词配额表
# ============================================================
NOUN_QUOTA = {
    (1, 3):   {"max_new": 3, "available": ["纹", "天命系统", "测灵碑"]},
    (3, 10):  {"max_new": 3, "available": ["窍", "引星", "脱凡关", "一转", "二转", "窍位"]},
    (10, 30): {"max_new": 2, "available": ["万关", "入门", "小成", "大成", "圆满", "三转", "四转"]},
    (30, 80): {"max_new": 2, "available": ["通灵", "神识", "五转", "六转", "灵压"]},
}

# ============================================================
# 核心函数
# ============================================================

def get_tier(chapter_num):
    """根据章节号推断当前境界"""
    for tier_id, info in TIERS.items():
        lo, hi = info["ch_range"]
        if lo <= chapter_num <= hi:
            return tier_id, info
    return None, None

def estimate_combat_power(chapter_num):
    """根据章节号估计主角战气（插值）"""
    # Tier 1: 从 Ch1(500) 到 Ch30(10000)
    if chapter_num <= 35:
        # 线性插值
        progress = (chapter_num - 1) / 29  # Ch1→Ch30
        return int(500 + progress * 9500)
    elif chapter_num <= 80:
        progress = (chapter_num - 30) / 50
        return int(10000 + progress * 190000)
    elif chapter_num <= 150:
        progress = (chapter_num - 70) / 80
        return int(200000 + progress * 4800000)
    else:
        return int(5000000 * (2 ** (ALPHA * math.sqrt(chapter_num / 50))))

def print_banner(chapter_num, combat_power):
    print()
    print("=" * 60)
    print(f"   《星陨天穹》第 {chapter_num} 章 · 写作工作流")
    tier_id, tier_info = get_tier(chapter_num)
    if tier_info:
        print(f"   当前境界: Tier {tier_id} · {tier_info['name']}")
        print(f"   境界门槛: {tier_info['threshold']:,}")
        print(f"   章节范围: Ch{tier_info['ch_range'][0]}–{tier_info['ch_range'][1]}")
    print(f"   主角战气估计: {combat_power:,}")
    print("=" * 60)
    print()

def print_phase_a(chapter_num, combat_power):
    """阶段 A：锚定"""
    print("─" * 60)
    print("  阶段 A：锚定（15 分钟）")
    print("─" * 60)
    print()

    # A1
    tier_id, tier_info = get_tier(chapter_num)
    next_threshold = None
    for tid, info in TIERS.items():
        if info["threshold"] > combat_power:
            next_threshold = info["threshold"]
            break

    print("  A1. 曲线位置确认")
    print(f"      主角当前战气: {combat_power:,}")
    print(f"      下一门槛:     {next_threshold:,}（还需 {next_threshold - combat_power:,}）")
    print(f"      本章战气上限: ~{int(combat_power * 1.2):,}（允许 ±5% 浮动）")
    print()

    # A2
    print("  A2. 知识库调取（8 条）")
    for i, (name, kid) in enumerate(KB_ENTRIES.items(), 1):
        if name in ("工作流",):
            continue
        print(f"      {i}. [{kid}] {name}")
    print("      另：通读上一章最后 500 字")
    print()

    # A3
    print("  A3. 上章断点清单")
    print("      Q1: 上章在哪个画面结束？")
    print("      Q2: 读者此刻情绪？")
    print("      Q3: 未收线索有哪些？")
    print("      Q4: 本章必须回答什么？")
    print()

    # A4
    print("  A4. 战气区间锁定")
    print(f"      起始: {combat_power:,}（不可改）")
    print(f"      结束: ~{int(combat_power * 1.15):,}–{int(combat_power * 1.25):,}（±5%）")
    print(f"      跨门槛: {'⚠️ 是 — 需分配足够篇幅' if next_threshold and (next_threshold - combat_power < combat_power * 0.25) else '否'}")
    print()

    # A5
    print("  A5. 名词配额")
    for (lo, hi), quota in NOUN_QUOTA.items():
        if lo <= chapter_num <= hi:
            print(f"      本章段: Ch{lo}–{hi}，新名词上限 {quota['max_new']} 个")
            print(f"      可用名词: {', '.join(quota['available'])}")
            break
    else:
        print("      本章段: 后期，新名词上限 1–2 个")
    print()

def print_phase_b(chapter_num, combat_power):
    """阶段 B：构架"""
    print("─" * 60)
    print("  阶段 B：构架（30 分钟）")
    print("─" * 60)
    print()

    print("  B1. 场景清单（建议 3–5 个）")
    print("       格式: 场景 N/M：地点 · 时间 → 动作 → 情绪走向 → 战气变化")
    print("       示例:")
    print("         场景 1/5：西院小屋 · 黄昏")
    print("           动作: [待填充]")
    print("           情绪: 平静 → 微微紧绷")
    print("           数字: [待填充]")
    print()

    print("  B2. POV 感官锚点")
    print("       每个场景标注感官焦点: 视觉 / 听觉 / 触觉 / 内部感知")
    print("       每场景至少一段纯描写（无对话、无独白）")
    print()

    print("  B3. 关键数字节点")
    print("       标注数字出现位置和形式：")
    print("       • 仅天命系统浮现 + 林缺内心 → 精确数字")
    print("       • 其余场景 → 模糊表达（「又涨了一点」「接近七百」）")
    print()

    print("  B4. 配角弧光检查")
    print("       对照 K1785304548，确认：")
    print("       • 出场配角当前弧光位置")
    print("       • 本章推进幅度（不能跳阶段）")
    print("       • 不出场的配角留给后续")
    print()

def print_phase_c(chapter_num, combat_power):
    """阶段 C：成稿"""
    print("─" * 60)
    print("  阶段 C：成稿（90–120 分钟）")
    print("─" * 60)
    print()

    print("  C1. 场景逐个写作")
    print("       每场景目标字数: ~500–700 字（总目标 ÷ 场景数）")
    print()
    print("       即时约束:")
    print("         ✗ 林缺对话 ≤ 2 句/场景，每句 ≤ 15 字")
    print("         ✗ 禁止其他角色知道林缺精确战气值")
    print("         ✗ 禁止战力数字出现在对话中")
    print("         ✗ 禁止林缺一次想太远（只想眼前一步）")
    print("         ✓ 允许短句为主，偶尔长句换气")
    print()

    print("  C2. 场景自检（4 问）")
    print("       □ 描写 ≥ 叙述？（≥50% 句子是画面/声音/触感/气味）")
    print("       □ 林缺对话 ≤ 2 句？")
    print("       □ 精确数字仅出现在允许位置？")
    print("       □ 情绪有变化？（平→扬 或 扬→抑）")
    print()

    print("  C3. 全章通读")
    print("       • 调整场景间呼吸节奏")
    print("       • 检查过渡句")
    print("       • 总字数: 2,000–3,500")
    print()

def print_phase_d(chapter_num, combat_power):
    """阶段 D：收尾"""
    print("─" * 60)
    print("  阶段 D：收尾（20 分钟）")
    print("─" * 60)
    print()

    print("  D1. 四维一致性校验")
    print("       战力: 所有数字符合曲线区间")
    print("       名词: 新名词 ≤ 配额，用法规范")
    print("       人物: 配角言行符合弧光位置")
    print("       视角: 全文林缺第三人称有限视角")
    print()

    print("  D2. 章节摘要 → 知识库")
    print("       格式:")
    print("         • 核心事件（3–5 条）")
    print("         • 战气变化（起→终）")
    print("         • 新引入设定/名词")
    print("         • 出场配角 + 弧光进度")
    print("         • 未收线索")
    print("         • 断点画面")
    print()

    print("  D3. 动态条目更新")
    print("       配角弧光推进 → K1785304548")
    print("       新功法机制   → K1785302925")
    print("       战力新信息   → K1785302902")
    print("       名词新用法   → K1785305099")
    print()

def print_quick_card():
    """快速参考卡片"""
    print()
    print("┌─────────────────────────────────────────┐")
    print("│  《星陨天穹》每章写作检查清单            │")
    print("│                                         │")
    print("│  □ A1 曲线位置确认                      │")
    print("│  □ A2 知识库 8 条调取                   │")
    print("│  □ A3 上章断点 + 情绪残留               │")
    print("│  □ A4 战气区间锁定                      │")
    print("│  □ A5 名词配额                          │")
    print("│  □ B1 场景清单（3-5 个）                │")
    print("│  □ B2 POV 感官锚点                      │")
    print("│  □ B3 数字节点标注                      │")
    print("│  □ B4 配角弧光检查                      │")
    print("│  □ C1 场景逐个写（每场景自检）          │")
    print("│  □ C2 场景自检 4 问                     │")
    print("│  □ C3 全章通读 + 字数                   │")
    print("│  □ D1 四维一致性校验                    │")
    print("│  □ D2 章节摘要入库                      │")
    print("│  □ D3 动态条目更新                      │")
    print("│                                         │")
    print("│  铁律：                                  │")
    print("│  • 林缺对话 ≤ 8 句/章，每句 ≤ 15 字     │")
    print("│  • 精确数字仅天命系统 + 林缺内心         │")
    print("│  • 描写 ≥ 叙述                          │")
    print("│  • 战力数字跟曲线，不跟灵感             │")
    print("│  • 每章至少 30% 叙事不含任何名词         │")
    print("└─────────────────────────────────────────┘")
    print()

# ============================================================
# 主入口
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python chapter_workflow.py <章号> [当前战气] [--brief]")
        print("示例: python chapter_workflow.py 3")
        print("      python chapter_workflow.py 3 500")
        print("      python chapter_workflow.py 3 --brief")
        sys.exit(1)

    chapter_num = int(sys.argv[1])

    # 解析可选参数
    combat_power = None
    brief = False

    for arg in sys.argv[2:]:
        if arg == "--brief":
            brief = True
        else:
            try:
                combat_power = int(arg)
            except ValueError:
                pass

    if combat_power is None:
        combat_power = estimate_combat_power(chapter_num)

    if brief:
        print_quick_card()
    else:
        print_banner(chapter_num, combat_power)
        print_phase_a(chapter_num, combat_power)
        print_phase_b(chapter_num, combat_power)
        print_phase_c(chapter_num, combat_power)
        print_phase_d(chapter_num, combat_power)
        print_quick_card()

    print("─" * 60)
    print("  工作流模板输出完毕。请逐阶段执行。")
    print("─" * 60)
    print()

if __name__ == "__main__":
    main()
