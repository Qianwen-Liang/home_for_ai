"""
隐藏曲线设计：α=1.35，八境制，取整战力值
"""
import math

alpha, c = 1.35, 0.08
print("=" * 60)
print("战力数值设计（隐藏曲线 α=1.35）")
print("=" * 60)

powers = []
for k in range(1, 9):
    logE = 2**(alpha*math.sqrt(k) + c)
    # Round to human-readable numbers
    raw_power = 10**logE
    # Round strategically
    if raw_power < 1000:
        display = round(raw_power / 100) * 100
    elif raw_power < 10000:
        display = round(raw_power / 1000) * 1000
    elif raw_power < 1e6:
        display = round(raw_power / 10000) * 10000
    elif raw_power < 1e8:
        display = round(raw_power / 1e6) * 1e6
    elif raw_power < 1e10:
        display = round(raw_power / 1e8) * 1e8
    elif raw_power < 1e12:
        display = round(raw_power / 1e10) * 1e10
    else:
        display = round(raw_power / 1e12) * 1e12
    powers.append((k, logE, raw_power, display))

# Chapter design: inversely proportional to energy multiplier
multipliers = [2**(alpha*(math.sqrt(i+1)-math.sqrt(i))) for i in range(1, 8)]
inv_mul = [1/m for m in multipliers]
total_inv = sum(inv_mul)
total_chapters = 380
chapter_ratios = [im/total_inv for im in inv_mul]
chapters = [round(r * total_chapters) for r in chapter_ratios]

print("\n境界\tlogE\t原始战力\t取整战力\t间隔章数")
for i, (k, le, raw, disp) in enumerate(powers):
    tier_names = ["", "凡人境", "超凡境", "通灵境", "宗师境", "王者境", "圣者境", "帝境", "天境"]
    ch = chapters[i-1] if i > 0 else 0
    print(f"T{k} {tier_names[k]:6s} {le:.1f}\t{raw:.1e}\t{disp:>12,.0f}\t{ch}")
print(f"\n总章节: {sum(chapters)} + 序幕尾声")

# Power formatting helper  
print("\n战力显示格式:")
for i, (k, le, raw, disp) in enumerate(powers):
    if disp >= 1e12:
        s = f"{disp/1e12:.0f}万亿"
    elif disp >= 1e8:
        s = f"{disp/1e8:.0f}亿"
    elif disp >= 1e4:
        s = f"{disp/1e4:.0f}万"
    else:
        s = f"{disp:.0f}"
    print(f"  Tier {k}: {s}")

print("\n每章战力增长(对数):")
for i, (ch, m) in enumerate(zip(chapters, multipliers)):
    le_gain = math.log2(m) / ch
    print(f"  Tier{i+1}->{i+2}: {ch}章, 每章log2增长={le_gain:.4f}")
