"""Dialog them/sua task - port tu TaskEditForm."""
from __future__ import annotations

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout

from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    FluentIcon,
    LineEdit,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TimeEdit,
    ToolButton,
)

from ..models import BackupTask


class TaskEditDialog(QDialog):
    def __init__(self, existing: BackupTask | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add new task" if existing is None else "Edit task")
        self.setMinimumWidth(520)

        # Giong C#: tao Result moi, giu lai Id + thong tin lan chay cu khi sua.
        self.result_task = BackupTask()
        if existing is not None:
            self.result_task.id = existing.id
            self.result_task.last_run_utc = existing.last_run_utc
            self.result_task.last_run_success = existing.last_run_success
            self.result_task.last_exit_code = existing.last_exit_code
            self.result_task.last_run_summary = existing.last_run_summary

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        layout.addWidget(SubtitleLabel(self.windowTitle()))

        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("Task name")
        layout.addWidget(BodyLabel("Task name:"))
        layout.addWidget(self.name_edit)

        layout.addWidget(BodyLabel("Source:"))
        src_row = QHBoxLayout()
        self.src_edit = LineEdit()
        self.src_edit.setClearButtonEnabled(True)
        src_row.addWidget(self.src_edit, 1)
        src_browse = ToolButton(FluentIcon.FOLDER)
        src_browse.clicked.connect(lambda: self._browse(self.src_edit))
        src_row.addWidget(src_browse)
        layout.addLayout(src_row)

        layout.addWidget(BodyLabel("Destination:"))
        dst_row = QHBoxLayout()
        self.dst_edit = LineEdit()
        self.dst_edit.setClearButtonEnabled(True)
        dst_row.addWidget(self.dst_edit, 1)
        dst_browse = ToolButton(FluentIcon.FOLDER)
        dst_browse.clicked.connect(lambda: self._browse(self.dst_edit))
        dst_row.addWidget(dst_browse)
        layout.addLayout(dst_row)

        self.mirror_check = CheckBox("Delete extra files at destination (mirror)")
        layout.addWidget(self.mirror_check)

        layout.addWidget(BodyLabel("Run times (daily):"))
        time_row = QHBoxLayout()
        self.time_edit = TimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime())
        time_row.addWidget(self.time_edit)
        add_btn = PushButton(FluentIcon.ADD, "Add time")
        add_btn.clicked.connect(self._add_time)
        time_row.addWidget(add_btn)
        remove_btn = PushButton(FluentIcon.REMOVE, "Remove")
        remove_btn.clicked.connect(self._remove_time)
        time_row.addWidget(remove_btn)
        time_row.addStretch(1)
        layout.addLayout(time_row)

        self.times_list = ListWidget()
        self.times_list.setMaximumHeight(130)
        layout.addWidget(self.times_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = PushButton("Close")
        close_btn.clicked.connect(self.reject)
        save_btn = PrimaryPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(close_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        if existing is not None:
            self.name_edit.setText(existing.name)
            self.src_edit.setText(existing.source)
            self.dst_edit.setText(existing.destination)
            self.mirror_check.setChecked(existing.mirror)
            for t in sorted(existing.scheduled_times):
                self.times_list.addItem(t)

    def _browse(self, target: LineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", target.text())
        if path:
            target.setText(path)

    def _add_time(self) -> None:
        value = self.time_edit.time().toString("HH:mm")
        for i in range(self.times_list.count()):
            if self.times_list.item(i).text() == value:
                return
        self.times_list.addItem(value)
        # Sap xep tang dan cho gon.
        items = sorted(self.times_list.item(i).text() for i in range(self.times_list.count()))
        self.times_list.clear()
        self.times_list.addItems(items)

    def _remove_time(self) -> None:
        for item in self.times_list.selectedItems():
            self.times_list.takeItem(self.times_list.row(item))

    def _on_save(self) -> None:
        self.result_task.name = self.name_edit.text().strip() or "Backup task"
        self.result_task.source = self.src_edit.text().strip()
        self.result_task.destination = self.dst_edit.text().strip()
        self.result_task.mirror = self.mirror_check.isChecked()
        self.result_task.enabled = True
        self.result_task.scheduled_times = sorted(
            self.times_list.item(i).text() for i in range(self.times_list.count())
        )
        self.accept()
