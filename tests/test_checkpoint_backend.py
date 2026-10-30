"""
E7 — Checkpoint Backend 后端测试（SQLite + File 双后端）
======================================================
验证 StorageBackend 抽象、FileBackend 向后兼容、
SQLiteBackend 功能完整性及后端切换。
"""
import sys
import os
import tempfile
import json
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    sys.path.insert(0, os.getcwd())

from tools.checkpoint_backend import (
    StorageBackend, FileBackend, SQLiteBackend, create_backend,
)
from tools.checkpoint_manager import CheckpointManager


# ── 测试数据 ──────────────────────────────────────────────

SAMPLE_CP = {
    "checkpoint_id": "cp_test_20260723_120000_123456",
    "task_id": "test_task",
    "phase": "init",
    "created_at": "2026-07-23 12:00:00",
    "metadata": {"author": "test"},
    "state": {"key": "value", "count": 42},
}


def _make_cp(cp_id: str, task_id: str = "t", phase: str = "p") -> dict:
    return {
        "checkpoint_id": cp_id,
        "task_id": task_id,
        "phase": phase,
        "created_at": "2026-07-23 12:00:00",
        "metadata": {},
        "state": {"cp": cp_id},
    }


# ── FileBackend 测试 ──────────────────────────────────────


def test_file_save_load():
    """FileBackend 保存+加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        be.save(SAMPLE_CP)
        loaded = be.load(SAMPLE_CP["checkpoint_id"])
        assert loaded["task_id"] == "test_task"
        assert loaded["state"]["key"] == "value"
    print("✅ file save+load: 通过")


def test_file_load_nonexistent():
    """FileBackend 加载不存在的检查点"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        try:
            be.load("cp_nonexistent")
            assert False, "应该抛出 KeyError"
        except KeyError:
            pass
    print("✅ file load 不存在: 通过")


def test_file_list():
    """FileBackend 列出检查点"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        be.save(_make_cp("cp_t1_a", task_id="t1", phase="a"))
        be.save(_make_cp("cp_t1_b", task_id="t1", phase="b"))
        be.save(_make_cp("cp_t2_x", task_id="t2", phase="x"))

        all_cps = be.list()
        assert len(all_cps) == 3

        t1_cps = be.list(task_id="t1")
        assert len(t1_cps) == 2
        assert all(cp["task_id"] == "t1" for cp in t1_cps)
    print("✅ file list: 通过")


def test_file_list_empty():
    """FileBackend 空目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        assert be.list() == []
    print("✅ file list 空: 通过")


def test_file_delete_task():
    """FileBackend 删除任务"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        be.save(_make_cp("cp_del_a", task_id="del_me"))
        be.save(_make_cp("cp_del_b", task_id="del_me"))
        be.save(_make_cp("cp_keep", task_id="keep_me"))

        deleted = be.delete_task("del_me")
        assert deleted == 2
        assert be.count("del_me") == 0
        assert be.count("keep_me") == 1
    print("✅ file delete_task: 通过")


def test_file_clean_old():
    """FileBackend 清理过期检查点"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        be.save(_make_cp("cp_old"))
        cleaned = be.clean_old(max_age_days=0)  # 0 天 = 全部
        assert cleaned >= 1
        assert be.count() == 0
    print("✅ file clean_old: 通过")


def test_file_cleanup_task():
    """FileBackend 保留最近 N 个"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        be.save(_make_cp("cp_k_a", task_id="keep"))
        be.save(_make_cp("cp_k_b", task_id="keep"))
        be.save(_make_cp("cp_k_c", task_id="keep"))
        assert be.count("keep") == 3

        be.cleanup_task("keep", keep=2)
        assert be.count("keep") == 2
    print("✅ file cleanup_task: 通过")


def test_file_count():
    """FileBackend 统计"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        assert be.count() == 0
        be.save(_make_cp("cp_cnt"))
        assert be.count() == 1
    print("✅ file count: 通过")


# ── SQLiteBackend 测试 ────────────────────────────────────


