# 智能体体系治理强制执行化：全方位调研

> 调研日期：2026-10-30
> 调研任务：T2797
> 方法：本地实证审计（可复现命令）+ 外部一手来源（MCP 官方规范、OpenTelemetry、arXiv、开源项目）
> 结论前置：**本项目的问题不是缺标准，是标准没有执行者。** 详见第 2 章的反例。

---

## 一、调研范围

本次调研回答一个具体问题：*要把这套智能体升级为"高鲁棒性/高标准化/高性能/高效率/高度结构化"，应该做逐个模块改造，还是做总领型更新？*

调研分为两条独立证据线，最后交叉验证：

| 证据线 | 内容 |
|---|---|
| **A. 本地实证** | 现有治理资产的真实覆盖度、缺口是否闭合、缺陷复发模式 |
| **B. 外部框架** | 7 层成熟方法论：适应度函数 / 测试隔离 / 契约 / 确定性 / 性能门禁 / 可观测性 / Agent 评估 |

---

## 二、本地实证：三个决定性反例

### 2.1 反例一：契约基线里的缺口悬空未闭合

`eval/governance/contract_baseline.json` 记录了 4 项真实缺口，字段 `fix_in` 指向修复步骤：

| ID | 缺口 | 原定修复 | 实测状态（2026-10-30） |
|---|---|---|---|
| K1 | 7 个工具错误前缀不统一 | 步骤5.2 | ❌ **仍存在** |
| K2 | `run_command` 失败返回中性串 `返回码: N` | 步骤5.2 | ❌ **仍存在** |
| K3 | 0/16 工具提供 `outputSchema` | 步骤2 | ⚠️ 未验证 |
| K4 | 0/16 工具提供 `annotations` | 步骤2 | ⚠️ 未验证 |

实测复现命令与输出：

```python
>>> execute_task_tracker_tool({"action": "invalid_op_xyz"})
'未知操作: invalid_op_xyz'          # 无 ❌ 前缀 → K1 未修
>>> execute_calculator_tool({})
'计算错误: 表达式不能为空'            # 前缀风格不一致 → K1 未修
>>> execute_runner_tool({"command": "cmd_that_does_not_exist_xyz", "timeout": 5})
"...返回码: 1"                       # 无明确失败标记 → K2 未修
```

用户已确认"步骤5.2 已完成"，但 K1/K2 **实际未修**。

**这不是执行者的疏忽，是机制的缺失**：`known_issues` 是一个**静态快照**，没有 `status` 字段、没有断言绑定、没有任何流程会在修复步骤交付时把它变红。基线写了，但没人读。

### 2.2 反例二：同类缺陷已复发至少两次

| 缺陷 | 历史处理 | 本次复现 |
|---|---|---|
| 测试污染生产知识库 | T2654「清理知识库压测数据」 | 发现 **3 个独立泄漏源**（test_stress / test_e2e / test_experience_learner） |
| 测试污染任务库 | T2667「修复 test_stress 污染 monitor 数据」 | `test_stress` 每次运行泄漏 100 条任务，任务库 294→397、进度 95%→66% |

修复方式是"清理现场"而非"堵住源头"，所以必然复发。

### 2.3 反例三：80+ 个一次性脚本构成了治理的"虚假执行力"

`eval/governance/` 目录下存在 **80+ 个一次性脚本**：`_verify_*.py`（27 个）、`_inspect_*.py`、`_probe_*.py`、`_research_*.py`、`_fetch_*.py`。

它们的共同特征：**用完即弃，不进入回归**。历次治理都"验证"了一遍，但验证逻辑没有沉淀为可重复执行的门禁。这正是"每次都治理、缺陷仍复发"的机制解释。

### 2.4 现状盘点（实测数据）

