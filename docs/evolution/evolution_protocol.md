# 🧬 Agent 1 进化协议 v1.0

Gödel 自举闭环的常态化运行机制。让自我进化从"被动响应"变为"主动飞轮"。

## 一、触发时机

每次**阶段完成**或**重大变更**后，运行一次进化循环。触发点：
- P0~P4 各阶段完成后
- 修复一个 bug 后
- 新增一个工具后
- 检测到健康分下降时

## 二、循环步骤（固定 6 步）

```
1. inspect   — self_improver.inspect：系统诊断，识别问题
2. generate  — improvement_generator.generate：生成改进创意（按优先级）
3. 决策      — evolution_strategy.check_action：检查操作是否被当前策略允许
4. 执行      — self_improver.run_cycle：运行循环（首次 dry_run 预演）
5. 评估      — effect_evaluator.evaluate：前后对比，拒绝无增益改动
6. 审计      — audit_log.log：记录决策（who/what/why/effect）
```

## 三、决策规则（采纳/拒绝标准）

- **采纳**：effect_evaluator 显示净增益 ≥ +1，且无退化信号
- **拒绝**：净增益 ≤ 0，或 cycle_tracker 检测到退化
- **回滚**：采纳后出现退化，用 safe_deploy.rollback 回滚

## 四、防退化机制

- `cycle_tracker.check`：每轮后检查退化信号
- `evolution_strategy.guardrails`：按健康分切换 激进/保守/维护 模式
- 健康分 < 70 → 自动切保守模式（禁止架构变更、需人工审批）

## 五、护栏（当前策略：激进 aggressive）

| 约束 | 激进 | 保守 | 维护 |
|------|------|------|------|
| 自动部署 | ✅ | ❌ | ❌ |
| 架构变更 | ✅ | ❌ | ❌ |
| 新增依赖 | ✅ | ❌ | ⚠️ |
| 需人工审批 | ❌ | ✅ | ✅ |

## 六、当前进度（截至 2026-08-15）

| 指标 | 当前 | 目标 |
|------|------|------|
| 进化循环数 | 1（dry_run 验证） | ≥20 |
| 审计记录 | 5 条 | 100% 覆盖 |
| 健康分 | 88 | ≥90 |
| 知识条目 | ~5 条 | ≥100 |

> 本协议由 Agent 1 在 P3 阶段确立，作为自我进化的"宪法"。
