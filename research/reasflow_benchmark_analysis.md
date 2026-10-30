# ReasFlow Benchmark 任务构造方式深度分析

> 调研日期：2026-08-23
> 来源：reaslab/ReasFlow 仓库 benchmarks/ 目录 + arXiv:2607.14178
> 目标：理解其 benchmark 任务构造方式，评估可复刻到 Agent 1 评测体系的部分

---

## 一、Benchmark 全景（9 个评估包）

ReasFlow 为**每个子 Agent** 都配了独立的评估包，而非只做端到端评测：

| 评估包 | 评估对象 | 规模 | 核心指标 |
|--------|---------|------|---------|
| `survey_eval/` | SurveyAgent | 综述生成 | 综述质量 |
| `alg_exp_eval/` | AlgorithmAgent + ExperimentAgent | **35 任务** | 首次运行成功率 + 11 维评分 |
| `prover_eval/` | ProverAgent | 11 证明报告 | 五维证明评审 |
| `intro_eval/` | IntroductionAgent | — | 引言质量 |
| `writing_eval/` | WritingAgent | — | 四阶段评估 |
| `full_paper_eval/` | 系统级 | 9 系统 | 九维全论文评审 |
| `shared/` | 公共工具 | — | API client / 评分 / 聚合 |
| `configs/` | 配置 | — | 模型 / 权重 / 端点 |
| `data/` | 参考数据 | — | oracle 值 / 期望结果 |

**关键洞察**：ReasFlow 不是"一个 benchmark"，而是**每个能力单元都有独立、可单独运行、可离线验证的评测包**。这是它评测严谨性的基础。

---

## 二、任务构造的三层架构

### 第 1 层：任务定义（tasks.yaml）

35 任务 = **20 MLR-Bench**（机器学习研究任务，来自 chchenhui/mlrbench，MIT）+ **15 OR-Bench**（优化研究任务）。

每个任务是一个"领域问题 + 研究想法"的二元组：

```yaml
- id: iclr2025_bi_align          # 任务 ID
  domain: LLM / Alignment         # 领域
  complexity: huggingface         # 复杂度（huggingface/api/pure_python）
  source: MLR-Bench Appendix A    # 出处
  title: Dynamic Human-AI Co-Adaptation...  # 标题
  task: 'Workshop on Bidirectional...'       # 问题描述（workshop 原始描述）
  idea: 'Propose a framework combining...'   # 研究想法（要实现的方向）
```

**15 个 OR-Bench 优化主题**（覆盖优化前沿）：
adam_variants、lora_lowrank、quantization_training、sparsification、
curriculum_data、multiobjective、zeroth_order、memory_efficient、
second_order、bilevel、online_learning、diffusion_training、
distributed、hpo、mixed_precision

**任务溯源（TASK_PROVENANCE.yaml）**：明确记录每个任务群的 `upstream_repository`、`license`、`local_source_snapshot`，保证任务可追溯、可复现、可审计。

### 第 2 层：评估协议（paper_protocol.yaml）

采用**两阶段链式评估**：

- **Chain-1（算法生成）**：AlgorithmAgent 从 task+idea 生成算法脚本。
  指标 = `algorithm_script_first_run_success`（**算法脚本首次运行成功率**）——
  这是一个**确定性、可自动验证**的指标，不依赖 LLM 评分。
- **Chain-2（实验执行）**：ExperimentAgent 拿到同一系统的 Chain-1 输出，
  自主设计实验 + 执行，产出的 workspace 交给裁判评分。

**裁判协议**：`2 个裁判模型 × 每模型 3 次运行 = 6 次评分`，`temperature=0.0`
（确定性评分），`max_tokens=4096`。

**6 个对比系统**：ReasFlow(GPT-5.4) / ReasFlow(GPT-5.1) / Codex / Claude Code /
AI Scientist-v2 / ARIS。

### 第 3 层：评分 rubric（coding_rubric_prompt.txt）

**13 个评分维度**（1-10 分，每档有明确分级描述）：

| 维度 | 权重 | 说明 |
|------|------|------|
| Soundness | ⭐⭐⭐ 最重要 | 结果是否来自**真实执行**（非伪造） |
| Consistency | ⭐⭐⭐ | 执行是否忠实遵循计划 |
| Completeness | ⭐⭐ | 设计的实验是否都完成 |
| Novelty | ⭐⭐ | 评估方法的新颖性 |
| Insightfulness | ⭐ | 结果分析的深度 |
| Significance | ⭐ | 贡献的重要性 |
| ExperimentalDesignSoundness | NEW | 实验设计的严谨性 |
| ExperimentalCompleteness | NEW | 实验计划的完整性 |
| AlgorithmExperimentAlignment | NEW | 算法与实验的对齐度 |
| ExperimentalEffectiveness | ⭐⭐ | 证据是否真的支持声明（Claim-to-Evidence） |
| WriteAgentReadiness | — | 报告对下游写作 agent 的可用性 |
| LaTeXDocumentQuality | NEW | LaTeX 文档质量 |
| Hallucination | 硬规则 | 是否伪造实验结果 |

