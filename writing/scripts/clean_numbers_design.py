"""
微调后的战力数值设计 —— 干净数字版
目标：1) 科学计数法为整数或一位小数  2) 大境界突破用10的幂次
"""
import math

# 原曲线参数
alpha_original = 1.35

# 新的干净门槛（读者友好）
clean_thresholds = [
    (1, 500,        "五百"),
    (2, 10000,      "一万"),
    (3, 200000,     "二十万"),
    (4, 5000000,    "五百万"),
    (5, 400000000,  "四亿"),
    (6, 50000000000,"五百亿"),
    (7, 10000000000000,    "十万亿"),
    (8, 1000000000000000,  "一千万亿"),
]

print("=" * 70)
print("干净数字 vs 原曲线 对比")
print("=" * 70)
print(f"{'境界':<10} {'干净值':<12} {'曲线原始值':<14} {'偏差%':<10} {'科学计数':<12}")
print("-" * 70)

clean_logE = []
for k, val, label in clean_thresholds:
    log_val = math.log10(val)
    curve_logE = 2**(alpha_original*math.sqrt(k) + 0.08)
    curve_val = 10**curve_logE
    deviation = (val - curve_val) / curve_val * 100
    
    # 科学计数法
    exp = int(math.floor(math.log10(val)))
    mantissa = val / 10**exp
    if mantissa == int(mantissa):
        scinot = f"{int(mantissa)}×10^{exp}"
    else:
        scinot = f"{mantissa:.1f}×10^{exp}"
    
    clean_logE.append(log_val)
    print(f"Tier {k:<4} {label:<12} {curve_val:<14.1f} {deviation:+.0f}%{'':<6} {scinot:<12}")

# 重新拟合 α
print()
print("--- 用干净数字重新拟合 2^(α√k) ---")
n = 8
k_vals = list(range(1, 9))
log2_clean = [math.log2(math.log10(v)) for _, v, _ in clean_thresholds]
sqk = [math.sqrt(k) for k in k_vals]

sx = sum(sqk); sy = sum(log2_clean)
sxy = sum(x*y for x,y in zip(sqk, log2_clean))
sx2 = sum(x*x for x in sqk)
alpha_new = (n*sxy - sx*sy) / (n*sx2 - sx*sx)
c_new = (sy - alpha_new*sx) / n

# R²
ssr, sst = 0, sum((y - sy/n)**2 for y in log2_clean)
for i in range(n):
    pred = alpha_new*sqk[i] + c_new
    ssr += (log2_clean[i] - pred)**2
r2 = 1 - ssr/sst

print(f"新 α = {alpha_new:.4f}  (原 α = {alpha_original})")
print(f"R² = {r2:.4f}")
print(f"新公式: log₁₀(E) = 2^({alpha_new:.4f}√k + {c_new:.4f})")

# 残差
print(f"\n{'k':<4} {'log10(干净值)':<16} {'拟合预测':<14} {'误差':<10}")
for i in range(8):
    pred = alpha_new*sqk[i] + c_new
    actual = log2_clean[i]
    print(f"{i+1:<4} {actual:<16.4f} {pred:<14.4f} {actual-pred:<+10.4f}")

# 每境倍率
print(f"\n每境倍率:")
for i in range(7):
    ratio = clean_thresholds[i+1][1] / clean_thresholds[i][1]
    print(f"  Tier{i+1}→{i+2}:  {clean_thresholds[i][2]}→{clean_thresholds[i+1][2]}  ×{ratio:.0f}")

# 章节设计
print(f"\n--- 章节分配 ---")
inv_ch_weights = []
for i in range(7):
    ratio = clean_thresholds[i+1][1] / clean_thresholds[i][1]
    # 倍率越大，需要的章数越多
    w = ratio
    inv_ch_weights.append(w)

total_w = sum(inv_ch_weights)
total_chapters = 370
chapters = [max(25, round(w/total_w * total_chapters)) for w in inv_ch_weights]
print(f"总章数: {sum(chapters)} (不含序幕尾声)")
for i in range(7):
    print(f"  Tier{i+1}→{i+2}: ~{chapters[i]}章")

# 主角中途战力示例
print(f"\n--- 主角中途战气值示例（取整后） ---")
for k_frac in [1.0, 1.3, 1.7, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]:
    # 线性插值
    ki = int(k_frac)
    frac = k_frac - ki
    if ki < 8 and frac > 0:
        logE_interp = math.log10(clean_thresholds[ki-1][1]) + frac * (math.log10(clean_thresholds[ki][1]) - math.log10(clean_thresholds[ki-1][1]))
    elif ki >= 8:
        logE_interp = math.log10(clean_thresholds[7][1])
    else:
        logE_interp = math.log10(clean_thresholds[ki-1][1])
    
    raw = 10**logE_interp
    # 取整到好看的数字
    if raw < 1000:
        nice = round(raw / 50) * 50
    elif raw < 10000:
        nice = round(raw / 500) * 500
    elif raw < 1e5:
        nice = round(raw / 5000) * 5000
    elif raw < 1e6:
        nice = round(raw / 50000) * 50000
    elif raw < 1e7:
        nice = round(raw / 5e5) * 5e5
    elif raw < 1e8:
        nice = round(raw / 5e6) * 5e6
    elif raw < 1e9:
        nice = round(raw / 5e7) * 5e7
    elif raw < 1e10:
        nice = round(raw / 5e8) * 5e8
    elif raw < 1e11:
        nice = round(raw / 5e9) * 5e9
    elif raw < 1e12:
        nice = round(raw / 5e10) * 5e10
    elif raw < 1e13:
        nice = round(raw / 5e11) * 5e11
    elif raw < 1e14:
        nice = round(raw / 5e12) * 5e12
    else:
        nice = round(raw / 5e13) * 5e13
    
    # 格式化显示
    if nice >= 1e12:
        s = f"{nice/1e12:.0f}万亿"
    elif nice >= 1e8:
        s = f"{nice/1e8:.0f}亿"
    elif nice >= 1e4:
        s = f"{nice/1e4:.0f}万"
    else:
        s = f"{nice:.0f}"
    
    print(f"  k={k_frac:.1f}: 原始{raw:.0f} → 取整{nice:.0f} ({s})")
