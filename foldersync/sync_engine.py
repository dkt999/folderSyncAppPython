"""Engine dong bo - port tu RobocopyRunner.cs.

Windows dung robocopy.exe; tren Linux dung rsync (tuong duong gan nhat):
  robocopy /E          -> rsync -r  (de quy, gom ca thu muc rong)
  robocopy (mac dinh copy timestamp) -> rsync -t (+ --modify-window=2 de giong
                         nguong 2 giay cua robocopy khi so sanh file)
  robocopy /Z          -> rsync --partial (cho phep tiep tuc file dang do)
  robocopy /R:3 /W:5   -> thu lai TOAN BO lan chay toi da 3 lan, cach nhau 5s
  robocopy /PURGE      -> rsync --delete (mirror: xoa file thua o dich)
  exit code 0-7 = ok   -> rsync exit code 0 = ok

Tien do: dem truoc so file "can copy" (cung tieu chi robocopy: kich thuoc
khac nhau HOAC thoi gian sua doi lech > 2 giay thi can copy), roi dem so dong
log rsync dang ">..." (file duoc gui di) de bao %.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3       # tuong duong /R:3
RETRY_WAIT_SECONDS = 5  # tuong duong /W:5
MTIME_TOLERANCE_SECONDS = 2.0  # nguong giong robocopy


class SourceNotFoundError(FileNotFoundError):
    """Thu muc nguon khong ton tai (o dia mang chua mount / rot mang)."""


class SyncCancelled(Exception):
    """Nguoi dung huy lan dong bo dang chay."""


def _needs_copy(src: Path, dst: Path) -> bool:
    """Tieu chi giong robocopy: bo qua (khong copy) neu kich thuoc bang nhau
    VA thoi gian sua doi lech nhau khong qua 2 giay."""
    try:
        if not dst.exists():
            return True
        if src.stat().st_size != dst.stat().st_size:
            return True
        if abs(src.stat().st_mtime - dst.stat().st_mtime) > MTIME_TOLERANCE_SECONDS:
            return True
        return False
    except OSError:
        # Khong doc duoc thong tin file dich (vd. loi quyen) - cu coi la can copy.
        return True


def count_files_to_copy(source: str, dest: str) -> int:
    """Dem so file can copy. Tra ve -1 neu khong doc duoc thu muc nguon."""
    try:
        src_root = Path(source)
        if not src_root.is_dir():
            return -1
        dst_root = Path(dest)
        count = 0
        for dirpath, _dirnames, filenames in os.walk(src_root):
            rel_dir = os.path.relpath(dirpath, src_root)
            for name in filenames:
                src_file = Path(dirpath) / name
                dst_file = dst_root / rel_dir / name if rel_dir != "." else dst_root / name
                if _needs_copy(src_file, dst_file):
                    count += 1
        return count
    except OSError:
        return -1


def _ensure_trailing_slash(path: str) -> str:
    """rsync 'src/' co nghia copy NOI DUNG thu muc src (giong robocopy
    'src' 'dst'), con 'src' (khong slash) la copy ca thu muc src vao dst."""
    return path if path.endswith("/") else path + "/"


def _is_file_sent_line(line: str) -> bool:
    # Dong --itemize-changes bat dau bang ">" = file/thu muc duoc gui di
    # (vd: ">f+++++++++ a.txt"). File khong doi khong in dong nao.
    return line.startswith(">")


class RsyncRunner:
    """Boc rsync de dong bo mot chieu, differential. run_with_progress() chay
    blocking - goi tu worker thread, KHONG goi tu UI thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    @staticmethod
    def is_success(exit_code: int) -> bool:
        return exit_code == 0

    def _build_cmd(self, source: str, dest: str, mirror: bool) -> list[str]:
        cmd = [
            "rsync",
            "-rt",                    # de quy + giu timestamp (tuong duong /E + copy time)
            "--modify-window=2",      # nguong 2 giay giong robocopy
            "--partial",              # tuong duong /Z (restartable)
            "--itemize-changes",      # in dong ">..." cho tung file duoc copy (de dem %)
            "--human-readable",
        ]
        if mirror:
            cmd.append("--delete")    # tuong duong /PURGE
        cmd.append(_ensure_trailing_slash(source))
        cmd.append(dest)
        return cmd

    def run_with_progress(
        self,
        source: str,
        dest: str,
        mirror: bool,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> int:
        src = Path(source)
        if not src.is_dir():
            raise SourceNotFoundError(
                f'Thu muc nguon khong ton tai: "{source}". '
                "Kiem tra o dia mang da duoc mount chua."
            )

        total_files = count_files_to_copy(source, dest)
        if on_progress:
            on_progress(0)

        # Khong dem duoc so file (vd. -1) hoac khong co gi can copy:
        # chay thang 1 lan roi bao 100%, giong nhanh cu ben C#.
        if total_files <= 0:
            exit_code = self._run_attempts(
                source, dest, mirror, on_log, None, total_files, should_cancel
            )
            if on_progress:
                on_progress(100)
            return exit_code

        done = 0
        last_reported = -1

        def handle_line(line: str) -> None:
            nonlocal done, last_reported
            if on_log:
                on_log(line)
            if _is_file_sent_line(line):
                done += 1
                percent = min(99, done * 100 // total_files)
                if percent != last_reported:
                    last_reported = percent
                    if on_progress:
                        on_progress(percent)

        exit_code = self._run_attempts(
            source, dest, mirror, handle_line, on_log, total_files, should_cancel
        )
        if on_progress:
            on_progress(100)
        return exit_code

    def _run_attempts(
        self,
        source: str,
        dest: str,
        mirror: bool,
        handle_line: Callable[[str], None] | None,
        on_log: Callable[[str], None] | None,
        total_files: int,
        should_cancel: Callable[[], bool] | None,
    ) -> int:
        cmd = self._build_cmd(source, dest, mirror)
        log.info("Chay: %s", " ".join(cmd))

        last_exit = 1
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if should_cancel and should_cancel():
                raise SyncCancelled()
            if attempt > 1:
                msg = f"Thu lai lan {attempt}/{MAX_ATTEMPTS} sau {RETRY_WAIT_SECONDS}s..."
                log.info(msg)
                if on_log:
                    on_log(msg)
                # Cho nhung van kiem tra huy giua chung.
                for _ in range(RETRY_WAIT_SECONDS * 10):
                    if should_cancel and should_cancel():
                        raise SyncCancelled()
                    time.sleep(0.1)
            last_exit = self._run_once(cmd, handle_line or on_log, should_cancel)
            if last_exit == 0:
                break
            if should_cancel and should_cancel():
                raise SyncCancelled()
        return last_exit

    def _run_once(
        self,
        cmd: list[str],
        handle_line: Callable[[str], None] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> int:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with self._lock:
            self._proc = proc
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                if should_cancel and should_cancel():
                    raise SyncCancelled()
                line = raw_line.rstrip("\n")
                if handle_line:
                    handle_line(line)
            proc.wait()
            return proc.returncode
        finally:
            with self._lock:
                self._proc = None

    def cancel(self) -> None:
        """Goi tu thread khac (vd. UI thread khi bam Huy) de dung rsync dang chay."""
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                # Tien trinh co the da tu ket thuc truoc do.
                pass
