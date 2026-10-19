"""Worker chay dong bo tren thread nen, phat signal ve UI thread."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from PyQt6.QtCore import QObject, pyqtSignal

from .models import BackupTask
from .sync_engine import RsyncRunner, SourceNotFoundError, SyncCancelled


class SyncWorker(QObject):
    """Chay 1 lan dong bo (cho task hen gio hoac dong bo thu cong).

    finished phat ra dict:
      {"task": BackupTask|None, "exit_code": int|None, "success": bool,
       "cancelled": bool, "error": str|None}
    """

    progress = pyqtSignal(int)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(
        self,
        source: str,
        dest: str,
        mirror: bool,
        task: BackupTask | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._mirror = mirror
        self._task = task
        self._runner = RsyncRunner()
        self._cancel_event = threading.Event()

    def run(self) -> None:
        result: dict = {
            "task": self._task,
            "exit_code": None,
            "success": False,
            "cancelled": False,
            "error": None,
        }
        try:
            exit_code = self._runner.run_with_progress(
                self._source,
                self._dest,
                self._mirror,
                on_log=self.log_line.emit,
                on_progress=self.progress.emit,
                should_cancel=self._cancel_event.is_set,
            )
            result["exit_code"] = exit_code
            result["success"] = RsyncRunner.is_success(exit_code)
        except SyncCancelled:
            result["cancelled"] = True
        except SourceNotFoundError as exc:
            result["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        finally:
            self.finished.emit(result)

    def cancel(self) -> None:
        self._cancel_event.set()
        self._runner.cancel()

    @staticmethod
    def apply_result_to_task(task: BackupTask, result: dict) -> None:
        """Cap nhat trang thai task sau khi chay xong (giong RunTaskWorker ben C#)."""
        task.last_run_utc = datetime.now(timezone.utc).isoformat()
        if result["cancelled"]:
            task.last_run_success = False
            task.last_run_summary = "Da huy"
        elif result["error"]:
            task.last_run_success = False
            task.last_run_summary = "Loi: " + result["error"]
        else:
            task.last_exit_code = result["exit_code"]
            task.last_run_success = bool(result["success"])
            task.last_run_summary = (
                "Thanh cong" if result["success"] else "Loi"
            )
