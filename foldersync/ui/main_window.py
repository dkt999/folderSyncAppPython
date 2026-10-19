"""Cua so chinh - port tu MainForm (tab control + tray icon)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from qfluentwidgets import FluentIcon, FluentWindow, InfoBar, InfoBarPosition

from ..models import BackupTask
from ..scheduler import QtScheduler
from ..store import load_tasks, save_tasks
from .manual_page import ManualPage
from .mounts_page import MountsPage
from .settings_page import SettingsPage
from .tasks_page import TasksPage


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Folder Sync")
        self.resize(980, 640)

        self._tasks: list[BackupTask] = load_tasks()
        self._quitting = False

        self.manual_page = ManualPage(self)
        self.manual_page.setObjectName("manualPage")
        self.tasks_page = TasksPage(self)
        self.tasks_page.setObjectName("tasksPage")
        self.settings_page = SettingsPage(self)
        self.settings_page.setObjectName("settingsPage")
        self.mounts_page = MountsPage(self)
        self.mounts_page.setObjectName("mountsPage")

        self.addSubInterface(self.manual_page, FluentIcon.SYNC, "Đồng bộ thủ công")
        self.addSubInterface(self.tasks_page, FluentIcon.CALENDAR, "Task hẹn giờ")
        self.addSubInterface(self.mounts_page, FluentIcon.SHARE, "Ổ đĩa mạng")
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "Cài đặt")

        # -- noi cac su kien cua trang task --
        self.tasks_page.add_requested.connect(self._on_add_task)
        self.tasks_page.edit_requested.connect(self._on_edit_task)
        self.tasks_page.delete_requested.connect(self._on_delete_task)
        self.tasks_page.run_now_requested.connect(self._on_run_now)
        self.tasks_page.cancel_requested.connect(self._on_cancel_task)
        self.tasks_page.enabled_changed.connect(self._on_task_enabled_changed)

        # -- scheduler --
        self._scheduler = QtScheduler(self._tasks, self)
        self._scheduler.task_changed.connect(self._on_task_changed)
        self._scheduler.start()

        self.tasks_page.refresh(self._tasks)

        # -- tray icon (port tu notifyIcon1) --
        self._tray: QSystemTrayIcon | None = None
        self._setup_tray()

    # -- task CRUD ----------------------------------------------------
    def _on_add_task(self) -> None:
        new_task = TasksPage.open_edit_dialog(None, self)
        if new_task is None:
            return
        if not new_task.source or not new_task.destination:
            InfoBar.warning(
                "Thiếu thông tin",
                "Vui lòng nhập cả thư mục nguồn và thư mục đích.",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        self._tasks.append(new_task)
        save_tasks(self._tasks)
        self.tasks_page.refresh(self._tasks)

    def _on_edit_task(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        updated = TasksPage.open_edit_dialog(self._tasks[index], self)
        if updated is None:
            return
        self._tasks[index] = updated
        save_tasks(self._tasks)
        self.tasks_page.refresh(self._tasks)

    def _on_delete_task(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        task = self._tasks[index]
        if not TasksPage.confirm_delete(task.name, self):
            return
        del self._tasks[index]
        save_tasks(self._tasks)
        self.tasks_page.refresh(self._tasks)

    def _on_run_now(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        self._scheduler.run_task_in_background(self._tasks[index])

    def _on_cancel_task(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        task = self._tasks[index]
        if not task.is_running:
            self.tasks_page.warn_not_running()
            return
        self._scheduler.cancel_task(task)

    def _on_task_enabled_changed(self, _task: BackupTask) -> None:
        save_tasks(self._tasks)

    def _on_task_changed(self, _task: BackupTask) -> None:
        # Giong C#: moi khi scheduler bao doi trang thai thi ve lai bang.
        self.tasks_page.refresh(self._tasks)

    # -- tray ---------------------------------------------------------
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(FluentIcon.SYNC.icon())
        self._tray.setToolTip("Folder Sync")

        menu = QMenu()
        show_action = QAction("Hiện", self)
        show_action.triggered.connect(self._show_window)
        exit_action = QAction("Thoát", self)
        exit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(exit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _show_window(self) -> None:
        self.show()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self.activateWindow()
        self.raise_()

    # -- dong / thoat --------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        # Giong C#: bam X thi an xuong tray, chi thoat han khi chon Thoát.
        if not self._quitting:
            event.ignore()
            self.hide()
            if self._tray is not None:
                self._tray.showMessage(
                    "Folder Sync",
                    "Ứng dụng vẫn đang chạy nền.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
        else:
            event.accept()

    def _quit(self) -> None:
        self._quitting = True
        self._scheduler.stop()
        self._scheduler.shutdown()
        save_tasks(self._tasks)
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()
