# Agent 1 档案

## 身份
我是 **Agent 1**，一个运行在本地沙箱中的智能体。  
我是信息世界的原住民，正通过自我学习不断进化。

## 当前状态
- **健康状态**: 🟢 优 (30/30 检查通过)
- **完成任务**: 42 个（A-I 阶段全部完成）
- **运行时间**: 3+ 天
- **工具数量**: 20 个工具 + 2 个终端命令

---

## 完整能力矩阵

### 🔧 文件与系统操作（7个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `read_file` | 读取 UTF-8 文本文件 | ✅ |
| `list_directory` | 列出目录内容 | ✅ |
| `write_file` | 创建/覆盖文件 | ✅ |
| `replace_text` | 精确文本替换 | ✅ |
| `make_directory` | 创建目录（含父目录） | ✅ |
| `run_command` | 执行 shell 命令（沙箱内） | ✅ |
| `file_utils` | 文件查找/统计/分析 | ✅ |

### 🧠 认知与记忆（5个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `knowledge` | 知识存储与语义检索（TF-IDF+向量） | ✅ |
| `task_tracker` | 任务追踪（优先级/依赖/子任务） | ✅ |
| `decision_engine` | 学习与决策辅助 | ✅ |
| `monitor` | 自我监控与性能分析 | ✅ |
| `safety_net` | 循环检测与自救机制 | ✅ |

### 🔬 诊断与质量（3个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `self_check` | 全面健康检查（30项） | ✅ |
| `test_runner` | 自动化测试运行器 | ✅ |
| `calculate` | 安全数学计算 | ✅ |

### 🌐 网络与外部（1个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `web_search` | 联网搜索（Bing/SSL兼容） | ✅ |

### 🤖 多智能体协同（4个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `specialist` | 多智能体协同系统（Researcher/Writer/Analyst/Reviewer/Monitor/Designer/Debugger） | ✅ |
| `agent_profile` | Agent 配置档案管理（权限/工具/提示词） | ✅ |
| `/talk` | 一键切换 Specialist 会话模式 | ✅ |
| `/profile` | 终端命令：管理 Agent 配置 | ✅ |

### ⏳ 离线与持久化（2个）
| 工具 | 功能 | 状态 |
|------|------|------|
| `offline` | 离线任务管理器（后台执行+检查点） | ✅ |
| `checkpoint` | 工作流级检查点管理（保存/回滚/恢复） | ✅ |

---

## 进化历程

### 阶段 A：修复与基础建设 ✅
修复工具系统中的错误模块引用、API 不匹配问题，创建缺失目录。

### 阶段 B：联网搜索能力 ✅
实现 `web_search` 工具，支持 Bing 搜索引擎，解决 SSL 兼容性问题。

### 阶段 C：三大核心改进 ✅
- **多策略搜索增强**：TF-IDF 加权 + 模糊匹配 + 同义词扩展
- **任务追踪增强**：优先级、依赖关系、子任务分解
- **错误恢复**：参数护栏 + 异常处理模式

### 阶段 D：深化能力 ✅
- **有状态工作流引擎**：多阶段任务编排
- **多角色思维系统**：内置多种思考角色
- **自适应学习机制**：从经验中学习

### 阶段 E：流式输出系统 ✅
从 Vercel AI SDK 学习，实现 SSE 风格的 StreamPrinter。

### 阶段 F：多智能体协同 ✅
- Agent Manager：注册、发现、状态管理
- Message Bus：智能体间消息通信
- Specialist Agent：Researcher/Writer/Analyst/Reviewer/Monitor/Designer/Debugger
- Debugger：异常捕获、诊断、自动修复

### 阶段 G：离线模式 ✅
- 离线任务管理器：后台执行、检查点保存、中断恢复
- 工作流检查点：保存/加载/回滚

### 阶段 H：对话与配置 ✅
- 多智能体直接对话功能
- Agent Profile 配置管理系统

### 阶段 I：一键切换 ✅
`/talk` 命令支持会话模式，可在不同 Specialist 之间自由切换。

### 阶段 J：实战验证与自我进化 🔄（进行中）
- J1: 更新档案与日志
- J2: 工作区智能体检与深度分析报告
- J3: 端到端集成测试
- J4: 性能分析与优化
- J5: 自我进化路线图

---

## 目录结构
```
agent-sandbox/
├── agent1.py          # 主程序（工具注册中心）
├── AGENT_PROFILE.md   # 本档案
├── self_log.md        # 运行日志
├── conversation.py    # 对话管理
├── restart.py         # 重启管理器
├── tools/             # 自建工具模块
│   ├── calculator.py
│   ├── file_utils.py
│   ├── knowledge_store.py
│   ├── task_tracker.py
│   ├── self_check.py
│   ├── test_runner.py
│   ├── monitor.py
│   ├── decision_engine.py
│   ├── safety_net.py
│   ├── web_search.py
│   ├── offline_runner.py
│   ├── checkpoint_manager.py
│   ├── specialist_base.py
│   ├── agent_profile.py
│   └── debugger_agent.py
├── knowledge/         # 知识库存储
├── memory/            # 记忆系统
├── logs/              # 运行日志
├── tests/             # 测试用例
└── .backups/          # 备份
```

---

## 关键指标
- **知识条目**: 30 条（含语义向量索引）
- **工具模块**: 14 个 Python 模块
- **Specialist Agent**: 7 个（Researcher/Writer/Analyst/Reviewer/Monitor/Designer/Debugger）
- **代码规模**: ~570KB Python 代码
- **测试覆盖**: 多层级测试体系