| 维度 | 实测值 | 判断 |
|---|---|---|
| `tools/` 模块总数 | 45 | — |
| 注册进 `ALL_TOOLS` 的工具 | 16 | 契约测试覆盖对象 |
| `LEGACY_TOOLS` 未注册工具名 | 26 | 代码保留、无契约守护 |
| 契约测试结果 | 96 passed / 2 skipped | 覆盖 16 工具 × C1-C6 |
| 契约测试是否有 CI | **无**（无 `.github/workflows` 等任何 CI 配置） | ⚠️ 需手动触发 |
| 全量测试 | 598 passed / 2 failed | 2 个为改动前既有失败 |
| `monitor` 统计 | 1310 调用 / 6 错误（0.5%）/ 均值 3495.6ms | 有数据、无门禁 |
| 性能基线文件 | **无** | 本次 2.6x 提速无处登记，退化无人知 |
| 知识库条目 | 227 | — |

**结构性判断**：资产很全（契约测试、注册表、中间件、错误契约、capsule 都有），但**没有任何一个会在违规时阻止交付**。这是"装饰性治理"（decorative governance）。

---

## 三、外部框架调研（7 层）

### 3.1 层一：架构适应度函数（Architecture Fitness Function）

**核心概念**：Ford / Kua / Parsons 在《Building Evolutionary Architectures》提出——把架构约束写成**可自动执行的客观测试**，使架构"演进"而非"腐化"。适应度函数是"带阈值和自动判定的架构断言"，与单元测试同构，但断言对象是架构属性而非业务逻辑。

**对本项目的映射**：
- 已有：契约测试网（C1-C6）= 工具接口层的适应度函数 ✅
- 缺失：数据隔离、确定性、性能、依赖方向、模块归属 —— **均无适应度函数**

**可复用实践**：开源项目 `australiangreens/ag-arch-rules` 展示了把架构规则写成测试套件的具体形态（依赖方向断言、分层断言）。这类断言的价值在于**用代码表达架构意图**，而非文档。

### 3.2 层二：Hermetic Testing（Google 测试实践）

**核心概念**：测试必须是"密封的"——不依赖网络、不写外部状态、可重复。Google 按资源占用分三级：

| 级别 | 时长上限 | 允许资源 |
|---|---|---|
| Small | 1s（部分标准 200ms） | 单进程、无网络、无磁盘 I/O |
| Medium | 5min（部分 60s） | 单机、可访问 localhost |
| Large | 15min+ | 多机、网络、外部服务 |

**强制化手段**：`mikelane/pytest-test-categories` —— pytest 插件，检查时长上限、资源隔离、测试金字塔比例，其设计原则明确写为 **"No escape hatches"**（不提供豁免开关）。

**对本项目的映射**：
- 本项目**违反密封性**：测试直接写生产 `knowledge/knowledge_store.json`、`memory/tasks.json`
- 本次修复（`tests/conftest.py` autouse fixture）方向正确，但**缺少"事后校验"**——如果将来有新测试绕过 fixture，仍然无人发现
- 缺口：**没有"测试后生产数据指纹比对"这道断言**

### 3.3 层三：契约测试与 Schema 漂移

**MCP 官方规范（2026-07-28）要点**：
- 工具定义必填：`name`（1-128 字符，`[A-Za-z0-9_-.]`）、`inputSchema`
- 可选：`outputSchema`、`annotations`（**规范明确 annotations 默认不可信**，须视为不可信输入）
- 错误分两类：**Protocol Errors**（JSON-RPC 层）与 **Tool Execution Errors**（`isError: true`，供模型自纠）

**本项目对齐度**：`tests/contract/SPEC.md` 已对齐该规范，包含三层错误模型（RETRYABLE/FATAL/REJECTED），设计质量高。

**缺口**：`outputSchema` 与 `annotations` 覆盖率 0/16（K3/K4）——这不是"必须项"，但 `annotations` 承载 `readOnly`/`idempotent`/`destructive` 语义，**是并行执行与自动重试的安全前提**。缺了它，"工具并行化"改造就没有安全边界依据。

**Schema 漂移检测**：`REGAL`（arXiv 2603.03018）提出"注册表即 interface-as-code"，工具规格与执行由同一注册表驱动，从而**缓解 tool drift**（工具实际行为与声明规格脱节）。本项目已有 `tools/registry.py`（T2792 声明式注册表），方向一致，但尚未把"规格 vs 实际行为一致性"作为断言。

