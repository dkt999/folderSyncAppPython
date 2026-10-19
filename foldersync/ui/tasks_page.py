"""Trang danh sach task hen gio - port tu tab 'Schedule sync' cua MainForm."""
from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from qfluentwidgets import (
    CheckBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TableWidget,
)

from ..models import BackupTask
from .task_edit_dialog import TaskEditDialog

HEADERS = [
    "Task name", "Source", "Destination", "Run at", "Enabled",
    "Status", "Progress", "Last run", "Result",
]
COL_ENABLED = 4


class TasksPage(QWidget):
    add_requested = pyqtSignal()
    edit_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    run_now_requested = pyqtSignal(int)
    cancel_requested = pyqtSignal(int)
    enabled_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("Scheduled sync tasks"))

        self.table = TableWidget(self)
        self.table.setColumnCount(len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.add_btn = PrimaryPushButton(FluentIcon.ADD, "Add")
        self.add_btn.clicked.connect(lambda: self.add_requested.emit())
        self.edit_btn = PushButton(FluentIcon.EDIT, "Edit")
        self.edit_btn.clicked.connect(self._emit_selected(self.edit_requested))
        self.delete_btn = PushButton(FluentIcon.DELETE, "Delete")
        self.delete_btn.clicked.connect(self._emit_selected(self.delete_requested))
        self.run_btn = PushButton(FluentIcon.PLAY, "Run now")
        self.run_btn.clicked.connect(self._emit_selected(self.run_now_requested))
        self.cancel_btn = PushButton(FluentIcon.CANCEL, "Cancel task")
        self.cancel_btn.clicked.connect(self._emit_selected(self.cancel_requested))
        for b in (self.add_btn, self.edit_btn, self.delete_btn, self.run_btn, self.cancel_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _emit_selected(self, signal: pyqtSignal):
        def handler() -> None:
            index = self.selected_index()
            if index < 0:
                InfoBar.info(
                    "No task selected",
                    "Please select a task in the table first.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            signal.emit(index)

        return handler

    def selected_index(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    # -- hien thi -----------------------------------------------------
    def refresh(self, tasks: list[BackupTask]) -> None:
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self._set_row(row, task)

    def _set_row(self, row: int, task: BackupTask) -> None:
        def item(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return it

        self.table.setItem(row, 0, item(task.name))
        self.table.setItem(row, 1, item(task.source))
        self.table.setItem(row, 2, item(task.destination))
        self.table.setItem(row, 3, item(", ".join(sorted(task.scheduled_times))))

        # Tai su dung checkbox cu neu co (tranh tao moi gay lech layout).
        wrapper = self.table.cellWidget(row, COL_ENABLED)
        if wrapper is None:
            enabled_check = CheckBox()
            enabled_check.stateChanged.connect(
                lambda _state, t=task: self._on_enabled_toggled(t)
            )
            # Can giua checkbox trong cell.
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(0, 0, 0, 0)
            wrap_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrap_layout.addWidget(enabled_check)
            self.table.setCellWidget(row, COL_ENABLED, wrapper)
        else:
            enabled_check = wrapper.findChild(CheckBox)
        enabled_check.blockSignals(True)
        enabled_check.setChecked(task.enabled)
        enabled_check.blockSignals(False)

        if task.is_running:
            status = "Running..."
            progress = f"{task.progress}%" if task.progress >= 0 else "..."
        else:
            status = "Waiting"
            progress = ""
        self.table.setItem(row, 5, item(status))
        self.table.setItem(row, 6, item(progress))

        if task.last_run_utc:
            try:
                dt = datetime.fromisoformat(task.last_run_utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                last_run = dt.astimezone().strftime("%d/%m %H:%M")
            except ValueError:
                last_run = task.last_run_utc
        else:
            last_run = "Never"
        self.table.setItem(row, 7, item(last_run))

        if task.last_run_success is True:
            result = "Success"
        elif task.last_run_success is False:
            result = "Error"
        else:
            result = ""
        self.table.setItem(row, 8, item(result))

    def _on_enabled_toggled(self, task: BackupTask) -> None:
        sender = self.sender()
        task.enabled = sender.isChecked() if sender is not None else not task.enabled
        self.enabled_changed.emit(task)

    @staticmethod
    def confirm_delete(task_name: str, parent: QWidget) -> bool:
        box = MessageBox(
            "Confirm delete",
            f'Delete task "{task_name}"?',
            parent,
        )
        return box.exec()

    @staticmethod
    def open_edit_dialog(existing: BackupTask | None, parent: QWidget) -> BackupTask | None:
        dialog = TaskEditDialog(existing, parent)
        if dialog.exec():
            return dialog.result_task
        return None

    def warn_not_running(self) -> None:
        InfoBar.info(
            "Task not running",
            "This task is not currently running.",
            parent=self,
            position=InfoBarPosition.TOP,
        )
