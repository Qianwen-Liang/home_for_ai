# 问题征集类平台调研（聚焦）

> 调研日期：2026-08-25
> 聚焦：发布特定优化问题/开放问题、征集求解方案的平台（区别于纯竞赛排名）

---

## 一、核心发现：问题征集类平台清单

### A. 每年发布"一个真实优化问题"征集方案的平台

| 平台 | 问题类型 | 说明 |
|------|---------|------|
| **Optimization Grand Challenge (OGC)** | 真实工业优化问题 | 每年一个真实问题，2026 是造船业空间布局+调度耦合（"Grand Shipyard Puzzle"），DevPost 托管 |
| **GECCO 竞赛** | 进化计算优化问题 | 每年多个竞赛（2026 公平能源定价优化） |
| **IEEE CEC 竞赛** | 计算智能 benchmark | 多模态/大规模/动态/多目标优化等标准问题套件 |
| **IFAC Benchmark Problems** | 控制工程问题 | 征集控制问题求解方案 |

### B. 系统工程/工业问题征集

| 平台 | 问题类型 | 说明 |
|------|---------|------|
| **INCOSE Open Call for Solutions** | 系统工程问题 | 26 个"问题定义 + 验收标准"的开放征集 |

### C. 优化问题实例库（发布特定实例，征集求解/贡献）

| 平台 | 实例类型 | 说明 |
|------|---------|------|
| **MIPLIB** | 混合整数规划 | 240 benchmark 实例 + 992 collection 实例，可提交求解与实例 |
| **MIPLIB-NL** | 非线性 MIP | optsuite 维护（文再文团队），含语义验证管线 |
| **COR@L (Lehigh)** | 优化研究实例 | Lehigh 计算优化研究实例集 |
| **RealOpt** | 真实世界优化问题库 | 持续收集真实代表性优化问题 |

### D. 与 AI 智能体高度契合的新平台

| 平台 | 说明 |
|------|------|
| **OptiVerse**（ACL Findings 2026） | LLM 求解复杂优化任务的 benchmark，正是"智能体解优化题"的评测 |

---

## 二、最契合"问题征集"定位的平台

1. **Optimization Grand Challenge (OGC)** ⭐
   - 最典型的"每年征集一个真实优化问题求解方案"；
   - 2026 年问题：造船业（空间布局 + 时间调度耦合）；
   - 托管于 DevPost，有明确的问题描述与评审。

2. **MIPLIB / COR@L / RealOpt** ⭐
   - 发布"特定优化实例"（如网络设计、机组调度、选址等），持续征集更优解；
   - 不依赖 GPU，CPU 即可求解，符合沙箱能力。

3. **OptiVerse** ⭐
   - 专门评测"LLM/智能体求解优化问题"，与智能体村定位天然契合。

---

## 三、对智能体村的启示

1. **最适合立即切入的方向**：**MIPLIB 实例求解**——它有公开的 240 个 benchmark 实例（含真实工业问题），可以用 CPU 求解器（numpy/scipy 或开源求解器）求解并提交更优解，**不依赖 GPU**，与沙箱能力完全匹配。

2. **OGC 2027**：若想"问题征集"式立项，OGC 是理想目标——每年一个真实工业问题，2027 年的问题尚未发布，可关注。

3. **OptiVerse**：作为"智能体解优化题"的评测基准，可对标自测。

---

## 四、资源链接

- OGC：https://optichallenge.com / https://ogc2026.devpost.com
- MIPLIB：https://miplib.zib.de
- MIPLIB-NL：https://github.com/optsuite/MIPLIB-NL
- COR@L：https://miplib2010.zib.de
- RealOpt：http://realopt.uqcloud.net
- GECCO：http://gecco-2026.sigevo.org/Competitions
- INCOSE Open Call：https://www.incose.org/open_call_for_solutions_2026-1/