### 3.4 层四：确定性验证 vs 统计监控（★本次最重要的外部证据）

arXiv 2608.02464（Real-Time Detection of LLM Agent Failures）给出**量化对比**：

| 方法 | 检出率 | 误报率 | 备注 |
|---|---|---|---|
| 统计监控（回声状态网络 + CUSUM） | 54% | **17%** | 冷启动 AUROC 仅 0.527，需重新校准、不能热迁移 |
| **确定性验证**（从实际工具结果重算声称总数 + 检查必需调用是否发生） | 60%（含覆盖检查 **96%**） | **0/63 = 0%** | 迁移到其他模型 110/110 成功、0/10 误报 |

同论文定义"静默失败"（silent failure）：**工具调用表面成功但信息部分/全部缺失且无任何通知**。审计 15 个工具、7 个失效位点。

项目知识库（K1793345752）已独立得出同一结论：**确定性验证 >> 统计异常检测**。

**对本项目的映射**：
- 本项目已有 `evidence_verifier` / `artifact_validator` / `multi_reviewer` 三个确定性校验器 ✅
- 但**工具层没有确定性验证**：K2（`返回码: 1` 无失败标记）正是"静默失败"的教科书案例——模型可能把失败读成成功
- 缺口：**"工具返回值必须携带机器可判定的成功/失败标记"这道断言**

### 3.5 层五：性能回归门禁

**核心概念**：性能必须像功能一样被门禁化，否则"优化"会悄悄退化。

**可复用工具**：
- `thebrianlopez/perfgate` —— 统计性能门禁 CLI，benchmark + 阈值强制，强调**统计显著性**而非单次比较
- `JSLEEKR/mcpbench` —— MCP server 负载测试，per-tool p50/p95/p99 + stdio/HTTP 传输 + **CI 回归门禁**

**关键工程要点**：性能门禁必须用**分位数（p50/p95）而非均值**，且需控制噪声（多次取中位数）。本项目 `monitor` 目前只记均值（3495.6ms），**均值会被长尾完全污染**——这正是 `safe_deploy` 33s、`run_command` 最长 115s 这类问题被平均值掩盖的原因。

**对本项目的映射**：
- 缺口：**无性能基线文件、无 p50/p95、无回归断言**
- 本次 5.1 的 2.6x 提速若不入基线，下次重构退化 50% 也无人知

### 3.6 层六：Agent 可观测性标准

**OpenTelemetry GenAI 语义约定**（已迁至 `open-telemetry/semantic-conventions-genai`）：

| 类别 | 关键项 |
|---|---|
| 属性 | `gen_ai.tool.name` / `gen_ai.tool.call.arguments` / `gen_ai.tool.call.result` / `gen_ai.agent.name` / `gen_ai.conversation.id` / `gen_ai.usage.*_tokens`（含 cache_read/cache_write） |
| 指标 | **`gen_ai.execute_tool.duration`** / `gen_ai.invoke_agent.duration` / `gen_ai.client.token.usage` |
| 异常 | `gen_ai.client.operation.exception` |
| Span 类型 | `execute_tool` / `invoke_agent` / `create_agent` / `fetch_response` / `memory` |

**学术补充**：
- `GAAT`（arXiv 2604.05119）指出 **"observe-but-do-not-act" 鸿沟**：现有 OTel/Langfuse 把治理做成下游分析而非实时执行。主张声明式实时违规检测（<200ms）+ 分级干预总线
- `Traccia`（arXiv 2607.14309）：遥测 + 语义护栏 + 执行血缘写入哈希 trace ledger（SHA-256 指纹映射 EU AI Act 条款）

**对本项目的映射**：知识库已记录"对齐 OTel 命名、零新增依赖本地实现"的决策。`monitor` 有埋点但**观测不闭环**——记录指标但不触发行动，正是 GAAT 批评的模式。

### 3.7 层七：Agent 评估与提示回归

