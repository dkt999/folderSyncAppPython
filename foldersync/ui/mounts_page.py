"""Trang quan ly o dia mang SMB/CIFS - mount an toan voi fstab.

Quy trinh: nhap thong tin -> [1. Mount thu] (khong dung den fstab)
-> ok moi duoc [2. Luu vao fstab & mount] (backup + validate cu phap).
Moi entry deu co `nofail` nen o mang loi may van boot binh thuong.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TableWidget,
    TextEdit,
)

from ..mounts import (
    build_fstab_line,
    build_options,
    credentials_path_for,
    current_uid_gid,
    find_entry,
    has_nofail,
    is_mounted,
    normalize_source,
    normalize_target,
    parse_fstab,
    resolve_server,
    server_of,
    validate_source,
    validate_target,
)
from ..privileged import run_privileged


class PrivWorker(QObject):
    finished = pyqtSignal(dict)
    log_line = pyqtSignal(str)

    def __init__(self, fn, parent: QObject | None = None) -> None:
        # fn: (log: Callable[[str], None]) -> dict — log goi tu thread nen
        # van an toan nho queued signal.
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self._fn(self.log_line.emit))
        except Exception as exc:  # noqa: BLE001
            self.finished.emit({"ok": False, "message": "Loi khong mong doi.", "detail": str(exc)})


class MountsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._tested_key: tuple | None = None  # (source, target, username, domain, guest)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("Ổ đĩa mạng (SMB/CIFS)"))
        layout.addWidget(
            BodyLabel(
                "Mount share mạng vào máy rồi dùng làm thư mục nguồn cho task đồng bộ. "
                "Mọi entry fstab đều có 'nofail' nên nếu ổ mạng lỗi, máy vẫn khởi động bình thường."
            )
        )

        # -- bang cac mount da cau hinh --
        list_card = CardWidget(self)
        list_layout = QVBoxLayout(list_card)
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Share", "Điểm mount", "Trạng thái", "fstab"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        list_layout.addWidget(self.table)
        refresh_row = QHBoxLayout()
        refresh_btn = PushButton(FluentIcon.SYNC, "Làm mới")
        refresh_btn.clicked.connect(self.refresh_table)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addStretch(1)
        list_layout.addLayout(refresh_row)
        layout.addWidget(list_card)

        # -- form them moi --
        form_card = CardWidget(self)
        form = QVBoxLayout(form_card)
        form.setSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("Share:"))
        self.source_edit = LineEdit()
        self.source_edit.setPlaceholderText("//192.168.1.10/du-lieu  (dán smb://... từ Files cũng được)")
        self.source_edit.setClearButtonEnabled(True)
        row1.addWidget(self.source_edit, 1)
        row1.addWidget(BodyLabel("Điểm mount:"))
        row1.addWidget(BodyLabel("/mnt/"))  # prefix co dinh, khong can go
        self.target_edit = LineEdit()
        self.target_edit.setPlaceholderText("VD: COM0068Share")
        self.target_edit.setClearButtonEnabled(True)
        row1.addWidget(self.target_edit, 1)
        form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("User:"))
        self.user_edit = LineEdit()
        self.user_edit.setPlaceholderText("tên đăng nhập share")
        row2.addWidget(self.user_edit, 1)
        row2.addWidget(BodyLabel("Pass:"))
        self.pass_edit = PasswordLineEdit()
        self.pass_edit.setPlaceholderText("mật khẩu")
        row2.addWidget(self.pass_edit, 1)
        row2.addWidget(BodyLabel("Domain:"))
        self.domain_edit = LineEdit()
        self.domain_edit.setPlaceholderText("(không bắt buộc)")
        row2.addWidget(self.domain_edit, 1)
        self.guest_check = CheckBox("Khách (guest)")
        self.guest_check.stateChanged.connect(self._on_guest_changed)
        row2.addWidget(self.guest_check)
        form.addLayout(row2)

        btn_row = QHBoxLayout()
        self.test_btn = PrimaryPushButton(FluentIcon.PLAY, "1. Mount thử")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = PushButton(FluentIcon.SAVE, "2. Lưu vào fstab && mount")
        self.save_btn.clicked.connect(self._on_save)
        self.verify_btn = PushButton(FluentIcon.CHECKBOX, "Kiểm tra fstab")
        self.verify_btn.clicked.connect(self._on_verify)
        self.umount_btn = PushButton("Gỡ mount")
        self.umount_btn.clicked.connect(self._on_umount)
        self.remove_btn = PushButton(FluentIcon.DELETE, "Xóa khỏi fstab")
        self.remove_btn.clicked.connect(self._on_remove)
        for b in (self.test_btn, self.save_btn, self.verify_btn, self.umount_btn, self.remove_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        form.addLayout(btn_row)
        layout.addWidget(form_card)

        layout.addWidget(BodyLabel("Nhật ký:"))
        self.log_view = TextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("monospace"))
        self.log_view.setMaximumHeight(180)
        layout.addWidget(self.log_view)

        self.refresh_table()

    # -- helpers ------------------------------------------------------
    def _on_guest_changed(self) -> None:
        guest = self.guest_check.isChecked()
        self.user_edit.setEnabled(not guest)
        self.pass_edit.setEnabled(not guest)

    def _log(self, line: str) -> None:
        self.log_view.append(line)

    def _set_busy(self, busy: bool) -> None:
        for b in (self.test_btn, self.save_btn, self.verify_btn, self.umount_btn, self.remove_btn):
            b.setEnabled(not busy)

    def _run_priv(self, job_fn, on_done) -> None:
        """Chay ham privileged tren thread nen.
        job_fn: (log) -> dict ; on_done: (result) -> None (chay o GUI thread)."""
        self._set_busy(True)
        self._thread = QThread(self)
        worker = PrivWorker(job_fn)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.log_line.connect(self._log)
        worker.finished.connect(on_done)
        worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        worker.finished.connect(worker.deleteLater)
        self._thread.start()

    def _on_priv_done(self, result: dict, done_msg: str = "") -> None:
        self._thread = None
        self._set_busy(False)
        # Chay o GUI thread nen an toan khi cham vao widget.
        if result.get("ok"):
            self._log("OK: " + (result.get("message") or done_msg))
        else:
            self._log("LỖI: " + result.get("message", ""))
            if result.get("detail"):
                self._log("  Chi tiết: " + result["detail"])
        self.refresh_table()

    def _form_values(self) -> tuple[str, str, str, str, str, bool]:
        return (
            normalize_source(self.source_edit.text()),
            normalize_target(self.target_edit.text()),
            self.user_edit.text().strip(),
            self.pass_edit.text(),
            self.domain_edit.text().strip(),
            self.guest_check.isChecked(),
        )

    def _validate_form(self) -> tuple | None:
        source, target, username, _pw, _domain, guest = self._form_values()
        err = validate_source(source) or validate_target(target)
        if err:
            InfoBar.warning("Thông tin chưa đúng", err, parent=self, position=InfoBarPosition.TOP)
            return None
        if not guest and not username:
            InfoBar.warning(
                "Thiếu user", "Nhập username của share (hoặc tick Khách).",
                parent=self, position=InfoBarPosition.TOP,
            )
            return None
        return (source, target, username, guest)

    def _current_key(self) -> tuple:
        source, target, username, _pw, domain, guest = self._form_values()
        return (source, target, username, domain, guest)

    def _build_options_and_line(self) -> tuple[str, str]:
        source, target, username, _pw, _domain, guest = self._form_values()
        uid, gid = current_uid_gid()
        cred_path = None if guest else credentials_path_for(target)
        options = build_options(uid, gid, cred_path, guest)
        return options, build_fstab_line(source, target, options)

    # -- bang ---------------------------------------------------------
    def refresh_table(self) -> None:
        entries = [e for e in parse_fstab() if e.fstype == "cifs"]
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(e.device))
            self.table.setItem(row, 1, QTableWidgetItem(e.mountpoint))
            status = "Đã mount" if is_mounted(e.mountpoint) else "Chưa mount"
            self.table.setItem(row, 2, QTableWidgetItem(status))
            safe = "An toàn (nofail)" if has_nofail(e.options) else "THIẾU nofail!"
            self.table.setItem(row, 3, QTableWidgetItem(safe))

    def _selected_target(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            InfoBar.info("Chưa chọn", "Hãy chọn một dòng trong bảng.", parent=self,
                         position=InfoBarPosition.TOP)
            return None
        item = self.table.item(rows[0].row(), 1)
        return item.text() if item else None

    # -- nut bam ------------------------------------------------------
    def _on_test(self) -> None:
        vals = self._validate_form()
        if vals is None:
            return
        source, target, username, guest = vals
        _s, _t, _u, password, domain, _g = self._form_values()
        options, _line = self._build_options_and_line()
        self._log(f"Mount thử {source} ...")

        def job(log) -> dict:
            # 0. Kiem tra ten may phan giai duoc khong — neu khong thi mount.cifs
            #    se treo rat lau. Dung bao loi som thay vi treo den.
            server = server_of(source)
            log(f"→ Đang phân giải tên máy '{server}' ...")
            ip = resolve_server(server)
            if ip is None:
                return {
                    "ok": False,
                    "message": f"Không phân giải được tên máy '{server}'.",
                    "detail": (
                        "Files (Nautilus) tự dò máy trong mạng nên vẫn mở được smb://..., "
                        "nhưng mount qua hệ thống cần tên phân giải được qua DNS. "
                        "Hãy dùng địa chỉ IP thay cho tên máy, VD: //192.168.1.10/02. share"
                    ),
                }
            log(f"→ {server} phân giải thành {ip}")
            if not guest:
                log("→ Đang xin quyền root để lưu credentials (có thể hiện hộp thoại mật khẩu)...")
                r = run_privileged(
                    ["write-credentials", "--path", str(credentials_path_for(target)),
                     "--username", username, "--domain", domain],
                    stdin_text=password + "\n",
                )
                if not r.get("ok"):
                    return r
                log("→ Đã lưu credentials.")
            log("→ Đang mount thử (chờ tối đa 60 giây)...")
            return run_privileged(["test-mount", "--source", source, "--options", options])

        def done(result: dict) -> None:
            self._on_priv_done(result)
            if result.get("ok"):
                self._tested_key = self._current_key()
                self._log("→ Mount thử OK. Giờ có thể bấm [2. Lưu vào fstab & mount].")

        self._run_priv(job, done)

    def _on_save(self) -> None:
        vals = self._validate_form()
        if vals is None:
            return
        source, target, username, guest = vals
        if self._tested_key != self._current_key():
            InfoBar.warning(
                "Chưa mount thử",
                "Hãy bấm [1. Mount thử] thành công trước khi lưu vào fstab.",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        _s, _t, _u, password, domain, _g = self._form_values()
        options, line = self._build_options_and_line()
        self._log(f"Dòng fstab sẽ thêm:\n  {line}")
        self._log("Đang lưu (có backup + kiểm tra cú pháp)...")

        def job(log) -> dict:
            def step(cmd: list[str], stdin_text: str | None = None) -> dict | None:
                r = run_privileged(cmd, stdin_text=stdin_text)
                log(("✓ " if r.get("ok") else "✗ ") + r.get("message", ""))
                if r.get("detail"):
                    log("  Chi tiết: " + r["detail"])
                return None if r.get("ok") else r

            if not guest:
                log("→ Đang xin quyền root để lưu credentials...")
                failed = step(
                    ["write-credentials", "--path", str(credentials_path_for(target)),
                     "--username", username, "--domain", domain],
                    stdin_text=password + "\n",
                )
                if failed:
                    return failed
            log("→ Đang tạo điểm mount...")
            failed = step(["ensure-mountpoint", "--target", target])
            if failed:
                return failed
            log("→ Đang ghi fstab (có backup)...")
            failed = step(["fstab-add", "--line", line])
            if failed:
                return failed
            log("→ Đang mount...")
            return run_privileged(["mount-target", "--target", target])

        self._run_priv(job, lambda r: self._on_priv_done(r, "Hoàn tất: đã lưu fstab và mount."))

    def _on_verify(self) -> None:
        self._log("Kiểm tra cú pháp /etc/fstab ...")
        self._run_priv(
            lambda log: run_privileged(["fstab-verify"]),
            lambda r: self._on_priv_done(r),
        )

    def _on_umount(self) -> None:
        target = self._selected_target()
        if target is None:
            return
        self._log(f"Gỡ mount {target} ...")
        self._run_priv(
            lambda log: run_privileged(["umount-target", "--target", target]),
            lambda r: self._on_priv_done(r),
        )

    def _on_remove(self) -> None:
        target = self._selected_target()
        if target is None:
            return
        entries = parse_fstab()
        if find_entry(entries, target=target) is None:
            InfoBar.info("Không có", "Dòng này không còn trong fstab.", parent=self,
                         position=InfoBarPosition.TOP)
            return
        self._log(f"Xóa {target} khỏi fstab (có backup)...")
        self._run_priv(
            lambda log: run_privileged(["fstab-remove", "--target", target]),
            lambda r: self._on_priv_done(r),
        )
