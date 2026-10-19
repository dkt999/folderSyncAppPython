"""Trang cai dat - port tu tab 'Settings' cua MainForm (cboAutoStart)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, CardWidget, SubtitleLabel, SwitchButton

from .. import __version__
from ..autostart import is_autostart_enabled, set_autostart
from ..store import TASKS_FILE


class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("Cài đặt"))

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        self.autostart_switch = SwitchButton("Tự khởi động cùng hệ thống")
        self.autostart_switch.setChecked(is_autostart_enabled())
        self.autostart_switch.checkedChanged.connect(self._on_autostart_changed)
        card_layout.addWidget(self.autostart_switch)

        card_layout.addWidget(
            BodyLabel(
                "Khi bật, app sẽ tự chạy ẩn xuống khay hệ thống mỗi lần đăng nhập."
            )
        )
        layout.addWidget(card)

        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.addWidget(BodyLabel(f"FolderSync v{__version__} - bản port Python/Qt của FolderSyncApp (C#)"))
        info_layout.addWidget(BodyLabel(f"File task: {TASKS_FILE}"))
        info_layout.addWidget(
            BodyLabel(
                "Ổ đĩa mạng: hãy mount thư mục chia sẻ vào hệ thống trước "
                "(VD: qua Files > smb://... hoặc dòng cifs trong /etc/fstab), "
                "rồi chọn đường dẫn đã mount làm thư mục nguồn."
            )
        )
        layout.addWidget(info_card)
        layout.addStretch(1)

    def _on_autostart_changed(self, checked: bool) -> None:
        set_autostart(checked)
        # Doc lai de dam bao trang thai that.
        self.autostart_switch.setChecked(is_autostart_enabled())
