"""Lich chay tu dong - port tu BackupScheduler.cs.

Kiem tra danh sach task moi 20 giay (QTimer), den gio hen thi chay tren
thread nen (QThread), khong chan UI.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from .models import BackupTask
from .store import save_tasks
from .worker import SyncWorker

CHECK_INTERVAL_MS = 20_000
DUE_WINDOW = timedelta(minutes=2)  # giong C#: chay trong 2 phut sau gio hen


def parse_slot(slot: str) -> tuple[int, int] | None:
    """'HH:mm' -> (hour, minute), sai dinh dang -> None."""
    try:
        parts = slot.strip().split(":")
        if len(parts) != 2:
            return None
        hour, minute = int(parts[0]), int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None
    except (ValueError, AttributeError):
        return None


def due_slots(task: BackupTask, now: datetime) -> list[str]:
    """Tra ve cac slot den gio chay tai thoi diem `now` (chua chay hom nay).

    Ham thuan (khong phu thuoc Qt) de de unit-test.
    """
    if task.fired_slots_date is None or task.fired_slots_date != now.date():
        task.fired_slots_today.clear()
        task.fired_slots_date = now.date()

    due: list[str] = []
    for slot in task.scheduled_times:
        parsed = parse_slot(slot)
        if parsed is None:
            continue
        hour, minute = parsed
        slot_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        already_due = now >= slot_dt and (now - slot_dt) < DUE_WINDOW
        if already_due and slot not in task.fired_slots_today:
            due.append(slot)
    return due


class QtScheduler(QObject):
    # Phat ra moi khi trang thai 1 task thay doi (bat dau chay / tien do / xong).
    task_changed = pyqtSignal(object)

    def __init__(
        self,
        tasks: list[BackupTask],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._tasks = tasks
        # Map task.id -> (QThread, SyncWorker) dang chay.
        self._running: dict[str, tuple[QThread, SyncWorker]] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    # -- dieu khien -----------------------------------------------------
    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # -- chay task ------------------------------------------------------
    def run_task_in_background(self, task: BackupTask) -> bool:
        """Chay 1 task ngay lap tuc tren thread nen. Tra ve False neu task
        dang chay roi (giong C# bo qua khi task.IsRunning)."""
        if task.is_running or task.id in self._running:
            return False
        task.is_running = True
        task.progress = -1
        self.task_changed.emit(task)

        thread = QThread(self)
        worker = SyncWorker(task.source, task.destination, task.mirror, task=task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.log_line.connect(self._on_worker_log)
        worker.finished.connect(self._on_worker_finished)
        # Don dep thread khi xong.
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.finished.connect(worker.deleteLater)

        self._running[task.id] = (thread, worker)
        thread.start()
        return True

    def cancel_task(self, task: BackupTask) -> bool:
        """Huy task dang chay (neu co)."""
        entry = self._running.get(task.id)
        if entry is None:
            return False
        _thread, worker = entry
        worker.cancel()
        return True

    def shutdown(self) -> None:
        """Huy het task dang chay, cho thread ket thuc (goi khi thoat app)."""
        for _thread, worker in list(self._running.values()):
            worker.cancel()
        for thread, _worker in list(self._running.values()):
            thread.quit()
            thread.wait(5000)

    # -- slots rieng ----------------------------------------------------
    def _on_worker_progress(self, _percent: int) -> None:
        worker = self.sender()
        task = worker._task if isinstance(worker, SyncWorker) else None
        if task is not None:
            task.progress = _percent
            self.task_changed.emit(task)

    def _on_worker_log(self, _line: str) -> None:
        # Log chi tiet cua task hen gio hien khong hien ra UI (giong C#
        # truyen delegate rong). Giu signal de sau nay muon thi noi vao.
        pass

    def _on_worker_finished(self, result: dict) -> None:
        task: BackupTask | None = result.get("task")
        if task is None:
            return
        SyncWorker.apply_result_to_task(task, result)
        task.is_running = False
        task.progress = -1
        self._running.pop(task.id, None)
        save_tasks(self._tasks)
        self.task_changed.emit(task)

    # -- timer ----------------------------------------------------------
    def _on_tick(self) -> None:
        now = datetime.now()
        for task in list(self._tasks):
            if not task.enabled or task.is_running:
                continue
            for slot in due_slots(task, now):
                task.fired_slots_today.add(slot)
                self.run_task_in_background(task)
                break  # moi tick chi kich hoat 1 slot/task (tranh chay chong)