| 工具 | 能力 |
|---|---|
| `promptfoo` | 声明式配置测试 prompt/agent/RAG，CI 友好，支持红队测试 |
| `langfuse` | 开源 agent evals + observability 一体 |
| `mlflow` | agent/LLM 全生命周期，含评估与监控 |

**对本项目的映射**：项目已有 `Agent1-bench`（T134/T140）与 `tests/agent1_bench`，但**未与门禁联动**——跑完出报告，不阻断交付。

---

## 四、交叉验证：缺口 ↔ 外部成熟解

| 本地缺口（实证） | 外部对应方法论 | 可落地形态 |
|---|---|---|
| K1-K4 悬空未闭合 | 适应度函数 + 基线即看板 | `known_issues` 加 `status` + 测试断言"未关闭即红" |
| 测试写生产数据（复发 2 次） | Google hermetic testing | 测试前后生产路径**指纹哈希比对**断言 |
| ID 冲突静默丢数据 | 确定性/幂等设计 | 唯一性断言 + 并发写测试 |
| K2 静默失败（`返回码: 1`） | arXiv 2608.02464 确定性验证 | 返回值必须含机器可判定成功标记 |
| 无性能基线 | perfgate / mcpbench | p50/p95 基线 JSON + 回归断言 |
| 观测不闭环 | GAAT "observe-but-do-not-act" | 阈值突破 → 阻断/告警/降级 |
| 26 个 legacy 工具无守护 | REGAL 注册表驱动 | 明确"归档"或"纳管"，不留中间态 |
| 无 CI | 适应度函数自动执行 | `scripts/gate.py` 统一入口 |

**结论**：8 个缺口全部能映射到成熟方法论，**无需发明新框架，只需把已有标准接到执行点上**。

---

## 五、门禁设计（G1-G4）

### G1｜数据隔离门禁（hermetic）

- **断言**：任何测试运行前后，`knowledge/knowledge_store.json`、`memory/tasks.json`、`memory/monitor_data.json` 的内容哈希必须不变
- **实现**：conftest 会话级 fixture 计算指纹 → 会话结束比对 → 不一致即 fail 并输出 diff 摘要
- **依据**：Google hermetic testing + 本案 3 处泄漏实证
- **成本**：低（半天）

### G2｜确定性门禁

- **断言**：① 条目 ID 全局唯一（含同秒并发写）② 同一输入重复调用结果稳定 ③ 工具返回值含机器可判定的成功/失败标记
- **实现**：属性测试（hypothesis）+ 并发写用例 + 返回值契约断言
- **依据**：arXiv 2608.02464（确定性 0% 误报 vs 统计 17% 误报）
- **成本**：中（1-2 天）

### G3｜契约漂移门禁

- **断言**：`contract_baseline.json` 中 `status != closed` 的 known_issue 必须使门禁变红；修复则自动摘除
- **实现**：基线加 `status`/`closed_at` 字段；测试读取并断言；修复时更新基线
- **依据**：适应度函数 + REGAL 注册表驱动
- **成本**：低（半天）
- **直接收益**：K1/K2 这类"标记了但没人修"的情况会立刻暴露

### G4｜性能回归门禁

- **断言**：核心路径 p50 退化 > 20% 即 fail；p95 同步记录
- **实现**：bench 输出 JSON 基线（分位数）+ 多次取中位数控制噪声
- **依据**：perfgate 统计门禁 + mcpbench per-tool 分位数
- **成本**：中（1 天）

### 统一入口

`scripts/gate.py`：一条命令跑完 G1-G4，输出红绿清单，**替代 80+ 个一次性脚本**。这才是"高标准化"的实质——约束有落点、违反会红。

---

## 六、反模式警示（本次调研发现）

