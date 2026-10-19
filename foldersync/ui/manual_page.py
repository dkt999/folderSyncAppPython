"""Trang dong bo thu cong - port tu tab 'Manual sync' cua MainForm."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SubtitleLabel,
    TextEdit,
    ToolButton,
    LineEdit,
)

from ..worker import SyncWorker


class ManualPage(QWidget):
    log_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: SyncWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("Manual sync"))

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        # --- nguon ---
        src_row = QHBoxLayout()
        src_row.addWidget(BodyLabel("Source:"))
        self.src_edit = LineEdit()
        self.src_edit.setPlaceholderText("E.g.: /mnt/shared-data  (mounted network drive)")
        self.src_edit.setClearButtonEnabled(True)
        src_row.addWidget(self.src_edit, 1)
        src_browse = ToolButton(FluentIcon.FOLDER)
        src_browse.clicked.connect(lambda: self._browse(self.src_edit))
        src_row.addWidget(src_browse)
        card_layout.addLayout(src_row)

        # --- dich ---
        dst_row = QHBoxLayout()
        dst_row.addWidget(BodyLabel("Dest:   "))
        self.dst_edit = LineEdit()
        self.dst_edit.setPlaceholderText("E.g.: /home/user/backup")
        self.dst_edit.setClearButtonEnabled(True)
        dst_row.addWidget(self.dst_edit, 1)
        dst_browse = ToolButton(FluentIcon.FOLDER)
        dst_browse.clicked.connect(lambda: self._browse(self.dst_edit))
        dst_row.addWidget(dst_browse)
        card_layout.addLayout(dst_row)

        self.mirror_check = CheckBox("Delete extra files at destination (mirror)")
        card_layout.addWidget(self.mirror_check)

        # --- nut chay/huy ---
        btn_row = QHBoxLayout()
        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "Start")
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn = PushButton(FluentIcon.CANCEL, "Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        card_layout.addLayout(btn_row)

        self.progress = ProgressBar()
        self.progress.setValue(0)
        card_layout.addWidget(self.progress)

        layout.addWidget(card)

        layout.addWidget(BodyLabel("Log:"))
        self.log_view = TextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("monospace"))
        layout.addWidget(self.log_view, 1)

    # -- ui helpers ---------------------------------------------------
    def _browse(self, target: LineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", target.text())
        if path:
            target.setText(path)

    def _append_log(self, line: str) -> None:
        self.log_view.append(line)

    def _set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.src_edit.setEnabled(not running)
        self.dst_edit.setEnabled(not running)
        self.mirror_check.setEnabled(not running)

    # -- chay dong bo -------------------------------------------------
    def _on_start(self) -> None:
        source = self.src_edit.text().strip()
        dest = self.dst_edit.text().strip()
        if not source or not dest:
            InfoBar.warning(
                "Missing information",
                "Please enter both the source and destination folders.",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        self.log_view.clear()
        self.progress.setValue(0)
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = SyncWorker(source, dest, self.mirror_check.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._append_log)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._append_log("Cancelling...")
            self._worker.cancel()

    def _on_finished(self, result: dict) -> None:
        self._thread = None
        self._worker = None
        self._set_running(False)
        self.progress.setValue(100 if not result["cancelled"] else 0)

        self._append_log("")
        if result["cancelled"]:
            self._append_log("Cancelled by user.")
        elif result["error"]:
            self._append_log("Error: " + result["error"])
        else:
            code = result["exit_code"]
            if result["success"]:
                self._append_log(f"Done. (rsync exit code: {code})")
            else:
                self._append_log(f"An error occurred! See the log above. (rsync exit code: {code})")
