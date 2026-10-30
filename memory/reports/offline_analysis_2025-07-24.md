# 离线功能深度分析报告

> **生成日期**: 2025-07-24  
> **分析者**: Evolver  
> **目标受众**: Debugger Agent  
> **状态**: 待修复

---

## 一、架构概览

```
┌──────────────────────────────────────────────┐
│             offline_runner.py                 │
│         (离线任务管理器 v1.0)                  │
│                                              │
│  submit → execute → status/list/report       │
│            ↓                                 │
│    每阶段自动调用 CheckpointManager           │
│    保存进度 → 支持 pause/resume/cancel        │
└──────────────┬───────────────────────────────┘
               │ 依赖
┌──────────────▼───────────────────────────────┐
│         checkpoint_manager.py                 │
│         (检查点管理器 v1.0)                    │
│                                              │
│  save → load → list → rollback               │
│  delete_task → clean_all                     │
│  持久化：memory/offline/*.json                │
│  持久化：memory/checkpoints/cp_*.json         │
└──────────────────────────────────────────────┘
```

**涉及文件**：

| 文件 | 路径 |
|---|---|
| 离线任务管理器源码 | `agent-sandbox/tools/offline_runner.py` |
| 检查点管理器源码 | `agent-sandbox/tools/checkpoint_manager.py` |
| 离线任务管理器测试 | `agent-sandbox/tests/test_offline_runner.py` |
| 检查点管理器测试 | `agent-sandbox/tests/test_checkpoint_manager.py` |
| 离线任务持久化目录 | `agent-sandbox/memory/offline/` |
| 检查点持久化目录 | `agent-sandbox/memory/checkpoints/` |
| 工具注册入口 | `agent-sandbox/tools/__init__.py`（execute_offline_tool, execute_checkpoint_tool） |

---

## 二、测试结果

| 模块 | 测试数 | 通过 | 失败 | 通过率 |
|---|---|---|---|---|
| **offline_runner** | 14 | 13 | **1** | 93% |
| **checkpoint_manager** | 14 | 8 | **6** | 57% |
| **合计** | 28 | 21 | **7** | 75% |

**运行命令**：
```bash
python -m pytest agent-sandbox/tests/test_offline_runner.py -v
python -m pytest agent-sandbox/tests/test_checkpoint_manager.py -v
```

---

## 三、发现的问题（按严重程度排序）

### 🔴 P0 — Checkpoint Manager：测试与源码 API 严重不匹配（6 个失败）

**这是最严重的问题**。测试文件使用了与源码实现完全不同的 API：

| 测试调用（错误） | 源码实际 API | 问题性质 |
|---|---|---|
| `_manager.list_checkpoints()` | `_manager.list(task_id)` | 方法名不存在 |
| `_manager.load(task_id=..., phase=...)` | `_manager.load(checkpoint_id)` | 参数签名完全不同 |
| `assert isinstance(result, str)` (delete_task) | 返回 `int`（删除数量） | 返回类型断言错误 |
| `assert isinstance(result, str)` (clean_all) | 返回 `int`（清理数量） | 同上 |

**根因分析**：测试文件似乎是为一个更早版本（或不同设计）的 API 编写的，当时可能：
- `load()` 支持 `(task_id, phase)` 二元组查找
- `list_checkpoints()` 是旧方法名
- `delete_task()` 和 `clean_all()` 返回字符串消息而非整数计数

源码后来重构了但测试未同步更新。

**影响范围**：6 个测试用例，涉及基本的增删查功能。

---

### 🟡 P1 — Offline Runner：阶段执行失败不导致任务失败

`test_execute_with_failure` 暴露了设计缺陷。

**源码位置**：`offline_runner.py` 第 172-179 行（大约）

```python
if phase_executor:
    try:
        phase_result = phase_executor(task_id, phase, task.params)
    except Exception as exc:
        phase_result = {
            "error": str(exc),
            "phase": phase,
            "status": "failed",  # ← 仅标记阶段失败
        }
# ❌ 但任务继续执行下一阶段，最终 status = "done"
```

**问题**：阶段执行器抛异常被静默吞掉，任务仍然标记为 `done`。只有 `phase_executor` 外层的异常（如 JSON 序列化失败）才会触发 `status = "failed"`。

**预期行为**：某个阶段执行失败后，任务状态应立即变为 `"failed"`，后续阶段不应继续执行。

---

### 🟢 P2 — 设计局限性

