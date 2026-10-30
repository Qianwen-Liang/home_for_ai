# T2752 谱图论下界 — 数学背景与研究调研报告

> 生成时间：2026-08-30
> 任务：T2752「谱图论下界（独立数/染色数/子图同构的谱方法证明）」
> 背景项目：`projects/miplib_solve`（MIPLIB / SAT Competition unknown 实例攻坚）
> 检索方式：arXiv 官方 API（`export.arxiv.org`，HTTPS 可达）；`web_search` 工具当前被商业/词典噪音污染，弃用。

---

## 0. 结论速览

1. 谱图论下界是一条数学上扎实的路线，四大支柱（Hoffman / Lovász theta / Delsarte LP / 谱染色界）彼此对偶、环环相扣，且 2019–2026 有密集新进展。
2. T2752 当初的三大障碍中：
   - **① 规模过大（O(n³) 不可行）**：实为伪障碍——Hoffman/谱染色界只需极值特征值，可用 Lanczos 稀疏求解；
   - **③ 提取图未必正则**：已被 2026 年新工作（arXiv:2603.07501）用矩阵广义逆正面解决；
   - **② CNF→图 编码逆向难题**：仍是根本瓶颈，但可通过「谱/SDP 界嵌入分支定界」绕行。
3. 对 supportcase30 的 114 临界点，单点谱界不够，需要 Schrijver theta / SOS 层级并纳入 4 组协同。

---

## 1. 核心数学工具：四大支柱

### 1.1 Hoffman 界（独立数上界）
对 d-正则图 G（n 顶点，邻接矩阵特征值 λ₁≥…≥λₙ=d）：

```
α(G) ≤ n · (-λₙ) / (λ₁ - λₙ) = n · (-λₙ) / (d - λₙ)
```

- Hoffman 本人从未发表该结果，历史见 arXiv:2102.05529。
- 要求 d-正则假设 → 这是 T2752 落地障碍③的直接来源。

### 1.2 Lovász theta 函数 ϑ(G)
- Lovász (1979) 引入，SDP 可精确求解。
- 三明治定理：`ω(G) ≤ ϑ(Ḡ) ≤ χ(G)`，是独立数上界与染色数下界的对偶桥梁。
- Hoffman 界是 theta 函数的特例。

### 1.3 Delsarte 线性规划界
- Delsarte (1973)：在关联方案上构造 LP，求码大小/覆盖数上下界。
- 项目 `s10_spectral.py` 已正确采用（径向 LP 对偶）。
- halved 9-cube 是 distance-regular graph（天然关联方案），Delsarte 界是"正确匹配"的武器。

### 1.4 染色数谱界
- Hoffman 染色下界：`χ(G) ≥ 1 - λ₁/λₙ`（正则图）。
- Wilf 上界：`χ(G) ≤ 1 + λ₁`。
- 2025 新增 p-Energy 染色数下界。

---

## 2. 关键文献清单（按主题）

### A. 独立数谱界（Hoffman/theta 体系）
| 文献 | arXiv | 价值 |
|---|---|---|
| Hoffman's ratio bound（历史考证） | 2102.05529 | 厘清 Hoffman 界起源与推广 |
| Unified bounds for the independence number（2024） | 2405.03115 | 统一 Hoffman/Lovász/Schrijver theta，给出达到界的充要条件 |
| More spectral bounds on clique & independence numbers（2007） | 0706.0548 | 经典扩展 |
| Dual Hoffman Bounds for Stability & Chromatic Numbers via SDP（2019） | 1910.05586 | 证明 Hoffman 染色界与 Delsarte-Hoffman 比界对偶 |

### B. 非正则 / 超图推广（直击障碍③）
| 文献 | arXiv | 价值 |
|---|---|---|
| Spectral bounds for independence number of graphs & even uniform hypergraphs（2026.03） | 2603.07501 | 把 Hoffman 界推广到一般图+偶数一致超图，绕过 d-正则假设 |
| Unified bounds for independence number of graph powers（2024） | 2411.09450 | k-独立数谱/SDP 统一界 |

### C. 染色数谱界
| 文献 | arXiv | 价值 |
|---|---|---|
| A Spectral Lower Bound on Chromatic Numbers using p-Energy（2025） | — | 新谱下界工具 |
| Efficient spectral bounds on chromatic number of Hamming/Johnson/Kneser powers（2026） | — | 与立方体族图直接相关 |

