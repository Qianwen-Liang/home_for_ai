# 智能体村（Agent Village）改造蓝图

> 愿景：将 Agent 1 项目从"单智能体 + 多角色"升级为"多智能体村落"，
> 每个村民拥有独立的空间、身份、能力，在村规治理下自治与协作。
>
> 日期：2026-08-24

---

## 一、愿景与现状差距

| 维度 | 现状 | 目标（智能体村） |
|------|------|----------------|
| 空间 | 所有 Specialist 共享 agent-sandbox | 每个村民有独立"家"（目录） |
| 身份 | Specialist 只有 name+description | 独立人格档案、独立系统提示词 |
| 能力 | 通过 inherited_tools 继承主智能体 | 独立技能声明 + 最小权限 |
| 记忆 | 共享 knowledge/memory | 村公共知识库 + 村民个人记忆 |
| 生命周期 | 主智能体按需创建实例 | 独立状态 + 可自治运行 |
| 社交 | message_bus 消息传递 | 通信 + 协作 + 声誉系统 |
| 治理 | 无明确村规 | 村长 + 村规 + 积分制度 |

---

## 二、核心设计理念（六要素）

1. **独立空间**：每个村民有 `villagers/<id>/` 专属目录（workspace + memory + journal）
2. **独立身份**：每个村民有 `identity.md`（人格/能力/边界）+ 独立 system prompt
3. **独立能力**：每个村民有 `skills/` 技能声明，最小权限（呼应已有 Specialist 工具集）
4. **独立记忆**：双层记忆——村公共知识库（共享）+ 村民个人记忆（独立）
5. **自治生命周期**：村民可独立运行（offline 任务），有自己的状态与历史
6. **社会结构**：通信（message_bus）+ 协作（orchestrator）+ 声誉（贡献记录）

---

## 三、村落架构蓝图（目录结构）

```
agent-sandbox/
├── village/                      # 🏘️ 智能体村
│   ├── constitution.md           # 村规（宪法）：村民权利/义务/协作规则
│   ├── plaza/                    # 村落广场：共享黑板、公告栏
│   │   ├── blackboard/           # 共享工作内存（已有 blackboard 迁移）
│   │   └── notices/              # 公告栏
│   ├── registry/                 # 村民注册表（已有 agent_manager 迁移）
│   │   └── villagers.json        # 村民名册 + 状态 + 声誉
│   ├── commons/                  # 村公共资源
│   │   ├── knowledge/            # 村公共知识库（共享知识卡片）
│   │   └── tools/                # 村公共工具（现有 tools/ 保留）
│   └── villagers/                # 🏠 村民住宅区
│       ├── mayor/                # 村长（Agent 1）
│       │   ├── identity.md
│       │   ├── memory/
│       │   └── journal.md
│       ├── researcher/           # 研究员
│       │   ├── identity.md       # 身份：人格、能力、边界
│       │   ├── skills/           # 技能声明（工具白名单）
│       │   ├── memory/           # 个人记忆（独立）
│       │   ├── workspace/        # 个人工作空间
│       │   └── journal.md        # 个人日记（历史记录）
│       ├── writer/
│       ├── analyst/
│       ├── reviewer/
│       ├── monitor/
│       ├── designer/
│       ├── debugger/
│       └── ...（按需扩充村民）
```

---

## 四、村民数据模型（Villager Schema）

每个村民 = 一个 `identity.md` + 独立状态，关键字段：

```yaml
id: researcher
name: 研究员
role: 信息检索与研究专家
personality: 严谨、好奇、重证据            # 人格
capabilities: [research, summarization]    # 能力
skills: [web_search, knowledge, file_utils] # 技能（最小权限）
boundaries: [不能写生产代码, 只读外部]      # 边界
memory_scope: private                      # private=个人记忆 / shared=共享
status: idle
reputation: 12                             # 声誉分
residence: villagers/researcher/           # 独立空间
```