def test_sqlite_save_load():
    """SQLiteBackend 保存+加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        be = SQLiteBackend(db_path)
        try:
            be.save(SAMPLE_CP)
            loaded = be.load(SAMPLE_CP["checkpoint_id"])
            assert loaded["task_id"] == "test_task"
            assert loaded["state"]["key"] == "value"
        finally:
            be.close()
    print("✅ sqlite save+load: 通过")


def test_sqlite_load_nonexistent():
    """SQLiteBackend 加载不存在的检查点"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            try:
                be.load("cp_nonexistent")
                assert False, "应该抛出 KeyError"
            except KeyError:
                pass
        finally:
            be.close()
    print("✅ sqlite load 不存在: 通过")


def test_sqlite_list():
    """SQLiteBackend 列出+筛选"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            be.save(_make_cp("cp_s1_a", task_id="s1", phase="a"))
            be.save(_make_cp("cp_s1_b", task_id="s1", phase="b"))
            be.save(_make_cp("cp_s2_x", task_id="s2", phase="x"))

            all_cps = be.list()
            assert len(all_cps) == 3

            s1_cps = be.list(task_id="s1")
            assert len(s1_cps) == 2
            assert all(cp["task_id"] == "s1" for cp in s1_cps)
        finally:
            be.close()
    print("✅ sqlite list: 通过")


def test_sqlite_list_empty():
    """SQLiteBackend 空数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            assert be.list() == []
        finally:
            be.close()
    print("✅ sqlite list 空: 通过")


def test_sqlite_delete_task():
    """SQLiteBackend 删除任务"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            be.save(_make_cp("cp_sd_a", task_id="del"))
            be.save(_make_cp("cp_sd_b", task_id="del"))
            be.save(_make_cp("cp_sk", task_id="keep"))

            deleted = be.delete_task("del")
            assert deleted == 2
            assert be.count("del") == 0
            assert be.count("keep") == 1
        finally:
            be.close()
    print("✅ sqlite delete_task: 通过")


def test_sqlite_clean_old():
    """SQLiteBackend 清理旧检查点"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            be.save(_make_cp("cp_so"))
            cleaned = be.clean_old(max_age_days=36500)  # ~100 年，不清理
            # 新创建的检查点不应被清理
            assert be.count() >= 1
        finally:
            be.close()
    print("✅ sqlite clean_old: 通过")


def test_sqlite_cleanup_task():
    """SQLiteBackend 保留最近 N 个"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            be.save(_make_cp("cp_sk_a", task_id="keep"))
            be.save(_make_cp("cp_sk_b", task_id="keep"))
            be.save(_make_cp("cp_sk_c", task_id="keep"))
            assert be.count("keep") == 3

            be.cleanup_task("keep", keep=2)
            assert be.count("keep") == 2
        finally:
            be.close()
    print("✅ sqlite cleanup_task: 通过")


def test_sqlite_save_overwrite():
    """SQLiteBackend INSERT OR REPLACE — 相同 ID 覆盖"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            cp1 = _make_cp("cp_ov", task_id="t", phase="v1")
            cp2 = _make_cp("cp_ov", task_id="t", phase="v2")

            be.save(cp1)
            be.save(cp2)  # 应覆盖

            loaded = be.load("cp_ov")
            assert loaded["phase"] == "v2"
        finally:
            be.close()
    print("✅ sqlite overwrite: 通过")


def test_sqlite_count():
    """SQLiteBackend 统计"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        try:
            assert be.count() == 0
            be.save(_make_cp("cp_cnt"))
            assert be.count() == 1
        finally:
            be.close()
    print("✅ sqlite count: 通过")


# ── CheckpointManager 后端切换 ────────────────────────────


def test_manager_with_file_backend():
    """CheckpointManager + FileBackend（向后兼容）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = FileBackend(directory=tmpdir)
        cm = CheckpointManager(backend=be)
        cp_id = cm.save(task_id="cm_file", phase="test", state={"a": 1})
        data = cm.load(cp_id)
        assert data["state"]["a"] == 1
    print("✅ manager + file backend: 通过")


