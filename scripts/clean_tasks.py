# -*- coding: utf-8 -*-
"""P2 清理：过滤 memory/tasks.json 中的压力测试污染与占位任务。

用法：
    python scripts/clean_tasks.py --dry-run   # 仅分析，不写入
    python scripts/clean_tasks.py --apply     # 实际写入（先自动备份）
"""
import json
import sys
import shutil
import os

SRC = 'memory/tasks.json'
BAK = '.backups/tasks.json.bak_before_p2_cleanup'

def classify(title):
    """返回 (类别, 是否删除)"""
    t = title or ''
    if '压力测试任务' in t:
        return 'pressure_test', True
    if '超长任务标题' in t:
        return 'long_title', True
    if t in ('系统扩容计划', '完善监控体系', '集成安全网与监控'):
        return 'placeholder', True
    return 'real', False

def main():
    apply_mode = '--apply' in sys.argv

    with open(SRC, encoding='utf-8') as f:
        d = json.load(f)

    # 1. 建立 id -> title 映射，用于检查 parent_id 引用
    id_to_title = {}
    for k, v in d.items():
        tid = v.get('id') or k
        id_to_title[tid] = v.get('title', '')

    # 2. 分类
    to_delete = []  # (key, title, category)
    to_keep = []    # (key, title, category)
    for k, v in d.items():
        title = v.get('title', '')
        cat, should_del = classify(title)
        if should_del:
            to_delete.append((k, title, cat))
        else:
            to_keep.append((k, title, cat))

    # 3. 检查引用完整性：保留任务是否 parent_id 指向被删除任务
    deleted_ids = set(d[k].get('id', k) for k, _, _ in to_delete)
    dangling = []
    for k, title, cat in to_keep:
        v = d[k]
        pid = v.get('parent_id', '')
        if pid and pid in deleted_ids:
            dangling.append((k, title, pid))

    # 4. 报告
    print('=== 分类统计 ===')
    print('总任务数:', len(d))
    print('待删除:', len(to_delete))
    print('保留:', len(to_keep))
    from collections import Counter
    cat_counter = Counter(c for _, _, c in to_delete)
    for c, n in cat_counter.most_common():
        print(f'  删除-{c}: {n}')
    print('--- 保留任务状态分布 ---')
    status_counter = Counter(d[k].get('status', '') for k, _, _ in to_keep)
    for s, n in status_counter.most_common():
        print(f'  {n} {repr(s)}')
    print('--- 悬空 parent_id 引用（保留任务指向已删任务）---')
    if dangling:
        for k, title, pid in dangling:
            print(f'  悬空! {k} {title!r} -> parent {pid}')
    else:
        print('  无')

    # 5. 展示保留任务中"进行中/被阻塞"的关键任务
    print('--- 保留任务中非终态任务 ---')
    active = [(k, v.get('title',''), v.get('status','')) for k, v in d.items()
              if (k, v.get('title',''), 'real') in to_keep
              and v.get('status') in ('进行中', '被阻塞', '待办')]
    for k, title, s in active[:50]:
        print(f'  {k} [{s}] {title!r}')

    if not apply_mode:
        print('\n[DRY-RUN] 未写入。确认后运行: python scripts/clean_tasks.py --apply')
        return

    # 6. 实际写入
    if os.path.exists(BAK):
        print('\n[SKIP] 备份已存在:', BAK)
    else:
        shutil.copyfile(SRC, BAK)
        print('\n[BACKUP] 已备份到', BAK)

    new_d = {k: v for k, v in d.items() if (k, v.get('title',''), 'real') in to_keep}
    # 修正：to_keep 里的 key 是 d 的 key，直接用集合更稳妥
    keep_keys = set(k for k, _, _ in to_keep)
    new_d = {k: v for k, v in d.items() if k in keep_keys}

    with open(SRC, 'w', encoding='utf-8') as f:
        json.dump(new_d, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(SRC) / 1024 / 1024
    print(f'[DONE] 写入完成。任务数 {len(d)} -> {len(new_d)}，文件大小 {size_mb:.3f} MB')

if __name__ == '__main__':
    main()