| 问题 | 详情 | 建议 |
|---|---|---|
| **无真实执行器** | `execute_offline_tool` 调用 `_manager.execute()` 时不传 `phase_executor`，只能模拟执行（直接标记各阶段完成），不做实际工作 | 增加 executor 注入机制 |
| **恢复不自动继续** | `resume()` 后需手动调 `execute`，不会自动从上次阶段继续 | resume 内部自动触发 execute |
| **无超时机制** | 长时间运行的任务没有超时控制 | 增加 `timeout` 参数 |
| **无重试策略** | 阶段失败后无自动重试 | 增加 `max_retries` 参数 |
| **清理策略简单** | 每个任务保留最近 10 个检查点，但每次 `save()` 都触发清理扫描 | 改为惰性清理或定时清理 |

---

## 四、离线功能能力矩阵

| 能力 | 状态 | 备注 |
|---|---|---|
| 任务提交/持久化 | ✅ 正常 | JSON 文件存储到 `memory/offline/` |
| 阶段式执行 | ✅ 正常 | 支持自定义阶段列表 |
| 检查点自动保存 | ✅ 正常 | 每阶段完成后自动保存 |
| 暂停/恢复 | ✅ 正常 | 需手动恢复后重新执行 |
| 取消任务 | ✅ 正常 | 实质是标记为 paused |
| 进度追踪 | ✅ 正常 | 0.0~1.0 浮点 + 进度条 |
| 报告生成 | ✅ 正常 | 结构化报告含时间线和各阶段结果 |
| 回滚到历史阶段 | ✅ 正常 | checkpoint_manager 支持 |
| 过期检查点清理 | ✅ 正常 | 按天数清理 |
| **真实工具调用执行** | ❌ 缺失 | 无 phase_executor 注入 |
| **阶段失败传播** | ❌ Bug | 被静默吞掉 |
| **自动恢复执行** | ❌ 缺失 | resume 不会自动继续 |
| **超时控制** | ❌ 缺失 | 无 |
| **阶段重试** | ❌ 缺失 | 无 |

---

## 五、修复建议（供 Debugger 参考）

### 优先级排序

| 优先级 | 问题 | 修复文件 | 预计工时 |
|---|---|---|---|
| **P0** | checkpoint_manager 测试 API 不匹配 (6 个失败) | `tests/test_checkpoint_manager.py` | 中 |
| **P1** | offline_runner 阶段失败传播 | `tools/offline_runner.py` | 小 |
| **P2** | 设计增强（执行器注入等） | `tools/offline_runner.py` | 大 |

### P0 具体修复方向

1. `_manager.list_checkpoints()` → `_manager.list(task_id)`，或反向在源码中添加 `list_checkpoints` 别名
2. `_manager.load(task_id=..., phase=...)` → 先 `list(task_id)` 遍历找到匹配 phase 的 checkpoint，再用 `_manager.load(checkpoint_id)` 加载
3. `assert isinstance(result, str)` → `assert isinstance(result, int)`（delete_task/clean_all 返回计数）
4. 或者反向修改源码使其匹配测试 API（如果测试 API 更合理）

### P1 具体修复方向

在 `offline_runner.py` 的阶段循环中增加：
```python
if phase_result.get("status") == "failed":
    task.status = "failed"
    break  # 停止执行后续阶段
```

---

## 六、附录：原始命令行输出

### test_offline_runner.py（13/14 通过）

```
test_submit_task .......................... PASSED
test_submit_with_custom_phases ............ PASSED
test_execute_task ......................... PASSED
test_pause_and_resume_task ................ PASSED
test_cancel_task .......................... PASSED
test_list_tasks ........................... PASSED
test_get_status ........................... PASSED
test_get_report ........................... PASSED
test_execute_with_failure ................. FAILED  ← P1
test_submit_duplicate_id .................. PASSED
test_execute_nonexistent_task ............. PASSED
test_pause_nonexistent_task ............... PASSED
test_resume_nonexistent_task .............. PASSED
test_cancel_nonexistent_task .............. PASSED
```

### test_checkpoint_manager.py（8/14 通过）

```
test_save_checkpoint ...................... PASSED
test_save_multiple_checkpoints ............ PASSED
test_load_checkpoint ...................... FAILED  ← API 不匹配
test_list_checkpoints ..................... FAILED  ← API 不匹配
test_rollback ............................. PASSED
test_delete_task_checkpoints .............. FAILED  ← 返回类型断言错误
test_clean_all ............................ FAILED  ← 返回类型断言错误
test_save_empty_state ..................... PASSED
test_save_large_state ..................... PASSED
test_save_unicode_state ................... PASSED
test_load_nonexistent_checkpoint .......... PASSED
test_rollback_nonexistent_phase ........... PASSED
test_delete_nonexistent_task .............. FAILED  ← 返回类型断言错误
test_clean_all_no_expired ................. FAILED  ← 返回类型断言错误
```

---

> **请 Debugger Agent 按 P0 → P1 → P2 顺序处理。如有疑问可查阅对应源码文件。**
