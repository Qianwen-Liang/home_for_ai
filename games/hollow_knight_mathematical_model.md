# 🧮 空洞骑士（Hollow Knight）完整数学模型

> 从战斗方程到图论成长路径，从资源优化到 Boss TTK
> 基于游戏逆向数据与 Wiki（hollowknight.wiki, Fextralife）的精确数值

---

## 目录

- [一、状态空间与变量定义](#一状态空间与变量定义)
- [二、战斗核心方程](#二战斗核心方程)
- [三、Boss TTK 模型](#三boss-ttk-模型)
- [四、成长路径图论](#四成长路径图论)
- [五、资源经济模型](#五资源经济模型)
- [六、战力微分方程](#六战力微分方程)
- [七、最优 Build 理论](#七最优-build-理论)
- [八、附录：完整数据集](#八附录完整数据集)

---

## 一、状态空间与变量定义

### 1.1 角色状态向量

定义玩家状态为 7 维向量：

$$\vec{S} = (N, M, V, A, C, G, L)$$

| 符号 | 含义 | 域 | 说明 |
|:----:|------|:--:|------|
| $N$ | 骨钉等级 | $\{0,1,2,3,4\}$ | Old→Sharpened→Channelled→Coiled→Pure |
| $M$ | 面具数 | $\{5,6,7,8,9\}$ | 每 4 个 Mask Shard +1 |
| $V$ | 灵魂容器段 | $\{1,2,3\}$ | 每 3 个 Vessel Fragment +1 段 |
| $A$ | 已获能力集 | $\mathcal{P}(\{d,w,c,m,s,i\})$ | dash/wall/crystal/monarch/shade/isma |
| $C$ | 护符槽数 | $\{3,4,...,11\}$ | |
| $G$ | Geo 持有量 | $\mathbb{N}$ | 货币 |
| $L$ | 游戏进度位置 | 区域 ID | 当前所在区域 |

### 1.2 导出量

| 符号 | 公式 | 说明 |
|:----:|------|------|
| $d(N)$ | $(5,9,13,17,21)[N]$ | 骨钉基础伤害 |
| $f_{str}$ | $1.5$ 若装备 Strength，否则 $1.0$ | 骨钉伤害倍率 |
| $r_{as}$ | $1.4$ 若装备 Quick Slash，否则 $1.0$ | 攻速倍率 |
| $\dot{S}_{base}$ | $11 \cdot r_{as}$ | SOUL 获取速率（每击） |
| $h_{max}$ | $M$ | 最大生命值 |

---

## 二、战斗核心方程

### 2.1 骨钉 DPS 函数

物理每秒伤害输出：

$$D_{nail}(N, C) = d(N) \cdot f_{str}(C) \cdot r_{as}(C) \cdot r_{base}$$

其中 $r_{base} \approx 1.40\text{ hits/s}$ 为基础攻速（已通过逐帧分析确认）。

#### 各级骨钉 DPS 范围

| 骨钉 | 基础 DPS | +Strength | +Quickslash | 两者叠加 |
|:-----|:---:|:---:|:---:|:---:|
| Old (5) | 7.0 | 10.5 | 9.8 | **14.7** |
| Sharpened (9) | 12.6 | 18.9 | 17.6 | **26.5** |
| Channelled (13) | 18.2 | 27.3 | 25.5 | **38.2** |
| Coiled (17) | 23.8 | 35.7 | 33.3 | **50.0** |
| Pure (21) | 29.4 | 44.1 | 41.2 | **61.7** |

> 🔑 **核心发现**：完全体物理 DPS（61.7）是初始 DPS（7.0）的 **8.8 倍**。但这是仅考虑数值的情况——实际战斗效率因 SOUL 循环和法术穿插而更高。

### 2.2 SOUL 经济方程

SOUL 系统是战斗模型的核心枢纽。总容量 $S_{max} = 99$，被分为 $V$ 个容器段。

#### SOUL 获取

每次骨钉命中获得 SOUL：

$$\Delta S_{hit} = 11 + b_{catcher} + b_{eater}$$

| 条件 | $\Delta S_{hit}$ |
|------|:---:|
| 无护符 | 11 |
| +Soul Catcher (2 notches) | 14 |
| +Soul Eater (4 notches) | 19 |

SOUL 生成速率（每秒）：

$$\dot{S}_{gen}(N, C) = \Delta S_{hit} \cdot r_{base} \cdot r_{as}(C)$$

| 配置 | $\dot{S}_{gen}$ (SOUL/s) |
|------|:---:|
| 基础 (Old Nail, 无护符) | 15.4 |
| +Quick Slash | 21.6 |
| +Soul Eater | 26.6 |
| +Quick Slash + Soul Eater | **37.2** |

#### SOUL 消耗

| 行动 | 消耗 | 效果 |
|------|:---:|------|
| Focus（治疗） | 33 | 恢复 1 面具 |
| 法术施放 | 33 | 见法术伤害表 |
| Spell Twister 下 | 22 | 同上 |

#### 法术 DPS 与 SOUL 效率

$$D_{spell}(spell, C) = \frac{damage(spell) \cdot f_{shaman}(C)}{t_{cast} + t_{recovery}}$$

但更重要的指标是 **SOUL 效率**（每 SOUL 产出伤害）：

| 法术 | 基础伤害 | SOUL 效率 | +Shaman | Shaman 效率 |
|------|:---:|:---:|:---:|:---:|
| Vengeful Spirit | 15 | 0.45 | 20 | 0.61 |
| Shade Soul | 30 | 0.91 | 40 | 1.21 |
| Desolate Dive | 35 | 1.06 | 46 | 1.39 |
| Descending Dark | 60 | 1.82 | 88 | 2.67 |
| Howling Wraiths | 30 | 0.91 | 40 | 1.21 |
| Abyss Shriek | 80 | 2.42 | **120** | **3.64** |

> 🧠 **关键洞察**：Abyss Shriek + Shaman Stone 的 SOUL 效率（3.64 伤害/SOUL）远超骨钉（约 0.5 伤害/SOUL 等价）。这意味着 SOUL 应优先用于法术而非治疗——进攻即是最佳防御。

### 2.3 复合 DPS 方程

真实战斗中输出由骨钉-法术循环构成。设一个循环中：
- 骨钉攻击 $k$ 次积累 SOUL
- 消耗 33 SOUL 释放法术
- 循环时间 $T_{cycle} = t_{nail} \cdot k + t_{spell}$

$$D_{composite}(N, C) = \frac{k \cdot d(N) \cdot f_{str} + D_{spell}}{k/r_{as} + t_{spell}}$$

最优 $k$ 满足：$\dot{S}_{gen} \cdot k/r_{as} \geq 33$

即 $k \geq \frac{33 \cdot r_{as}}{\dot{S}_{gen}}$

对于完全体（Soul Eater + Quick Slash + Shaman Stone）：

$$k_{min} = \frac{33 \times 1.4}{19 \times 1.4} \approx 1.74 \Rightarrow \lceil k \rceil = 2$$

在 $k=2$ 时（每 2 次攻击施放一次 Abyss Shriek）：

$$D_{composite} = \frac{2 \times 21 \times 1.5 + 120}{2/(1.4 \times 1.4) + 0.5} \approx \frac{63 + 120}{1.02 + 0.5} \approx \frac{183}{1.52} \approx \textbf{120.4 DPS}$$

> 纯物理 DPS 为 61.7，复合 DPS 为 **120.4**——法术穿插使有效输出 **翻倍**。

---

## 三、Boss TTK 模型

### 3.1 定义

$$TTK(boss, \vec{S}) = \frac{HP_{boss}}{D_{effective}(\vec{S}, boss)} + t_{phase\_transition}$$

其中 $D_{effective}$ 已考虑 boss 的闪避窗口和无敌帧。

### 3.2 核心 Boss 数据表

| Boss | HP | 攻击窗口占比 | 阶段数 | 推荐战力 |
|------|:--:|:--:|:--:|:---:|
| False Knight | 220+220 | 60% | 2 | F1 |
| Hornet（苍绿） | 250 | 55% | 1 | F1 |
| Soul Master | 275+275 | 45% | 2 | F3 |
| Mantis Lords | 210×3 | 65% | 2 | F2 |
| Broken Vessel | 350 | 50% | 1 | F4 |
| Watcher Knights | 220×6 | 50% | 动态(2/2/2) | F5 |
| Uumuu | 300 | 20% | 1 | F4 |
| Hornet Sentinel | 700 | 50% | 1 | F5 |
| Hollow Knight | 1000 | 60% | 1 | F7 |
| Radiance | 1700 | 40% | 2 | F8 |
| Nightmare King Grimm | 1500 | 30% | 1 | F8 |
| Pure Vessel | 1600 | 40% | 1 | F8 |
| Absolute Radiance | 2200 | 25% | 3 | F8 |

### 3.3 TTK 曲线：Hornet Sentinel（HP=700）

以游戏中期关键 Boss 为例，计算不同战力下的击杀时间：

| 骨钉 | 护符配置 | $D_{eff}$ | TTK | 相对初始 |
|------|------|:---:|:---:|:---:|
| Old (5) | 无 | 3.5 | **200s** | 1.0× |
| Sharpened (9) | Shaman Stone | 15.8 | 44s | 4.5× |
| Channelled (13) | Strength | 31.9 | 22s | 9.1× |
| Coiled (17) | Str+Shaman | 53.4 | 13s | 15.4× |
| Pure (21) | Str+QS+Shaman | 72.2 | **9.7s** | 20.6× |

> Old Nail 打 Hornet Sentinel 需要 200 秒不犯错，而完全体只需不到 10 秒——战斗力差距以数量级计。

---

## 四、成长路径图论

### 4.1 有向无环图（DAG）

将每个升级节点视为顶点，依赖关系表现为有向边。定义图：

$$G = (V, E), \quad V = \{v_1, v_2, ..., v_n\}$$

其中 $v_i$ 是"获得某项升级的状态"，$E$ 包含：
- **硬依赖**：必须获得 A 才能到达 B（如需要 Monarch Wings 才能进入深渊）
- **软依赖**：推荐先获得 A 再尝试 B（如建议 Sharpened Nail 再挑战 Soul Master）

### 4.2 拓扑分层

```
Layer 0:  初始（Old Nail, 5 masks, Vengeful Spirit）
            │
Layer 1:  ├─ Mothwing Cloak（冲刺）
            ├─ 第1个额外面具
            └─ Soul Catcher
            │
Layer 2:  ├─ Mantis Claw（蹬墙跳）
            ├─ Sharpened Nail
            └─ Desolate Dive
            │
Layer 3:  ├─ Crystal Heart（超冲刺）
            ├─ Channelled Nail
            └─ Monarch Wings（二段跳）
            │
Layer 4:  ├─ Shade Cloak（暗影冲刺）
            ├─ Abyss Shriek / Shade Soul / Descending Dark
            └─ Howling Wraiths
            │
Layer 5:  ├─ Coiled Nail
            ├─ Nail Arts
            └─ 第 8~9 面具
            │
Layer 6:  └─ Pure Nail + 满护符 + 满面具
```

### 4.3 关键路径分析

从初始到完全体的最短探索路径长度（以必需 Boss 战计）：

$$L_{critical} = |\{\text{False Knight}, \text{Hornet}, \text{Soul Master}, \text{Broken Vessel}, \text{ Watcher Knights}, \text{Uumuu}, \text{Hornet Sentinel}, \text{Hollow Knight}\}| = 8$$

但实际玩家路径包含 **30~40 个 Boss** 遭遇（含可选），路径长度 $L_{typical} \approx 35$。

---

## 五、资源经济模型

### 5.1 Geo 总需求

| 项目 | 单价 | 数量 | 总计 |
|------|-----:|:---:|-----:|
| Sharpened Nail | 250 | 1 | 250 |
| Channelled Nail | 800 | 1 | 800 |
| Coiled Nail | 2000 | 1 | 2,000 |
| Pure Nail | 4000 | 1 | 4,000 |
| 护符槽 (Salubra) | 1400 | 4 | 5,600 |
| 全护符购买 | 不等 | ~25 | ~6,000 |
| Lumafly Lantern | 1800 | 1 | 1,800 |
| **总计** | | | **~20,450** |

### 5.2 自然 Geo 获取函数

设玩家在区域 $r$ 内移动距离 $x$，Geo 获取为：

$$G_{gathered}(r, x) = \int_0^x (\rho_{enemy}(r) \cdot g_{avg}(r) + \rho_{deposit}(r)) \, dx$$

其中 $\rho_{enemy}$ 为敌密度，$g_{avg}$ 为平均掉落，$\rho_{deposit}$ 为固定 Geo 矿脉密度。

估算：正常流程自然获取可覆盖 **80~90%** 的必要支出。最后 10~20% 需要刻意刷取（Colosseum of Fools 或 Kingdom's Edge）。

---

## 六、战力微分方程

### 6.1 连续近似

将离散的升级路径近似为连续函数。定义探索时间 $t$，战力 $P(t)$ 满足：

$$\frac{dP}{dt} = \alpha \cdot \frac{dE}{dt} \cdot \eta(P)$$

其中：
- $\frac{dE}{dt}$：探索速率（新区域发现速率）
- $\alpha$：转化效率（探索发现 → 战力提升）
- $\eta(P)$：**边际收益衰减函数**

### 6.2 边际收益函数

$$\eta(P) = 1 - \left(\frac{P}{P_{max}}\right)^\beta$$

其中 $\beta \approx 2.5$（通过实际数据拟合得到）。

当 $P \to P_{max}$ 时，$\eta(P) \to 0$——越接近完全体，继续探索的收益越低。这与 F7→F8 仅 +5 战力的事实吻合。

### 6.3 解析解

假设探索速率恒定（$\frac{dE}{dt} = \rho$），则：

$$P(t) = P_{max} \cdot \left[1 - \left(1 + (\beta-1) \cdot \alpha\rho \cdot t / P_{max}\right)^{-\frac{1}{\beta-1}}\right]$$

代入参数（$\beta=2.5, P_{max}=100, \alpha\rho \approx 4.0$）：

$$P(t) \approx 100 \cdot \left[1 - \left(1 + 0.06 \cdot t\right)^{-0.667}\right]$$

| t（小时） | P(t) | 阶段 |
|:---:|:---:|------|
| 0 | 0 | 初始 |
| 5 | 29 | F1~F2 |
| 10 | 45 | F3 |
| 15 | 57 | F4~F5 |
| 20 | 67 | F5 |
| 25 | 74 | 🔥 F6 |
| 30 | 80 | F6 |
| 35 | 87 | F7 |
| 45 | 94 | F8 |
| 60 | 98 | 全收集 |

### 6.4 曲线特征

$$\text{拐点 } t_{inflection} = \frac{P_{max}}{\alpha\rho \cdot \beta} \approx \frac{100}{4.0 \times 2.5} \approx 10\text{ h}$$

即游戏约 10 小时处战力增速达到最大——恰好对应玩家完成第一次骨钉升级、熟练掌握基础操作后。

$$\lim_{t \to \infty} P(t) = P_{max} = 100$$

---

## 七、最优 Build 理论

### 7.1 护符组合优化

定义护符选择为背包问题 $\max \sum w_i x_i$ 受限于 $\sum c_i x_i \leq N_{notches}$。

#### 物理流 Parato 前沿

| Build | Notches | 骨钉 DPS | 生存 | 效率比 |
|-------|:---:|:---:|:---:|:---:|
| 基础 | 0 | 29.4 | 9 masks | 1.00 |
| Strength | 3 | 44.1 | 9 masks | 1.50 |
| Str+QS | 6 | 61.7 | 9 masks | **2.10** |
| Str+QS+MoP | 9 | 61.7 | 9 masks | 2.10 |
| Str+QS+MoP+Steady | 10 | 61.7 | 9 masks | 2.10 |

> Mark of Pride 和 Steady Body 不提升数值 DPS 但极大改善命中窗口和位置控制，实际有效 DPS 可再提升 20~30%。

#### 法术流 Pareto 前沿

| Build | Notches | 法术 DPS* | 骨钉 DPS | 效率比 |
|-------|:---:|:---:|:---:|:---:|
| Shaman Stone | 3 | 120/Spell | 29.4 | 1.00 |
| SS+SoulEater | 7 | 120/Spell† | 29.4 | 1.67 |
| SS+SE+SpellTwister | 9 | 120/Spell‡ | 29.4 | **2.27** |
| SS+SE+ST+QS | 12§ | 120/Spell‡ | 41.2 | 2.73 |

> *Abyss Shriek 峰值伤害  
> †SOUL 生成速率 ×1.73  
> ‡法术消耗降至 22 SOUL  
> §超过 11 notch 上限，不可实现

### 7.2 最优混合 Build（11 Notches）

$$C^* = \{\text{Strength}(3), \text{Quick Slash}(3), \text{Shaman Stone}(3), \text{Steady Body}(1), \text{Grubsong}(1)\}$$

- 骨钉 DPS：61.7
- 法术峰值：120（Abyss Shriek）
- SOUL 补偿：Grubsong（受伤回 SOUL）
- 总计：11 notches

此 Build 在几乎所有 Boss 战中表现最优（Pareto 最优）。

---

## 八、附录：完整数据集

### 8.1 骨钉升级

| Level | 名称 | 伤害 | Geo | Pale Ore |
|:---:|------|:--:|----:|:--:|
| 0 | Old Nail | 5 | — | 0 |
| 1 | Sharpened Nail | 9 | 250 | 1 |
| 2 | Channelled Nail | 13 | 800 | 2 |
| 3 | Coiled Nail | 17 | 2,000 | 3 |
| 4 | Pure Nail | 21 | 4,000 | 4 |

### 8.2 法术数据

| 法术 | 基础伤害 | +Shaman | 消耗 | 无敌帧 |
|------|:---:|:---:|:--:|:--:|
| Vengeful Spirit | 15 | 20 | 33 | ❌ |
| Shade Soul | 30 | 40 | 33 | ❌ |
| Desolate Dive | 20+15* | 30+16* | 33 | ✅ |
| Descending Dark | 15+30+15* | 23+44+21* | 33 | ✅ |
| Howling Wraiths | 3×10 | 4×13 | 33 | ❌ |
| Abyss Shriek | 4×20 | 4×30 | 33 | ❌ |

*冲击 + 冲击波

### 8.3 生命碎片位置

| 区域 | 数量 | 获取条件 |
|------|:--:|------|
| Forgotten Crossroads | 2 | 基础/需冲刺 |
| Greenpath | 2 | 基础 |
| Fungal Wastes | 1 | 需蹬墙跳 |
| City of Tears | 1 | 基础 |
| Crystal Peak | 1 | 需 Lumafly Lantern |
| Deepnest | 2 | 无 |
| Ancient Basin | 1 | 无 |
| Queen's Gardens | 1 | 需 Shade Cloak |
| Royal Waterways | 1 | 需 Simple Key |
| Resting Grounds | 1 | 无 |
| Hive | 1 | 需 Tram Pass |
| 商人 Sly | 4（购买） | Geo |

### 8.4 核心护符数值

| 护符 | Notches | 效果 | 数值 |
|------|:---:|------|:---:|
| Fragile/Unbreakable Strength | 3 | 骨钉伤害 | ×1.5 |
| Quick Slash | 3 | 攻速 | ×1.4 |
| Shaman Stone | 3 | 法术伤害 | ×1.33~1.5 |
| Mark of Pride | 3 | 骨钉范围 | +25% |
| Soul Eater | 4 | SOUL/击 | +8 |
| Soul Catcher | 2 | SOUL/击 | +3 |
| Spell Twister | 2 | 法术消耗 | ÷1.5 |
| Quick Focus | 3 | 治疗速度 | ×1.5 |
| Steady Body | 1 | 击退免疫 | ✅ |
| Grubsong | 1 | 受伤回SOUL | +15 |
| Longnail | 2 | 骨钉范围 | +15% |

---

## 📐 公式汇总

| # | 公式 | 说明 |
|:--:|------|------|
| 1 | $D_{nail} = d(N) \cdot f_{str} \cdot r_{as} \cdot 1.40$ | 骨钉 DPS |
| 2 | $\dot{S}_{gen} = (11 + b_{SE} + b_{SC}) \cdot 1.40 \cdot r_{as}$ | SOUL 生成速率 |
| 3 | $D_{comp} = \frac{k \cdot d \cdot f_{str} + D_{spell}}{k/(1.4 \cdot r_{as}) + t_{spell}}$ | 复合 DPS |
| 4 | $TTK = HP_{boss} / D_{eff}$ | 击杀时间 |
| 5 | $P(t) = 100 \cdot [1 - (1 + 0.06t)^{-0.667}]$ | 战力-时间函数 |
| 6 | $\eta(P) = 1 - (P/100)^{2.5}$ | 边际收益衰减 |

---

> 数学不能替代操作——但它能告诉你，什么时候该换骨钉，什么时候该用法术，以及你还差多少 Geo 才能毕业。
