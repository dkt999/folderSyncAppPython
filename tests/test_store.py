"""Test store (JSON) va scheduler logic thuan."""
from datetime import datetime

from foldersync.models import BackupTask
from foldersync.scheduler import due_slots, parse_slot
from foldersync.store import load_tasks, save_tasks


def test_roundtrip(tmp_path):
    path = tmp_path / "tasks.json"
    tasks = [
        BackupTask(name="Mang ve may", source="/mnt/share", destination="/home/u/bk",
                   mirror=True, scheduled_times=["08:00", "18:30"],
                   last_run_summary="Thanh cong"),
        BackupTask(name="Task 2"),
    ]
    save_tasks(tasks, path)
    loaded = load_tasks(path)
    assert len(loaded) == 2
    assert loaded[0].name == "Mang ve may"
    assert loaded[0].source == "/mnt/share"
    assert loaded[0].mirror is True
    assert loaded[0].scheduled_times == ["08:00", "18:30"]
    assert loaded[0].last_run_summary == "Thanh cong"
    # Truong runtime khong luu.
    assert loaded[0].is_running is False
    assert loaded[0].progress == -1


def test_load_missing_file_returns_empty(tmp_path):
    assert load_tasks(tmp_path / "khong-co.json") == []


def test_load_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{ khong phai json !!!")
    assert load_tasks(path) == []


def test_parse_slot():
    assert parse_slot("08:00") == (8, 0)
    assert parse_slot("23:59") == (23, 59)
    assert parse_slot("8:5") == (8, 5)
    assert parse_slot("24:00") is None
    assert parse_slot("abc") is None
    assert parse_slot("") is None


def test_due_slots():
    task = BackupTask(scheduled_times=["08:00", "18:30"])
    # Truoc gio hen -> khong den.
    assert due_slots(task, datetime(2026, 10, 19, 7, 59, 50)) == []
    # Dung gio hen -> den. Scheduler se danh dau slot da chay:
    assert due_slots(task, datetime(2026, 10, 19, 8, 0, 10)) == ["08:00"]
    task.fired_slots_today.add("08:00")
    # Trong 2 phut sau gio hen -> van den (chong bo lo khi timer tre).
    assert due_slots(task, datetime(2026, 10, 19, 18, 31, 30)) == ["18:30"]
    task.fired_slots_today.add("18:30")
    # Qua 2 phut -> bo lo, khong chay nua.
    assert due_slots(task, datetime(2026, 10, 19, 18, 35, 0)) == []
    # Slot da chay hom nay -> khong chay lai.
    assert due_slots(task, datetime(2026, 10, 19, 8, 0, 20)) == []
    # Sang ngay hom sau -> reset, chay lai duoc.
    assert due_slots(task, datetime(2026, 10, 20, 8, 0, 5)) == ["08:00"]


def test_due_slots_disabled_task_still_computed():
    # Scheduler se loc enabled truoc khi goi due_slots (giong C#).
    task = BackupTask(enabled=False, scheduled_times=["08:00"])
    assert due_slots(task, datetime(2026, 10, 19, 8, 0, 5)) == ["08:00"]
