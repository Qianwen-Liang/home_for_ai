# 智能体村 · 阶段 5 ACP 对齐实施计划

> 状态：规划（架构级，待批准后实施）
> 前置：research/acp_alignment_assessment.md 的可行性评估
> 日期：2026-08-24

---

## 一、目标

让村民通过 **Agent Client Protocol（ACP）** 与外部世界互联：
- 村民可被外部编辑器（如 Zed）直接调用
- 村民可作为 Client 调度外部 Agent
- 村落成为"可独立运转、可外部互联"的多智能体系统

## 二、前置结论（来自 ACP 评估）

1. 村民的 Specialist 体系与 ACP 高度同构，主要差距在**传输层**（自定义 → 标准 JSON-RPC over stdio）。
2. 正确姿势是"**加适配层**"而非"重写通信层"。
3. 阶段 A（Agent 适配层）低成本高收益，阶段 B（Client 适配层）中成本，阶段 C（全量迁移）暂缓。

## 三、实施步骤（对应评估文档的阶段 A）

### 步骤 1：实现 ACP Agent 适配层（`village/acp_server.py`）

- 把单个村民（VillagerStore + SpecialistAgent）包装为 ACP Agent
- 实现 ACP 核心方法：`initialize` / `session/new` / `session/prompt`
- 通过 stdio 读写 JSON-RPC 帧

### 步骤 2：村民身份映射

- 村民的 `identity.md`（身份/能力/边界）→ ACP 的能力声明
- 村民的 `skills`（工具白名单）→ ACP 的工具列表
- 村民的 `system_prompt` → ACP 的 agent 描述

### 步骤 3：编辑器集成验证

- 在 Zed 的 `agent_servers` 配置中注册村民
- 验证外部能调用村民、村民能返回结果

### 步骤 4（可选）：ACP Client 适配层

- 让村长（mayor）作为 Client 调度外部 ACP Agent
- 扩展 orchestrator 支持外部 Agent

## 四、风险与依赖

| 项 | 说明 |
|----|------|
| 架构变更 | 属架构级改动，需批准后实施 |
| 新依赖 | 无需新依赖（纯标准库实现 JSON-RPC over stdio） |
| 测试 | 需协议兼容性测试（帧解析、session 生命周期、异常隔离） |
| 外部环境 | 需真实编辑器（如 Zed）验证，沙箱内只能测协议层 |

## 五、验收标准

1. 村民可作为 ACP Agent 被外部调用（stdio JSON-RPC）
2. 村民身份/能力/边界正确映射到 ACP 声明
3. 协议层测试通过（不依赖真实编辑器）

---

*本计划承接 research/acp_alignment_assessment.md，是智能体村"外部互联"的落地路线。*