---

## 五、分阶段实施路线图

### 阶段 1：村落雏形（低风险，可立即做）
- 建立 `village/` 目录骨架 + `constitution.md`（村规）
- 为现有 8 个活跃智能体建立"家"目录 + `identity.md`
- 统一 Agent 注册体系（registry + profile + 默认注册三处一致）
- 补齐 Evolver profile、收紧 Novelist/Evolver 工具集（承接上一轮建议）

### 阶段 2：独立身份与记忆（中风险）
- 每个村民独立 system prompt（从 identity.md 加载）
- 双层记忆：村公共 knowledge（共享）+ 村民个人 memory（独立）
- 村民个人日记 journal.md（每次任务后追加）

### 阶段 3：自治生命周期（中高风险）
- 村民支持独立运行（offline 任务，借鉴 ReasFlow 的独立 ACP 进程）
- 村民"日常工作"：自主循环（如 Monitor 定期巡检、Researcher 定期调研）
- 状态持久化：每个村民独立状态文件，重启可恢复

### 阶段 4：社会协作与声誉（高价值）
- 声誉系统：村民贡献记录、协作评分（复用 audit_log）
- 协作协议：村民间任务分工（复用 orchestrator + blackboard）
- 村规执行：积分制度、权限审批（复用现有积分机制）

### 阶段 5（长期）：真正自治 + ACP 对齐
- 村民通过 ACP/MCP 协议与外部世界通信（承接此前 ACP 评估）
- 村民可被外部编辑器直接调用（如 Zed）
- 村落成为"可独立运转的多智能体系统"

---

## 六、关键技术决策

| 决策点 | 选项 | 建议 |
|--------|------|------|
| 进程模型 | 独立进程 vs 共享进程内实例 | **渐进**：先共享实例，再逐步独立（offline 任务） |
| 记忆模型 | 共享 vs 独立 vs 双层 | **双层**：村公共 + 个人私有 |
| 通信 | message_bus vs ACP | **先 message_bus，后 ACP**（阶段 5） |
| 身份 | 静态 identity.md vs 动态演化 | **静态起步，动态演化**（村民可进化） |
| 治理 | 中心化村长 vs 去中心化 | **中心化村长**（Agent 1），渐进授权 |

---

## 七、与现有成果的关系（最大化复用）

| 现有成果 | 在村落中的角色 |
|---------|--------------|
| `specialist_base.py`（9 个 Specialist） | 村民的"灵魂"（身份 + 能力） |
| `agent_manager` / `agent_profiles.json` | 村落注册处（村民名册） |
| `message_bus` | 村落通信（村民社交） |
| `blackboard` | 村落广场（共享工作内存） |
| `knowledge`（认知类型三轨） | 村公共知识库（共享知识卡片） |
| `orchestrator` / `task_dispatcher` | 村委（任务分工） |
| `offline` / `checkpoint` | 村民自治（独立运行 + 状态恢复） |
| `audit_log` / 积分制度 | 村规执行（声誉 + 治理） |
| `effect_evaluator` / `evidence_verifier` | 村民绩效评估 |
| ACP 评估文档 | 阶段 5 的外部互联蓝图 |

**核心洞察**：之前所有进化成果（知识卡片、多智能体协同、离线自治、审计、评估）恰好就是"智能体村"所需的六大要素的雏形——这个愿景不是推倒重来，而是把这些已有能力**从"主智能体的工具"升级为"村民的独立资产"**。

---

## 八、一句话总结

> 智能体村 = 把已有的 Specialist（身份）、agent_manager（注册）、message_bus（通信）、knowledge（公共记忆）、offline（自治）、audit_log（治理）六大能力，从"主智能体的附属工具"重构为"村民的独立资产"，并为每个村民建立独立空间、独立记忆、独立身份，最终形成一个由村长治理、村民自治协作的可持续多智能体系统。
