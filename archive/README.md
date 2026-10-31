# archive/ — 归档区

本目录存放**已退出活跃职责**但保留供追溯的代码。

## 归档原则

只有同时满足以下条件才允许归档：

1. **无人 import**（AST 级验证，含 `from pkg import sub` 形式）
2. **无人命令行调用**（全仓文本检索，识别 `python scripts/x.py` 入口）
3. **非既有能力交付物**（有明确任务编号的成果不能归档，否则等于撤销成果）

三条缺一条，都不算"死代码"。详见知识卡片《零入向依赖≠死代码，归档需三层验证》。

## 目录结构

| 目录 | 内容 | 归档日期 | 替代物 |
|---|---|---|---|
| `tools/` | `log_rotation.py`（145 行，零引用） | 2026-10-30 | 无（原功能未被使用） |
| `eval_governance/` | 85 个一次性验证脚本（`_verify_*.py` / `_probe_*.py` / `_inspect_*.py` / `_research_*.py`） | 2026-10-30 | `scripts/gate.py`（G1-G5）+ `scripts/test_audit.py` |
| `eval_search/` | 17 个一次性排查脚本（搜索能力重构时期） | 2026-10-30 | `eval/search/runner.py` 等保留件 |

每个子目录下均有 `MANIFEST.json` 记录文件清单与归档理由。

## 为什么要归档这些脚本

`eval/governance/` 曾长期堆积 85 个 `_verify_*.py`。它们共同造成一个后果：

> **看起来做了验证，实际上验证从不重复执行。**

历次治理都"验证"了一遍，但验证逻辑用完即弃、不进回归。这直接导致同类缺陷反复复发——
测试污染知识库被清理过两次仍复发；K1/K2 在基线里悬空三个月无人问。

归档它们，是为了让"哪条检查是活的"这个问题有唯一答案：**`scripts/gate.py`**。

## 回滚方式

```bash
git mv archive/eval_governance/_verify_xxx.py eval/governance/
```

或直接 `git log --follow` 找回原路径。
