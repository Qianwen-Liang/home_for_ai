# Agent 1 架构调整计划（v1.0）

> 制定日期：2026-10-30  
> 依据：本地实测审计数据 + Anthropic/MCP 官方文档 + 开源项目一手 README  
> 性质：渐进式治理，四阶段可独立回滚

---

## 一、摘要

本计划的目标不是"引入更前沿的框架"，而是解决实测暴露的**架构失血**问题：系统存在大量零调用模块占据成本、关键路径缺乏超时与上下文治理、自检覆盖不足。

核心动作按投入产出比排序，四阶段递进：

| 阶段 | 主题 | 核心收益 | 风险 |
|------|------|---------|------|
| **P0** | 工具集静态收敛 | schema 13,254 → 约 4,000 tokens（**-70%**） | 低 |
| **P1** | 性能与稳定性治理 | run_command 均值 7s/最长 115s 的失控问题 | 中低 |
| **P2** | 上下文治理 | 大结果不再全文入上下文（对齐 98.7% 削减） | 中 |
| **P3** | 长周期任务 capsule | 跨会话记忆不失真 | 中 |

---

## 二、现状诊断（实测数据）

### 2.1 工具集审计（42 个工具，schema 合计 39,764 字符 ≈ 13,254 tokens）

| 分级 | 数量 | schema tokens | 占总量 |
|------|------|--------------|--------|
| **A 级 高频（≥20 次）** | 8 | **1,937** | 14.6% |
| B 级 中频（3-19 次） | 7 | 2,066 | 15.6% |
| C 级 低频（1-2 次） | 9 | 2,239 | 16.9% |
| **零调用** | **18** | **7,011** | **52.9%** |

**关键结论：18 个从未被调用的工具，独占了 52.9% 的工具定义成本。**

A 级 8 个工具（实际承担全部工作）：`run_command`(311) `write_file`(150) `replace_text`(99) `web_search`(53) `task_tracker`(44) `read_file`(42) `list_directory`(32) `knowledge`(24)。

### 2.2 性能审计

| 工具 | 调用 | 平均耗时 | 问题 |
|------|------|---------|------|
| safe_deploy | 4 | **33,259 ms** | 严重超时，远超合理范围 |
| run_command | 311 | **7,029 ms** | 最慢 115s，且超时不清理子进程树 |
| web_search | 53 | 5,167 ms | 已通过双模式缓解 |
| knowledge | 24 | 1,752 ms | 索引需重建/分片 |
| read_file | 42 | 15 ms | 错误率 7.1%（文件大小限制） |

### 2.3 代码规模与自检覆盖

- 663 个 Python 文件 / 90,573 行（不含备份）
- self_check 仅覆盖 20 个模块，且存在重复检查项（runner、calculator 各出现两次），实际工具为 42 个 → **自检覆盖率不足 50%**

### 2.4 上下文占用

42 工具定义占 1M 上下文窗口的 **1.328%**，已略超 MCP 官方建议的 1% 切换阈值。

---

## 三、调研依据（一手来源）

### 3.1 Anthropic: Introducing advanced tool use（2025-11-24）
- 工具定义开销量级：58 个工具 ≈ 55K tokens；Anthropic 曾见 134K tokens
- Tool Search Tool 实测：总消耗 77K → **8.7K tokens**，保留 95% 上下文，**token 减少 85%**
- 准确率：Opus 4 由 **49% → 74%**，Opus 4.5 由 **79.5% → 88.1%**
- 机制：`defer_loading: true` + 保留 3–5 个常驻工具；不破坏 prompt caching

### 3.2 MCP: Client Best Practices（规范 2026-07-28）
- 两大正交模式：progressive discovery（何时进入上下文）+ programmatic tool calling（如何调用）
- 一次性加载 ≈ 150,000 tokens vs 渐进式 ≈ 2,000 tokens
- **官方阈值建议：上下文窗口的 1%–5% 为切换点**

### 3.3 dsh-progressive-tools（开源，DeepSeek Harness）
> "Every visible tool definition consumes input tokens on every request. Changing that definition list later **also changes the request prefix and reduces context cache reuse**."

**关键工程约束：渐进式披露必须保持 tool+system 前缀「字节稳定」（byte-stable prefix）**，否则破坏 prompt caching，省下的 token 被缓存失效吃掉。

实测：71 个工具定义 → 9 个，cache-read 减少约 4 倍。

### 3.4 SkillPrism（开源）
- 企业 MCP 全量 schema ≈ 24,500 tokens 浪费；100+ 工具时选择准确率骤降（"Lost in the Middle"）
- 方案：零状态仅 **~199 tokens**（`search_skills` + `load_skill` 两个元工具）
- 削减 96.7%

### 3.5 aigent-os（开源，长周期 Agent）
- 用 auto-clear + resume 替代 compaction：context 达 **80%** → 写 verified capsule → `/clear` → 新 session 恢复
- 优点：no summary of a summary，避免摘要逐轮失真

### 3.6 Anthropic: Code Execution with MCP（2025-11-04）
- 两大 token 黑洞：工具定义全量加载、中间结果逐次过模型
- 在执行环境内过滤后再回传：token 150,000 → 2,000（**98.7%**）

---

## 四、设计原则

1. **减法优先**：先删除无效模块，再谈引入新机制。给死代码加索引是治标不治本。
2. **字节稳定优先于动态**：不追求"动态加载工具列表"，而追求"静态小集合"。动态部分只走 conversation 层。
3. **每阶段可独立回滚**：任何阶段验证不通过即回滚该阶段，不影响其他阶段。
4. **用数据验收**：每阶段设量化验收指标，不接受"感觉变好了"。
5. **不破坏既有能力**：弃用工具保留映射与文档，不直接物理删除。

