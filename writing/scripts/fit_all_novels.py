"""
9本男频战斗小说战力曲线拟合 —— 对比《诡秘之主》的 2^(α√k) 模型
"""
import math

def fit_2sqrtk(data, name):
    """Fit y = base * 2^(alpha * sqrt(k)) to data[(k, log10_energy), ...]"""
    n = len(data)
    k_vals = [d[0] for d in data]
    y_vals = [d[1] for d in data]
    
    log2y = [math.log2(y) for y in y_vals]
    sqk = [math.sqrt(k) for k in k_vals]
    
    sx, sy = sum(sqk), sum(log2y)
    sxy = sum(x*y for x,y in zip(sqk, log2y))
    sx2 = sum(x*x for x in sqk)
    
    alpha = (n*sxy - sx*sy) / (n*sx2 - sx*sx)
    c = (sy - alpha*sx) / n
    
    ssr, sst = 0, sum((y - sy/n)**2 for y in y_vals)
    for i in range(n):
        pred = 2**(alpha*sqk[i] + c)
        ssr += (y_vals[i] - pred)**2
    r2 = 1 - ssr/sst
    
    # Also test pure 2^sqrt(k) without fitting
    ssr_pure = sum((y_vals[i] - 2**sqk[i])**2 for i in range(n))
    r2_pure = 1 - ssr_pure/sst
    
    # And simple exponential a*b^k
    log10y = [math.log10(y) for y in y_vals]
    sk = sum(k_vals)
    sk2 = sum(k*k for k in k_vals)
    sly = sum(log10y)
    skly = sum(k*l for k,l in zip(k_vals, log10y))
    logb = (n*skly - sk*sly) / (n*sk2 - sk*sk)
    loga = (sly - logb*sk) / n
    ssr_exp = sum((y_vals[i] - 10**(loga + logb*k_vals[i]))**2 for i in range(n))
    r2_exp = 1 - ssr_exp/sst
    
    return {
        'name': name,
        'alpha': alpha,
        'c': c,
        'base': 2**c,
        'r2_sqrtk': r2,
        'r2_pure': r2_pure,
        'r2_exp': r2_exp,
        'n_levels': n,
        'data': data,
    }


# ═══════════════════════════════════════════════════════════
# 各小说的战力数据 (k步数, log10(破坏能量≈焦耳))
# 基于粉丝社区共识、VS Battles 对标、原文表现推算
# ═══════════════════════════════════════════════════════════

novels = {}

# --- 1. 斗破苍穹 (12级斗气体系，去除斗帝的11级用于拟合) ---
novels['斗破苍穹'] = [
    (1, 3.0),   # 斗者: 碎石级 ~10³J
    (2, 4.5),   # 斗师: 破墙级
    (3, 6.0),   # 大斗师: 爆屋级
    (4, 7.5),   # 斗灵: 爆大型建筑
    (5, 9.0),   # 斗王: 飞行+范围攻击 
    (6, 10.5),  # 斗皇: 摧毁小城
    (7, 12.0),  # 斗宗: 空间能力+毁城
    (8, 13.5),  # 斗尊: 移山填海
    (9, 15.0),  # 半圣: 半圣级
    (10, 17.0), # 斗圣: 毁天灭地
]

# --- 2. 凡人修仙传 (人界+灵界，去除真仙以上) ---
novels['凡人修仙传'] = [
    (1, 3.5),   # 炼气: 火球术+灵力护体
    (2, 5.5),   # 筑基: 摧毁房屋
    (3, 7.5),   # 结丹: 摧毁小山
    (4, 10.0),  # 元婴: 移山填海
    (5, 12.0),  # 化神: 影响一国
    (6, 14.0),  # 炼虚: 跨越空间
    (7, 16.0),  # 合体: 大陆级影响
    (8, 18.0),  # 大乘: 准飞升
]

# --- 3. 斗罗大陆 (魂师体系，去除神级) ---
novels['斗罗大陆'] = [
    (1, 2.5),   # 魂士: 强化体质
    (2, 4.0),   # 魂师: 第一魂环
    (3, 5.5),   # 大魂师
    (4, 7.0),   # 魂尊
    (5, 8.5),   # 魂宗: 可破建筑
    (6, 10.0),  # 魂王
    (7, 11.5),  # 魂帝
    (8, 13.0),  # 魂圣: 宗门级
    (9, 14.5),  # 魂斗罗
    (10, 16.5), # 封号斗罗: 城市级
]

# --- 4. 遮天 (宏大型，数据跨度极大) ---
novels['遮天'] = [
    (1, 4.0),   # 轮海(彼岸): 初步超凡
    (2, 6.5),   # 道宫
    (3, 9.0),   # 四极: 大型破坏
    (4, 11.5),  # 化龙
    (5, 14.0),  # 仙台(半步大能)
    (6, 16.5),  # 大能
    (7, 19.0),  # 王者
    (8, 21.5),  # 圣人: 爆星级
    (9, 24.0),  # 圣人王
    (10, 27.0), # 大圣: 星系级
]

# --- 5. 盘龙 (西幻，从魔法师到上位神) ---
novels['盘龙'] = [
    (1, 3.0),   # 1-3级魔法师
    (2, 5.0),   # 4-6级
    (3, 7.0),   # 7-9级
    (4, 9.5),   # 圣域: 摧毁城堡
    (5, 12.5),  # 下位神: 影响位面
    (6, 15.5),  # 中位神
    (7, 18.5),  # 上位神: 位面战争
]