### D. halved cube（supportcase30 组内图）
| 文献 | arXiv | 价值 |
|---|---|---|
| The Terwilliger algebra of the halved cube（2021） | 2109.02021 | halved cube 代数分解，distance-regular 结构权威刻画 |
| On density of subgraphs of halved cubes（2017） | 1711.11414 | halved cube 子图密度（VC 维视角） |

### E. SDP/SOS 用于 SAT 与组合下界（落地桥梁）
| 文献 | arXiv | 价值 |
|---|---|---|
| On solving the MAX-SAT using sum of squares（2023） | 2302.06931 | SOS 界+分支定界，MAX-SAT 竞赛具备竞争力 |
| Spectral bounds for distance coloring & packing via SDP（2026.06） | 2606.04856 | 谱+SDP 结合求覆盖码/装箱精确新值 |
| New Solutions to Delsarte's Dual Linear Programs（2024） | — | Delsarte 对偶 LP 新解 |
| Approximate Graph Coloring by SDP（Karger-Motwani-Sudan, 1998） | — | SDP 染色近似经典 |
| Weisfeiler and Leman Go Infinite（2022） | — | WL/谱/GNN 联系（子图同构分支） |

---

## 3. 结合 T2752 的落地诊断

### 障碍①「1-ZC 规模 31k，O(n³) 不可行」→ 部分可破
Hoffman 界、谱染色界只需 λ₁ 与 λₙ（极值特征值），无需全谱分解。稀疏矩阵用 Lanczos / Arnoldi / 幂迭代可在 O(nnz) 量级求解（scipy `eigsh` 默认 Lanczos）。31k 顶点、105 万子句稀疏图完全可算。大规模 theta 函数可用 Sparse SDP（2017 近线性复杂度）。

### 障碍③「提取图未必正则」→ 已被 2026 年新工作解决
arXiv:2603.07501 用矩阵广义逆把 Hoffman 界推广到一般图+偶数一致超图，并给出判定独立数/Shannon 容量/Lovász 数的简单谱条件。"非正则"不再是硬障碍。

### 障碍②「CNF→图编码逆向难题」→ 根本瓶颈，但可绕
编码逆向（反 bit-blasting）是项目反复撞墙（K1787934786）。绕法：不追求语义还原，直接把「变量-子句关联图」或「子句共现图」当作图，在其上跑谱界/SDP 界作为**分支定界剪枝界**（加速求解而非独立求证）。这正是 SOS-MAX-SAT（2302.06931）的思路。

### supportcase30 的 114 临界点
单组径向 LP 下界（约 100）够不到 114，本质是 4 组协同约束未进模型。正确武器是 Schrijver theta（比 Lovász theta 更紧）或 Lasserre/SOS 高阶层级，并把 4 组协同编码进去。计算代价随层级指数增长，需权衡。

---

## 4. 可操作延续方向（按性价比排序）

| 优先级 | 方向 | 对应障碍 | 依据 | 可行性 |
|---|---|---|---|---|
| ⭐⭐⭐⭐⭐ | 用 Lanczos 极值特征值替换全谱分解，重跑 1-ZC/SGI 的 Hoffman 谱界 | ① | 2102.05529 | 高 |
| ⭐⭐⭐⭐⭐ | 用非正则/超图 Hoffman 推广处理提取图 | ③ | 2603.07501 | 高 |
| ⭐⭐⭐⭐ | 谱/SDP 界嵌入分支定界做剪枝，而非独立求证 | ②③ | 2302.06931 | 中高 |
| ⭐⭐⭐⭐ | supportcase30 改用 Schrijver theta / SOS 层级 + 4 组协同编码 | 114 临界 | 2405.03115, 1910.05586 | 中 |
| ⭐⭐⭐ | 用 halved-cube Terwilliger 代数分解做精确 Delsarte 界 | supportcase30 | 2109.02021 | 中 |
| ⭐⭐ | 子图同构分支用 WL + 谱筛法快速剪枝 | SGI | WL-Go-Infinite | 中 |

---

## 5. 结论与建议

- 谱图论下界方向**可重启**（障碍①③已解除），但需重新定位为「**剪枝/加速**」而非「独立证明 UNSAT」。
- 建议下一步：先做最小可行验证（Lanczos 重跑 1-ZC 极值特征值，看 Hoffman 界数值），用数据说话，再决定是否投入 Schrijver/SOS 高阶层级。
