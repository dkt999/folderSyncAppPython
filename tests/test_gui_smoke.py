"""Smoke test GUI offscreen: QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_gui_smoke.py -q"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from PyQt6.QtCore import QTime  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from qfluentwidgets import Theme, setTheme  # noqa: E402

from foldersync.models import BackupTask  # noqa: E402
from foldersync.scheduler import QtScheduler  # noqa: E402
from foldersync.ui.main_window import MainWindow  # noqa: E402
from foldersync.ui.mounts_page import MountsPage  # noqa: E402
from foldersync.ui.task_edit_dialog import TaskEditDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    setTheme(Theme.LIGHT)
    yield app


def _wait_until(predicate, timeout_ms=15000):
    from PyQt6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402

    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            return False
        QCoreApplication.processEvents()
    return True


def test_main_window_creates(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("foldersync.ui.main_window.load_tasks", lambda: [])
    monkeypatch.setattr("foldersync.ui.main_window.save_tasks", lambda tasks: None)
    monkeypatch.setattr("foldersync.scheduler.save_tasks", lambda tasks: None)
    win = MainWindow()
    assert win.manual_page is not None
    assert win.tasks_page is not None
    assert win.settings_page is not None
    assert win.mounts_page is not None
    assert isinstance(win.mounts_page, MountsPage)
    assert win.tasks_page.table.columnCount() == 9
    win._quit()
    # Don dep tuong minh de tranh crash luc teardown (GC xoa widget lung tung).
    from PyQt6.QtWidgets import QApplication as _QA  # noqa: E402

    win.deleteLater()
    _QA.processEvents()


def test_mounts_page_form_validation(qapp):
    page = MountsPage()
    # Form rong -> khong validate duoc.
    assert page._validate_form() is None
    # Dien sai dinh dang share.
    page.source_edit.setText("192.168.1.10/du-lieu")
    page.target_edit.setText("/mnt/dl")
    assert page._validate_form() is None
    # Dien dung share nhung thieu user (khong phai guest).
    page.source_edit.setText("//192.168.1.10/du-lieu")
    assert page._validate_form() is None
    # Dien du -> validate ok.
    page.user_edit.setText("fen")
    assert page._validate_form() == ("//192.168.1.10/du-lieu", "/mnt/dl", "fen", False)
    # Guest mode khong can user.
    page.guest_check.setChecked(True)
    page.user_edit.setText("")
    assert page._validate_form() == ("//192.168.1.10/du-lieu", "/mnt/dl", "", True)
    # Chua mount thu -> khong co tested_key.
    assert page._tested_key is None
    page.deleteLater()


def test_task_edit_dialog(qapp, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dlg = TaskEditDialog(None)
    dlg.name_edit.setText("Test task")
    dlg.src_edit.setText(str(src))
    dlg.dst_edit.setText(str(tmp_path / "dst"))
    dlg.mirror_check.setChecked(True)
    dlg.time_edit.setTime(QTime(8, 30))
    dlg._add_time()
    dlg.time_edit.setTime(QTime(18, 0))
    dlg._add_time()
    dlg._on_save()  # = bam nut Luu

    t = dlg.result_task
    assert t.name == "Test task"
    assert t.source == str(src)
    assert t.mirror is True
    assert t.scheduled_times == ["08:30", "18:00"]
    assert t.enabled is True


def test_scheduler_runs_due_task(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("foldersync.scheduler.save_tasks", lambda tasks: None)
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "f.txt").write_text("data")

    now = datetime.now()
    task = BackupTask(
        name="Hen gio",
        source=str(src),
        destination=str(dst),
        scheduled_times=[now.strftime("%H:%M")],
    )
    changed = []
    sched = QtScheduler([task])
    sched.task_changed.connect(lambda t: changed.append((t.is_running, t.progress)))

    sched._on_tick()  # gia lap timer 20s tick dung gio hen
    assert task.is_running

    ok = _wait_until(lambda: not task.is_running, timeout_ms=20000)
    assert ok, "task khong ket thuc"
    assert task.last_run_success is True
    assert task.last_run_summary == "Thanh cong"
    assert (dst / "f.txt").read_text() == "data"
    assert any(running for running, _p in changed)
    sched.shutdown()
    sched.deleteLater()
    from PyQt6.QtWidgets import QApplication as _QA2  # noqa: E402

    _QA2.processEvents()