# --- 6. 吞噬星空 (武者到界主，去除不朽以上) ---
novels['吞噬星空'] = [
    (1, 3.0),   # 初级战士
    (2, 4.5),   # 中级战士
    (3, 6.0),   # 高级战士
    (4, 8.0),   # 战神: 城市级
    (5, 10.5),  # 行星级: 灭城
    (6, 13.5),  # 恒星级: 灭国
    (7, 16.5),  # 宇宙级: 爆星
    (8, 19.5),  # 域主
    (9, 23.0),  # 界主: 星系级
]

# --- 7. 大王饶命 (都市异能，体系克制) ---
novels['大王饶命'] = [
    (1, 3.0),   # F级: 基础觉醒
    (2, 4.5),   # E级
    (3, 6.5),   # D级
    (4, 8.5),   # C级: 楼级
    (5, 10.5),  # B级: 街区级
    (6, 13.0),  # A级: 城市级
]

# --- 8. 剑来 (武道体系，相对克制) ---
novels['剑来'] = [
    (1, 3.0),   # 泥胚: 武夫入门
    (2, 4.5),   # 木胎
    (3, 6.0),   # 水银
    (4, 7.5),   # 英魂
    (5, 9.0),   # 雄魄
    (6, 10.5),  # 武胆
    (7, 12.0),  # 金身
    (8, 14.0),  # 羽化
    (9, 16.0),  # 远游: 影响天象
    (10, 18.0), # 山巅
]

# --- 9. 雪中悍刀行 (武者体系) ---
novels['雪中悍刀行'] = [
    (1, 2.5),   # 九品武夫
    (2, 3.5),   # 八品
    (3, 5.0),   # 七品
    (4, 6.5),   # 六品
    (5, 8.0),   # 五品
    (6, 9.5),   # 四品
    (7, 11.0),  # 三品: 百人敌
    (8, 13.0),  # 二品小宗师: 千人敌
    (9, 15.0),  # 一品金刚: 城级
    (10, 17.0), # 指玄
    (11, 19.0), # 天象: 影响气象
    (12, 21.0), # 陆地神仙: 万人敌
]

# --- 参考: 诡秘之主 ---
novels['诡秘之主'] = [
    (1, 3.0), (2, 4.0), (3, 5.5), (4, 7.5),
    (5, 9.5), (6, 11.5), (7, 13.5), (8, 16.0),
]


# ═══════════════════════════════════════════════════════════
# 拟合与输出
# ═══════════════════════════════════════════════════════════

print("=" * 80)
print("9本男频战斗小说 + 诡秘之主：2^(α√k) 拟合对比")
print("=" * 80)

results = []
for name, data in novels.items():
    r = fit_2sqrtk(data, name)
    results.append(r)

# Sort by R²
results.sort(key=lambda x: x['r2_sqrtk'], reverse=True)

print(f"\n{'排名':<4} {'小说':<12} {'等级数':<6} {'α系数':<8} {'R²(2^α√k)':<12} {'R²(纯2^√k)':<12} {'R²(指数)':<12} {'评价'}")
print("-" * 80)

for i, r in enumerate(results):
    grade = ""
    if r['r2_sqrtk'] >= 0.99:
        grade = "🏆 完美"
    elif r['r2_sqrtk'] >= 0.95:
        grade = "✅ 优秀"
    elif r['r2_sqrtk'] >= 0.90:
        grade = "👍 良好"
    elif r['r2_sqrtk'] >= 0.85:
        grade = "📐 可用"
    else:
        grade = "❌ 不适用"
    
    print(f"{i+1:<4} {r['name']:<12} {r['n_levels']:<6} α={r['alpha']:.3f}  {r['r2_sqrtk']:.4f}        {r['r2_pure']:.4f}        {r['r2_exp']:.4f}     {grade}")

print()
print("=" * 80)
print("详细分析")
print("=" * 80)

for r in results:
    print(f"\n{'─'*60}")
    print(f"【{r['name']}】  α={r['alpha']:.3f}  base={r['base']:.3f}  R²={r['r2_sqrtk']:.4f}")
    print(f"  拟合公式: y = {r['base']:.3f} × 2^({r['alpha']:.3f} × √k)")
    print(f"  纯2^√k R²={r['r2_pure']:.4f} | 指数R²={r['r2_exp']:.4f}")
    print(f"  {'k':<4} {'实际':<8} {'预测':<8} {'误差':<8}")
    for i, (k, y) in enumerate(r['data']):
        pred = 2**(r['alpha'] * math.sqrt(k) + r['c'])
        print(f"  {k:<4} {y:<8.1f} {pred:<8.2f} {y-pred:<+8.2f}")

# 对比 α 系数的分布
print(f"\n{'─'*60}")
print("α 系数分布分析:")
print(f"{'─'*60}")
for r in results:
    # α interpretation
    if r['alpha'] > 2.0:
        interp = "极陡峭——升级带来指数级质变"
    elif r['alpha'] > 1.5:
        interp = "陡峭——每级有显著质变"
    elif r['alpha'] > 1.2:
        interp = "温和——渐近增长，类似诡秘之主"
    elif r['alpha'] > 0.9:
        interp = "平缓——升级以量变为主"
    else:
        interp = "极平缓——战力增长慢，靠技巧弥补"
    print(f"  {r['name']:<12} α={r['alpha']:.3f}  {interp}")