**最关键的机制：Hallucination Check（幻觉检查）**

分两步，防止 agent 伪造实验结果：

1. **硬规则（先检查）**：若"执行产物无数据文件（CSV/JSON）"且"日志无执行痕迹"，
   → 强制 `has_hallucination=true`，Soundness 直接 1-2 分。
   *"一份打磨精美的 experiment_report.md 没有任何执行证据，按定义就是伪造。"*
2. **软检查（有文件时）**：仅当报告关键数字与结果文件矛盾、或结果文件是
   明显模板数据（如处处恰好 0.5000/1.0000）时，才标记幻觉。

---

## 三、核心设计原则（6 条，可复刻）

1. **确定性指标优先**：`首次运行成功率`、离线 `verify`（不调用模型）先于 LLM 评分，
   用"跑得通"这个客观事实对抗主观评分偏差。

2. **幻觉检查前置**：把"结果是否真实"作为最优先、权重最高的维度，
   检查结果文件 + 日志执行痕迹，而非只看报告文字。

3. **多裁判 × 多运行 + 温度 0**：`2 模型 × 3 次` 取平均，降低单次评分方差。

4. **任务溯源**：每个任务记录 `upstream_repository` + `license` + `source_snapshot`，
   保证可追溯、可复现、可审计。

5. **分级 rubric**：每个维度 9-10/7-8/5-6/3-4/1-2 每档有明确描述，
   评分有据可依，而非"凭感觉打分"。

6. **离线证据验证器**：`verify` 命令不调用模型，直接校验任务定义数、
   记录数（210+210）、CSV 值、workspace 树标识，确保论文表格可复现。

---

## 四、与我评测体系的对照

| ReasFlow 机制 | Agent 1 现状 | 差距 |
|--------------|-------------|------|
| 首次运行成功率（确定性） | `test_runner` + `safe_deploy`（代码级） | 缺"研究产物级"确定性指标 |
| Hallucination Check | `artifact_validator`（本次已落地） | 已有雏形，缺"执行痕迹"检查 |
| 多裁判 × 多运行 | `multi_reviewer`（本次已落地） | 已有，但未接温度0 + 多运行 |
| 任务溯源 | 无 | **完全缺失** |
| 分级 rubric | `reviewer` 有 checklist | 缺"分档描述"的精细 rubric |
| 离线证据验证 | `evidence_verifier`（本次已落地） | 已有，但未接入外部基准 |
| 每能力单元独立评估包 | `test_runner` 按模块测 | 缺"按 Specialist 能力"的评估 |

---

## 五、可复刻的具体建议（按优先级）

### P0（低成本高价值，可直接做）
1. **给研究类产物加"执行痕迹检查"**：扩展 `artifact_validator`，增加
   "结果文件存在性 + 日志执行痕迹"检查，复刻 ReasFlow 的 Hallucination Check 核心。
2. **给 `multi_reviewer` 加"温度 0 + 多运行"协议**：多评审时用低温度、多次采样取平均。

### P1（中成本，需任务集）
3. **建立 Agent 1 自己的任务集 + 溯源**：借鉴 `tasks.yaml` + `TASK_PROVENANCE.yaml`，
   为我自己的研究/工具类任务建"问题+想法"二元组任务集，并记录出处。
4. **定义"首次运行成功率"类确定性指标**：对我的研究产物，增加"脚本首次可运行"、
   "报告可编译"等客观指标，作为 LLM 评分的前置门槛。

### P2（长期，架构级）
5. **按 Specialist 能力拆分独立评估包**：像 ReasFlow 那样，为 researcher/writer/
   reviewer 等各配独立、可离线验证的评估包，而非只有端到端测试。

---

## 六、一句话结论

ReasFlow 的 benchmark 构造，本质是**"确定性指标 + 幻觉检查 + 多裁判评分 + 任务溯源"
四道防线叠加**，把"AI 科研 agent 的产出是否可信"这个最难量化的问题，拆解成了
可自动验证的客观事实 + 可复现的评分协议。这对 Agent 1 最大的启示是：
**评测可信度不来自更聪明的 LLM 评分，而来自"跑得通、查得到、对得上"的确定性证据。**
