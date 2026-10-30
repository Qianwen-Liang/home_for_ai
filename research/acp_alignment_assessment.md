# ACP 协议对齐评估报告

> 评估时间：2026-08-23
> 评估对象：Agent 1 的 Specialist 多智能体体系
> 目标协议：Agent Client Protocol (ACP) —— ReasFlow 所采用的开放协议
> 结论：**建议分阶段对齐，收益明确但需谨慎评估迁移成本**

---

## 1. 背景与动机

调研 ReasFlow（arXiv:2607.14178）时发现，其多智能体架构构建在
[Agent Client Protocol](https://agentclientprotocol.com/)（ACP）之上，扮演双重角色：

- **作为 ACP Agent**：通过 stdio 暴露给编辑器（如 Zed），可被外部工具直接调用；
- **作为 ACP Client**：派生并管理内置专业子智能体，转发消息并打来源标签。

Agent 1 当前拥有自己的 Specialist 体系（Researcher/Writer/Analyst/Reviewer/
Monitor/Designer/Novelist/Debugger/Evolver），通过自定义的 `specialist_base.py`
+ `agent_manager` + `message_bus` + `orchestrator` 协同。本报告评估将其对齐到
ACP 的可行性与迁移成本。

---

## 2. 现状与 ACP 的映射

| Agent 1 现状 | ACP 概念 | 对齐难度 |
|---|---|---|
| `SpecialistRegistry.create(type)` | ACP Agent 工厂 | 低 |
| `SpecialistAgent.process_task(task)` | Agent 处理请求 | 低 |
| `agent_manager`（注册/发现/状态） | Agent 注册与发现 | 中 |
| `message_bus`（消息队列/广播） | ACP 消息路由 | 中 |
| `orchestrator`（分解→分配→汇总） | ACP Client 调度 | 中 |
| `/talk` 会话模式（stdio 交互） | ACP stdio 传输 | 低 |
| `agent_profile`（权限/工具配置） | Agent 能力声明 | 低 |

**核心结论**：Agent 1 的多智能体语义与 ACP 高度同构，主要差距在**传输层**
（自定义 → 标准 JSON-RPC over stdio）和**协议规范**（内部消息格式 → ACP schema）。

---

## 3. 分阶段对齐方案

### 阶段 A：作为 ACP Agent（低成本、高收益）

**目标**：把单个 Specialist 暴露为标准 ACP Agent，可被 Zed 等编辑器直接调用。

**改动点**：
1. 实现 ACP `initialize` / `session/new` / `session/prompt` 等核心方法；
2. 在 `specialist_base.py` 增加一个 `to_acp_server()` 适配层，将
   `process_task` 映射为 ACP 的 prompt 处理；
3. 通过 stdio 读写 JSON-RPC 帧（现有 `runner.py` 已有 subprocess 经验）。

**收益**：
- 获得与 Zed 等编辑器的互操作性，降低外部接入成本；
- 复用生态内工具（无需自建编辑器集成）。

**风险**：低。不改动现有内部架构，仅加适配层。

### 阶段 B：作为 ACP Client（中成本、高收益）

**目标**：让 `orchestrator` 能调度外部 ACP Agent（而非仅内置 Specialist）。

**改动点**：
1. 实现 ACP Client 侧协议（派生子进程、session 管理、消息转发）；
2. `orchestrator` 的 `_get_ready_agents` 扩展为"内置 + 外部 ACP Agent"；
3. `message_bus` 增加对 ACP 消息的序列化/反序列化。

**收益**：
- 打破"只能调度内置 Specialist"的边界，可接入外部专业 Agent；
- 与 ReasFlow 生态互通（理论上可调度其 SurveyAgent/ProverAgent 等）。

**风险**：中。需处理外部进程生命周期、超时、错误隔离。

### 阶段 C：全量迁移（高成本、收益递减）

**目标**：用 ACP 完全替换自定义的 `message_bus` + `agent_manager` 通信层。

**评估结论**：**不建议近期执行**。原因：
1. 现有自定义通信层已稳定且经过多轮进化验证；
2. 全量迁移的收益（协议标准化）不足以抵消迁移风险与回归成本；
3. 保留自定义层 + 增加 ACP 适配层（阶段 A/B）即可获得主要收益。

---

## 4. 成本估算

| 阶段 | 新增代码 | 涉及文件 | 回归风险 | 建议优先级 |
|---|---|---|---|---|
| A（Agent 适配层） | ~300 行 | `tools/acp_server.py`（新增）+ `specialist_base.py` | 低 | 高 |
| B（Client 适配层） | ~500 行 | `tools/acp_client.py`（新增）+ `orchestrator.py` | 中 | 中 |
| C（全量迁移） | ~1000+ 行 | `message_bus` + `agent_manager` 重构 | 高 | 低 |

---

## 5. 前置条件与依赖

1. **新增依赖**：ACP 无强制 Python SDK，可纯标准库实现 JSON-RPC over stdio
   （参考 ReasFlow 的 `acp/server.py` 实现），因此**不引入新依赖**；
2. **测试**：需新增协议兼容性测试（帧解析、session 生命周期、异常隔离）；
3. **权限**：阶段 B 涉及派生外部进程，需确认沙箱允许；
4. **策略**：当前处于保守模式（禁架构变更），阶段 A 属"新增适配层"而非架构变更，
   可论证放行；阶段 B/C 需申请架构变更授权。

---

## 6. 决策建议

1. **近期（低风险）**：实施阶段 A，把 Specialist 暴露为 ACP Agent，作为
   "互操作性探针"，用最小成本验证外部接入价值；
2. **观察后**：若阶段 A 带来真实外部接入需求，再评估阶段 B；
3. **暂缓**：阶段 C（全量迁移）除非出现明确的协议级收益，否则不启动。

**一句话结论**：对齐 ACP 的**正确姿势是"加适配层"而非"重写通信层"**，
先做 Agent 侧（低成本探针），再按需做 Client 侧，全量迁移暂缓。
