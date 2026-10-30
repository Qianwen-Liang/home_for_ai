# 信息/应用数学领域 · 前沿竞技与问题征集平台调研

> 调研日期：2026-08-25
> 调研方式：联网搜索（web_search）

---

## 一、调研结论概览

信息/应用数学领域存在**四类**前沿平台：①竞技求解类（Kaggle 式）；②开放问题/悬赏征集类；③国内数学建模竞赛类；④benchmark/评测类。

---

## 二、竞技求解类平台（Kaggle 式）

| 平台 | 定位 | 特点 |
|------|------|------|
| **Kaggle** | 数据科学/ML 竞赛 | 全球最大，含优化、推荐、预测等数学类赛题 |
| **MIPcc26（Land-Doig MIP 竞赛）** | 混合整数规划求解器竞技 | 应用数学核心，比求解器性能，`mixedinteger.org/2026/competition` |
| **NeurIPS Competition Track** | 学术会议竞赛 | 如 Smart Buildings Challenge（真实世界大规模优化） |
| **IEEE WCCI 2026 Competitions** | 计算智能竞赛 | 进化计算、模糊系统、神经网络等 |
| **Codabench** | 开源 AI benchmark 平台 | 可自建任务、定义数据集与成功指标 |
| **Netflix Prize（历史）** | 工业优化挑战 | 协同过滤/矩阵补全的经典悬赏（$1M） |

**关键发现**：MIPcc 与 NeurIPS 竞赛赛道是"应用数学 + 优化"最直接的竞技入口；Netflix Prize 正是矩阵补全的工业起源。

---

## 三、开放问题 / 悬赏征集类平台

| 平台 | 定位 | 规模 |
|------|------|------|
| **UnsolvedMath** | 数学问题档案 | 8,785 个开放/部分解决/历史问题 |
| **Open Problem Garden** | 开放问题园 | 可读、评论、创建/编辑开放问题 |
| **AIM Problem Lists** | AIM 问题列表 | 维护最新未解决问题列表 |
| **MathOverflow** | 数学问答 | 含"带金钱奖励的开放问题"专题 |
| **Wolfram MathWorld** | 数学百科 | Open Problems 栏目（14,203 条目） |
| **FrontierMath Open Problems（Epoch AI）** | 为 AI 设计的开放问题 | 测试 AI 推进人类数学知识的能力 |

**关键发现**：FrontierMath（Epoch AI）最契合"AI 驱动的数学研究"——专门收集供 AI 系统挑战的开放数学问题。

---

## 四、国内数学建模竞赛类

| 竞赛 | 主办 | 规模/特点 |
|------|------|----------|
| **全国大学生数学建模竞赛（CUMCM）** | 中国工业与应用数学学会 | 国家级，`mcm.edu.cn` |
| **深圳杯数学建模挑战赛** | 深圳尚龙数学中心 | 2025 年 228 所高校、3267 队、6828 人，首次设国际赛道 |
| **华为杯中国研究生数学建模竞赛** | 华为 × 高校 | 研究生顶级赛事 |
| **MathorCup 数学应用挑战赛** | MathorCup 组委会 | 含大数据竞赛赛道 |

**关键发现**：深圳杯、华为杯的赛题多来自**真实工业/社会问题**，是"问题征集"的国内典型。

---

## 五、benchmark / 评测类

| 平台 | 定位 |
|------|------|
| **MIPLIB** | 混合整数规划问题库（真实世界 MIP 实例） |
| **AIME / MATH benchmark** | 数学竞赛题集（当前主要用于 AI 模型评测） |

---

## 六、对智能体村的启示

1. **可对标方向**：
   - **MIPcc / MIPLIB**：NoisyMC-Cert 的矩阵补全与优化，可对标 MIP 求解器竞技；
   - **FrontierMath / Open Problem Garden**：适合"问题征集"式立项——从开放问题库选题，挑战未解决难题；
   - **深圳杯 / 华为杯**：真实工业问题驱动，适合"全村协同解决一个真实建模题"。

2. **最契合的选择**：
   - 若要**竞技对抗**：对标 MIPcc（求解器性能）或 NeurIPS 竞赛（优化挑战）；
   - 若要**问题征集**：从 FrontierMath / UnsolvedMath 的开放问题中选题；
   - 若要**真实落地**：参考深圳杯/华为杯的工业赛题模式，全村协同解一道真实建模题。

---

## 七、资源链接

- MIPcc26：https://www.mixedinteger.org/2026/competition/
- MIPLIB：https://miplib.zib.de/
- FrontierMath：https://epoch.ai/frontiermath/open-problems
- UnsolvedMath：https://www.unsolvedmath.com/
- Open Problem Garden：https://openproblemgarden.org/
- AIM Problem Lists：http://www.aimpl.org/
- MathOverflow（悬赏）：https://mathoverflow.net/questions/66084/
- Codabench：https://www.codabench.org/
- 全国大学生数学建模竞赛：https://www.mcm.edu.cn/
