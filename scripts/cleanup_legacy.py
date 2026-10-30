#!/usr/bin/env python3
"""
cleanup_legacy.py — Debugger 遗留文件清理脚本

安全设计：
  * 默认 dry-run（只打印计划，不执行任何删除/移动）
  * 需显式传 --execute 才会真正落盘
  * 幂等：重复运行不会产生副作用
  * 全程写入 .backups/cleanup_log.txt 审计日志

清理项：
  1. 根目录一次性临时脚本 -> .backups/root_scripts/
  2. 冗余原始 .sanitized.cnf（仅当同目录存在对应 .xz 压缩版时才删除明文）
  3. 归档膨胀的 memory/tasks.json（>100KB 时移到 memory/audit/ 并重建空任务文件）

用法：
  python scripts/cleanup_legacy.py              # 预览
  python scripts/cleanup_legacy.py --execute    # 真正执行
"""
import argparse
import json
import os
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(ROOT, ".backups", "root_scripts")
LOG_PATH = os.path.join(ROOT, ".backups", "cleanup_log.txt")

# 根目录一次性临时脚本（已确认存在）
ROOT_SCRIPTS = [
    "_mdp_final2.py", "_mdp_fix.py", "_mdp_fix2.py", "_mdp_insert.py",
    "_mdp_rebuild.py", "_mdp_restore.py", "_mdp_trace.py", "_mdp_verify.py",
    "_mdp_verify2.py", "_grep_kissat.py", "_check_monitor.py",
]

TASKS_LIMIT = 100_000  # 与 read_file 读取上限一致


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def move_root_scripts(execute: bool) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    moved = 0
    for name in ROOT_SCRIPTS:
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(BACKUP_DIR, name)
        if os.path.exists(dst):
            dst = os.path.join(BACKUP_DIR, name + "." + time.strftime("%Y%m%d_%H%M%S"))
        log(f"{'MOVE' if execute else 'DRY'}  {src}  ->  {dst}")
        if execute:
            shutil.move(src, dst)
        moved += 1
    log(f"根目录临时脚本：共 {moved} 个")


def delete_redundant_cnf(execute: bool) -> None:
    base = os.path.join(ROOT, "projects", "miplib_solve", "instances")
    if not os.path.isdir(base):
        log("实例目录不存在，跳过 .cnf 清理")
        return
    removed = 0
    freed = 0
    for dirpath, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(".sanitized.cnf"):
                continue
            xz = os.path.join(dirpath, fn + ".xz")
            if not os.path.isfile(xz):
                continue  # 无压缩版，保留明文
            src = os.path.join(dirpath, fn)
            sz = os.path.getsize(src)
            log(f"{'DEL' if execute else 'DRY'}  {src}  ({sz / 1e9:.2f} GB, 保留 {fn}.xz)")
            if execute:
                os.remove(src)
            removed += 1
            freed += sz
    log(f"冗余 .sanitized.cnf：共 {removed} 个，可释放 {freed / 1e9:.2f} GB")


def archive_tasks(execute: bool) -> None:
    src = os.path.join(ROOT, "memory", "tasks.json")
    if not os.path.isfile(src):
        log("memory/tasks.json 不存在，跳过")
        return
    sz = os.path.getsize(src)
    if sz <= TASKS_LIMIT:
        log(f"memory/tasks.json 仅 {sz} 字节（<= {TASKS_LIMIT}），无需归档")
        return
    archive_dir = os.path.join(ROOT, "memory", "audit")
    os.makedirs(archive_dir, exist_ok=True)
    dst = os.path.join(archive_dir, f"tasks.archive.{time.strftime('%Y%m%d_%H%M%S')}.json")
    log(f"{'ARCHIVE' if execute else 'DRY'}  {src}  ({sz / 1e6:.2f} MB)  ->  {dst}")
    if execute:
        shutil.move(src, dst)
        with open(src, "w", encoding="utf-8") as f:
            json.dump(
                {"tasks": [], "note": f"历史任务已归档至 {dst}"},
                f, ensure_ascii=False, indent=2,
            )
        log(f"已重建空 tasks.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debugger 遗留文件清理")
    parser.add_argument("--execute", action="store_true", help="真正执行（默认 dry-run）")
    args = parser.parse_args()

    log(f"==== 清理开始（mode={ 'execute' if args.execute else 'dry-run' }）====")
    move_root_scripts(args.execute)
    delete_redundant_cnf(args.execute)
    archive_tasks(args.execute)
    log("==== 清理结束 ====")


if __name__ == "__main__":
    main()