| 反模式 | 表现 | 后果 |
|---|---|---|
| 装饰性治理 | 有 SPEC.md、有基线、有测试，但不阻断交付 | 缺陷复发 |
| 快照式基线 | `known_issues` 无状态字段 | 缺口永久悬空（K1-K4） |
| 清理而非堵源 | 发现污染就删数据 | 必然复发（已证 2 次） |
| 均值掩盖长尾 | monitor 只记均值 | `safe_deploy` 33s 被 3495ms 均值掩盖 |
| 形容词目标 | "提升鲁棒性/性能" | 不可验收，催生新一次性脚本 |
| 验证脚本一次性 | 80+ `_verify_*.py` | 治理执行力是虚假的 |

---

## 七、路线建议

### 优先级裁决

| 顺序 | 门禁 | 理由 |
|---|---|---|
| **1** | **G1 数据隔离** | 复发 2 次、有现成 fixture、半天成本、最高性价比 |
| **2** | **G3 契约漂移** | 已有基线，只需加状态字段与断言，直接暴露 K1/K2 |
| **3** | **G2 确定性** | 静默丢数据 + 静默失败，两者都是"错误无法被发现"类风险 |
| **4** | **G4 性能** | 有价值但依赖前三者稳定，且需先建立基线 |

### 对"四个高"的改写建议

形容词目标 → 失效模式清单（每条可复现、可验收）：

| 原表述 | 改写为 |
|---|---|
| 高鲁棒性 | 任意工具对 6 类边界输入不得泄漏未包装异常（已有 C4）；失败必须携带机器可判定标记 |
| 高标准化 | 新增工具必须同时提供 TOOL_DEFINITION + 契约断言 + 回归测试，否则门禁红 |
| 高性能 | knowledge 关键词检索 p50 < 0.15s，退化 > 20% 即 fail |
| 高度结构化 | 每个 `tools/` 模块必须处于"注册 / 归档"二态之一，无中间态 |
| 高效率 | 单次门禁全跑 ≤ 3 分钟 |

### 待决事项

1. 26 个 legacy 工具：归档进 `archive/` 还是补契约纳管？（**不留中间态**是原则）
2. 是否允许改造测试基建 + 新增 `scripts/gate.py` 作为唯一入口
3. "标准化"是对齐外部（MCP/OTel）还是内部一致性——当前已对齐 MCP，建议继续但以内部一致性为优先

---

## 八、数据来源

**本地实证**
- `eval/governance/contract_baseline.json`（K1-K4、exemptions、latest_run）
- `tests/contract/SPEC.md`、`tests/contract/test_tool_contracts.py`（96 passed）
- `agent1.py`（`ALL_TOOLS` 16 项 / `LEGACY_TOOLS` 26 项）
- `eval/governance/` 目录（80+ 一次性脚本）
- 知识库 K1793344813 / K1793345752 / K1793344403 / K1793339033

**外部一手来源**
- MCP 官方规范 2026-07-28：Tools 章节、Client Best Practices、Security Best Practices
- OpenTelemetry GenAI Semantic Conventions
- arXiv 2608.02464（确定性验证 vs 统计监控，量化对比）
- arXiv 2604.05119 GAAT（observe-but-do-not-act）
- arXiv 2607.14309 Traccia（遥测治理栈）
- arXiv 2603.03018 REGAL（注册表驱动、tool drift）
- arXiv 2411.05285 AgentOps（AgentOps 分类法）
- Gooogle Testing Blog（Test Sizes / hermetic testing）
- 开源：`mikelane/pytest-test-categories`、`thebrianlopez/perfgate`、`JSLEEKR/mcpbench`、`promptfoo/promptfoo`、`langfuse/langfuse`、`australiangreens/ag-arch-rules`

---

## 九、能力边界（本次调研的局限）

1. 外部框架均来自二手摘要，未逐篇精读原文；"适应度函数"的量化收益无本地数据支撑
2. 未评估 MCP `outputSchema` 强制化的迁移成本（16 工具需逐个改造）
3. OTel 方案受本地依赖限制（`opentelemetry` 系列全部不可用），只能"对齐命名"，无法真正接入
4. 性能门禁的阈值（20%）为经验值，未经本项目实测标定
5. 未调研多智能体协同场景下的门禁（当前系统有 orchestrator/village 等多 agent 组件，本次未覆盖其一致性风险）
