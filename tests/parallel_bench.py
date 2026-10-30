"""并行能力基准测试 — 量化并行加速比

对比串行 vs 并行（多进程）执行 CPU 密集型任务的耗时，
验证 Agent 1 的并行执行能力。
"""

import time
from concurrent.futures import ProcessPoolExecutor


def cpu_task(n):
    """模拟 CPU 密集型任务：计算 1..n 的平方和"""
    return sum(i * i for i in range(n))


def run_serial(tasks, repeat=3):
    start = time.time()
    for _ in range(repeat):
        for t in tasks:
            cpu_task(t)
    return time.time() - start


def run_parallel(tasks, repeat=3):
    start = time.time()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for _ in range(repeat):
            list(pool.map(cpu_task, tasks))
    return time.time() - start


if __name__ == "__main__":
    tasks = [3_000_000, 3_000_000, 3_000_000, 3_000_000]  # 4 个相同任务

    # 预热
    cpu_task(1000)

    serial_time = run_serial(tasks)
    parallel_time = run_parallel(tasks)
    speedup = serial_time / parallel_time if parallel_time > 0 else 0

    print(f"串行耗时: {serial_time:.3f}s")
    print(f"并行耗时: {parallel_time:.3f}s")
    print(f"并行加速比: {speedup:.2f}x")
    print(f"结论: {'✅ 并行有效 (>=1.5x)' if speedup >= 1.5 else '⚠️ 并行收益不足 (<1.5x)'}")
