"""knowledge_store 并发写安全测试（T2840）。

修复的真实缺陷（由 G2 门禁实测捕获）：
  并发写知识库时抛出 `RuntimeError: dictionary changed size during iteration`。
  根因：线程 A 在 _save() 里 `json.dumps(self._data)` 迭代字典，
  线程 B 同时在 store() 里插入新条目 —— 本模块此前**完全没有锁**。

修复要点（缺一不可）：
  1. _save() 持写锁 —— 保护序列化这段读迭代
  2. store() 的「写入字典 + save」整体持同一把锁 —— 否则写字典仍在锁外，
     另一线程的 save 照样会看到尺寸变化
  3. 用 RLock（可重入），因为 store 持锁后还会调用同样加锁的 _save
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.knowledge_store as KS  # noqa: E402


@pytest.fixture()
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(KS, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(KS, "VECTOR_CACHE_FILE", tmp_path / "vectors.json")
    return KS.KnowledgeStore(path=tmp_path / "kb.json")


# ── 1. 并发写不抛异常（核心回归） ───────────────────────

def test_concurrent_store_does_not_raise(store) -> None:
    """回归：并发 store 曾抛 "dictionary changed size during iteration"。"""
    errors: list[str] = []

    def worker(tid: int) -> None:
        for i in range(15):
            try:
                store.store(f"并发{tid}-{i}", f"内容{tid}-{i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发写入抛异常: {errors[:3]}"


def test_concurrent_store_no_data_loss(store) -> None:
    """并发写入后条目数必须等于写入次数（无静默丢失）。"""
    n_threads, n_each = 6, 10

    def worker(tid: int) -> None:
        for i in range(n_each):
            store.store(f"m{tid}-{i}", f"c{tid}-{i}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(store._data) == n_threads * n_each


def test_concurrent_read_write_mixed(store) -> None:
    """读写混合并发：写线程 + 读线程同时跑，不得抛异常。"""
    errors: list[str] = []

    def writer() -> None:
        for i in range(20):
            try:
                store.store(f"w{i}", f"内容{i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"write: {type(exc).__name__}: {exc}")

    def reader() -> None:
        for _ in range(20):
            try:
                store.search("内容", 3, mode="keyword")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"read: {type(exc).__name__}: {exc}")

    threads = ([threading.Thread(target=writer) for _ in range(3)]
               + [threading.Thread(target=reader) for _ in range(3)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"读写并发抛异常: {errors[:3]}"


# ── 2. 锁的存在性（防止将来被移除） ─────────────────────

def test_module_has_write_lock() -> None:
    assert hasattr(KS, "_WRITE_LOCK"), "写锁被移除，并发问题会复发"
    # 必须是可重入锁：store 持锁后会调用同样加锁的 _save
    assert hasattr(KS._WRITE_LOCK, "acquire") and hasattr(KS._WRITE_LOCK, "release")


def test_store_and_save_are_lock_protected() -> None:
    """静态检查：store / _save 都必须在 with _WRITE_LOCK 内操作数据。"""
    import inspect
    store_src = inspect.getsource(KS.KnowledgeStore.store)
    save_src = inspect.getsource(KS.KnowledgeStore._save)
    assert "_WRITE_LOCK" in store_src, "store 未持锁，写字典仍在锁外"
    assert "_WRITE_LOCK" in save_src, "_save 未持锁，序列化会与插入冲突"


# ── 3. 正常功能未受影响 ────────────────────────────────

def test_sequential_store_still_works(store) -> None:
    store.store("串行1", "内容1")
    store.store("串行2", "内容2")
    assert len(store._data) == 2
    assert "串行1" in store.search("串行1", 3, mode="keyword")


def test_same_second_ids_still_deduped(store) -> None:
    """加锁不应破坏此前的同秒 ID 去重。"""
    for i in range(5):
        store.store(f"快速{i}", f"内容{i}")
    assert len(store._data) == 5
    assert len(set(store._data.keys())) == 5