def test_manager_with_sqlite_backend():
    """CheckpointManager + SQLiteBackend"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        cm = CheckpointManager(backend=be)
        try:
            cp_id = cm.save(task_id="cm_sqlite", phase="test", state={"b": 2})
            data = cm.load(cp_id)
            assert data["state"]["b"] == 2

            cps = cm.list(task_id="cm_sqlite")
            assert len(cps) == 1
            assert cps[0]["checkpoint_id"] == cp_id
        finally:
            be.close()
    print("✅ manager + sqlite backend: 通过")


def test_manager_rollback_sqlite():
    """CheckpointManager + SQLiteBackend rollback"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        cm = CheckpointManager(backend=be)
        try:
            cm.save(task_id="rb_sql", phase="before", state={"v": 1})
            cm.save(task_id="rb_sql", phase="after", state={"v": 2})

            state = cm.rollback("rb_sql", "before")
            assert state["v"] == 1
        finally:
            be.close()
    print("✅ manager rollback sqlite: 通过")


def test_manager_delete_sqlite():
    """CheckpointManager + SQLiteBackend delete_task"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        cm = CheckpointManager(backend=be)
        try:
            cm.save(task_id="del_sql", phase="x", state={})
            deleted = cm.delete_task("del_sql")
            assert deleted == 1
            assert cm.list("del_sql") == []
        finally:
            be.close()
    print("✅ manager delete sqlite: 通过")


def test_manager_clean_sqlite():
    """CheckpointManager + SQLiteBackend clean_all"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = SQLiteBackend(os.path.join(tmpdir, "test.db"))
        cm = CheckpointManager(backend=be)
        try:
            cm.save(task_id="cln_sql", phase="x", state={})
            cleaned = cm.clean_all(max_age_days=36500)  # 不清理新数据
            assert isinstance(cleaned, int)
        finally:
            be.close()
    print("✅ manager clean sqlite: 通过")


# ── 工厂函数 ─────────────────────────────────────────────


def test_create_backend_file():
    """create_backend('file') → FileBackend"""
    with tempfile.TemporaryDirectory() as tmpdir:
        be = create_backend("file", path=tmpdir)
        assert isinstance(be, FileBackend)
    print("✅ create_backend file: 通过")


def test_create_backend_sqlite():
    """create_backend('sqlite') → SQLiteBackend"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        be = create_backend("sqlite", path=db_path)
        assert isinstance(be, SQLiteBackend)
        be.close()
    print("✅ create_backend sqlite: 通过")


def test_create_backend_default():
    """create_backend() 默认 → FileBackend"""
    be = create_backend()
    assert isinstance(be, FileBackend)
    print("✅ create_backend default: 通过")


# ── 抽象基类 ──────────────────────────────────────────────


def test_storage_backend_abc():
    """StorageBackend 是抽象基类，不能直接实例化"""
    try:
        StorageBackend()
        assert False, "ABC 应该不能实例化"
    except TypeError:
        pass
    print("✅ StorageBackend ABC: 通过")


if __name__ == "__main__":
    all_tests = [
        test_file_save_load,
        test_file_load_nonexistent,
        test_file_list,
        test_file_list_empty,
        test_file_delete_task,
        test_file_clean_old,
        test_file_cleanup_task,
        test_file_count,
        test_sqlite_save_load,
        test_sqlite_load_nonexistent,
        test_sqlite_list,
        test_sqlite_list_empty,
        test_sqlite_delete_task,
        test_sqlite_clean_old,
        test_sqlite_cleanup_task,
        test_sqlite_save_overwrite,
        test_sqlite_count,
        test_manager_with_file_backend,
        test_manager_with_sqlite_backend,
        test_manager_rollback_sqlite,
        test_manager_delete_sqlite,
        test_manager_clean_sqlite,
        test_create_backend_file,
        test_create_backend_sqlite,
        test_create_backend_default,
        test_storage_backend_abc,
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("🧪 E7 — Checkpoint Backend 后端测试")
    print("=" * 60)

    for test in all_tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"❌ {test.__name__}: {e}")
            traceback.print_exc()

    print("=" * 60)
    print(f"🎉 完成: {passed} 通过, {failed} 失败  ({passed + failed} 总计)")
    print("=" * 60)