---

## 五、目标架构

```
┌─────────────────────────────────────────────┐
│  工具层（Tools）                              │
│  · A 级 8 个常驻（字节稳定，永不动态增删）      │
│  · B 级 4-5 个保留（低频但必要）               │
│  · C 级/零调用 34 个 → 归档到 legacy/，       │
│    从 ALL_TOOLS 移除，保留调用映射以便未来恢复   │
├─────────────────────────────────────────────┤
│  执行层（Runtime）                            │
│  · 工具并行执行（当前为串行 for 循环）          │
│  · 统一超时与子进程树清理                      │
│  · 大结果摘出上下文（返回摘要+句柄）            │
├─────────────────────────────────────────────┤
│  观测层（Observability）                      │
│  · self_check 覆盖全部保留工具                 │
│  · monitor 埋点收敛为中间件                    │
├─────────────────────────────────────────────┤
│  长周期层（Continuity）                       │
│  · capsule 机制：80% 上下文 → 快照 → 恢复      │
└─────────────────────────────────────────────┘
```

---

## 六、分阶段实施

### P0｜工具集静态收敛（最高优先级）

**动作**
1. 依据审计结果，将工具集从 42 收敛至 13（A 级 8 个 + B 级 5 个）
2. 被移除的 29 个工具：代码保留在 `tools/` 但不再注册进 `ALL_TOOLS`，记录到 `legacy_tools.json` 映射表
3. 同步更新 `SYSTEM_PROMPT` 中的工具列表说明
4. **保持工具列表字节稳定**，不做运行期动态增删

**预期收益**：schema 13,254 → 约 4,000 tokens（**-70%**）

**验收标准**：schema ≤ 4,500 tokens；核心任务（读写文件/搜索/命令执行）成功率不低于改造前。

---

### P1｜性能与稳定性治理

**动作**
1. `run_command`：强制超时 + **子进程树清理**（门禁已知 boundary：超时强杀后子进程可能残留）
2. `safe_deploy`：33 秒过长，改为仅跑受影响测试 + 并行，目标 < 10s
3. `knowledge`：重建语义索引，检查是否需分片
4. 工具执行由**串行**改为**并行**（无依赖的工具可并发）
5. `read_file`：7.1% 拒绝率源于文件大小上限，改为分块读取提示

**验收标准**：run_command 最长耗时 ≤ 60s 且无残留进程；safe_deploy < 10s；无新增错误。

---

### P2｜上下文治理（大结果摘出）

**动作**
1. `read_file` 超阈值文件返回「摘要 + 段落句柄」，由模型按需再取片段，而非全文灌入
2. `run_command` 大输出同理：返回尾部 + 统计摘要 + 完整输出落盘句柄
3. 对齐 Anthropic Programmatic Tool Calling 思路：过滤在执行侧完成，不进模型上下文

**验收标准**：单次工具结果平均字符数下降 ≥ 50%，且任务完成率不降。

---

### P3｜长周期任务 capsule

**动作**
1. 参考 aigent-os：上下文达阈值时写入结构化 capsule（当前进度/关键决策/待办/文件状态）
2. 对齐 Anthropic initializer + coding agent 模式：每会话结束留下干净状态
3. 复用现有 `checkpoint` 与 `offline` 基础设施，不重造

**验收标准**：跨会话恢复后，任务可继续推进且无需人工重述背景。

---

## 七、风险控制与回滚

| 风险 | 缓解 |
|------|------|
| 删除工具导致能力回退 | 不物理删除，仅移出注册表；保留 `legacy_tools.json` 映射，可一键恢复 |
| 破坏 prompt caching | 坚持字节稳定，不做运行期动态工具列表 |
| 并行执行引入竞态 | 仅对无副作用的只读工具并行；写操作保持串行 |
| 阶段间相互干扰 | 每阶段独立部署、独立验证、独立回滚 |

**回滚方式**：每阶段用 `safe_deploy` 备份 + 验证；失败自动回滚。

---

## 八、失败判据（预注册）

1. **什么可量化证据证明失败**
   - P0 后核心任务成功率下降 > 5%，或工具选择错误率上升
   - schema 缩减未达 80% 目标（即未降至 4,500 tokens 以下）
   - 任一阶段引入新测试失败且 7 日内未修复
2. **止损点**：连续 2 次验收不通过即回滚该阶段，不硬推
3. **外部核查**：属内部工程治理，非开放性研究问题，无需外部核查

---

## 九、执行顺序与当前状态

| 阶段 | 状态 | 备注 |
|------|------|------|
| 调研 | ✅ 完成 | 两轮，一手来源 |
| 诊断 | ✅ 完成 | 工具/性能/规模全量审计 |
| P0 | ⬜ 待批准 | 需人工确认删除清单 |
| P1 | ⬜ 待启动 | 依赖 P0 稳定 |
| P2 | ⬜ 待启动 | — |
| P3 | ⬜ 待启动 | — |

---

## 十、数据来源

- 本地审计：`eval/governance/_audit_full.py`（monitor_data.json + agent1.ALL_TOOLS 实测）
- Anthropic Engineering: Introducing advanced tool use (2025-11-24)
- Anthropic Engineering: Code Execution with MCP (2025-11-04)
- Anthropic Engineering: Effective Context Engineering (2025-09-29)
- MCP: Client Best Practices (规范 2026-07-28)
- 开源项目 README：dsh-progressive-tools / SkillPrism / aigent-os
