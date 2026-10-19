"""Test sync_engine (rsync thay robocopy). Chay: python3 -m pytest tests/ -x -q"""
import os
import threading
import time
from pathlib import Path

import pytest

from foldersync.sync_engine import (
    RsyncRunner,
    SourceNotFoundError,
    SyncCancelled,
    count_files_to_copy,
)


@pytest.fixture()
def src_dst(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "a.txt").write_text("hello")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("world")
    return src, dst


def test_count_files_to_copy(src_dst):
    src, dst = src_dst
    assert count_files_to_copy(str(src), str(dst)) == 2
    # Dong bo xong -> khong con file can copy.
    r = RsyncRunner()
    assert r.run_with_progress(str(src), str(dst), False) == 0
    assert count_files_to_copy(str(src), str(dst)) == 0


def test_count_mtime_tolerance(src_dst):
    """Doi mtime trong 2s, cung size -> coi nhu khong doi (giong robocopy)."""
    src, dst = src_dst
    r = RsyncRunner()
    assert r.run_with_progress(str(src), str(dst), False) == 0
    assert count_files_to_copy(str(src), str(dst)) == 0
    # Sua noi dung (doi size) -> can copy.
    (src / "a.txt").write_text("hello!")
    assert count_files_to_copy(str(src), str(dst)) == 1
    assert r.run_with_progress(str(src), str(dst), False) == 0
    # Giu nguyen size, doi mtime +10s -> can copy.
    st = (src / "a.txt").stat()
    os.utime(src / "a.txt", (st.st_atime, st.st_mtime + 10))
    assert count_files_to_copy(str(src), str(dst)) == 1
    # Doi mtime trong 1s -> khong can copy.
    os.utime(src / "a.txt", (st.st_atime, st.st_mtime + 1))
    assert count_files_to_copy(str(src), str(dst)) == 0


def test_count_source_missing(tmp_path):
    assert count_files_to_copy(str(tmp_path / "khong-co"), str(tmp_path)) == -1


def test_run_copies_files_and_reports_progress(src_dst):
    src, dst = src_dst
    progresses = []
    logs = []
    r = RsyncRunner()
    code = r.run_with_progress(
        str(src),
        str(dst),
        False,
        on_log=logs.append,
        on_progress=progresses.append,
    )
    assert code == 0
    assert RsyncRunner.is_success(code)
    assert (dst / "a.txt").read_text() == "hello"
    assert (dst / "sub" / "b.txt").read_text() == "world"
    assert progresses[0] == 0
    assert progresses[-1] == 100
    assert any("a.txt" in line for line in logs)


def test_mirror_deletes_extra_files(src_dst):
    src, dst = src_dst
    (dst).mkdir(exist_ok=True)
    (dst / "thua.txt").write_text("x")
    r = RsyncRunner()
    assert r.run_with_progress(str(src), str(dst), False) == 0
    assert (dst / "thua.txt").exists()  # khong mirror -> giu lai
    assert r.run_with_progress(str(src), str(dst), True) == 0
    assert not (dst / "thua.txt").exists()  # mirror -> xoa


def test_source_not_found(tmp_path):
    r = RsyncRunner()
    with pytest.raises(SourceNotFoundError):
        r.run_with_progress(str(tmp_path / "khong-co"), str(tmp_path / "dst"), False)


def test_cancel_before_start(src_dst):
    src, dst = src_dst
    r = RsyncRunner()
    with pytest.raises(SyncCancelled):
        r.run_with_progress(
            str(src), str(dst), False, should_cancel=lambda: True
        )


def test_cancel_during_run(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    # Nhieu file nho de rsync chay du lau de kip huy.
    for i in range(3000):
        (src / f"f{i:05d}.txt").write_text("x" * 100)

    r = RsyncRunner()
    cancel_flag = threading.Event()
    seen = []

    def on_log(line):
        seen.append(line)
        if len(seen) >= 5:
            cancel_flag.set()

    error = []

    def target():
        try:
            r.run_with_progress(
                str(src),
                str(dst),
                False,
                on_log=on_log,
                should_cancel=cancel_flag.is_set,
            )
        except SyncCancelled:
            error.append("cancelled")

    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=60)
    assert not t.is_alive(), "thread bi treo"
    assert error == ["cancelled"]


def test_is_success_mapping():
    assert RsyncRunner.is_success(0) is True
    assert RsyncRunner.is_success(1) is False
    assert RsyncRunner.is_success(23) is False
