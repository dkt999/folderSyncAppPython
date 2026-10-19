"""Test logic mount SMB/CIFS (khong can root, khong can server that)."""
import json
import stat
import subprocess
import sys
from pathlib import Path

from foldersync import privileged
from foldersync.mounts import (
    build_fstab_line,
    build_options,
    credentials_path_for,
    escape_fstab,
    find_entry,
    has_nofail,
    is_mounted,
    list_cifs_mounts,
    normalize_source,
    parse_fstab,
    unescape_fstab,
    validate_source,
    validate_target,
)


def test_validate_source():
    assert validate_source("//192.168.1.10/du-lieu") is None
    assert validate_source("//server/share") is None
    assert validate_source("//server/share/") is None  # rstrip "/"
    assert validate_source("/mnt/x") is not None
    assert validate_source("//server") is not None
    assert validate_source("//server/a/b") is not None
    assert validate_source("server/share") is not None


def test_validate_target():
    assert validate_target("/mnt/du-lieu") is None
    assert validate_target("mnt/du-lieu") is not None
    assert validate_target("/") is not None
    assert validate_target("/etc") is not None
    # Dau cach o diem mount gio duoc chap nhan (se escape \040 khi ghi fstab).
    assert validate_target("/mnt/co dau cach") is None


def test_normalize_source():
    # Paste nguyen tu Files (smb://...) cung duoc.
    assert normalize_source("smb://com0068/02. share/") == "//com0068/02. share"
    assert normalize_source("SMB://srv/share") == "//srv/share"
    assert normalize_source("//srv/share/") == "//srv/share"
    assert normalize_source("smb://srv/my%20docs/") == "//srv/my docs"
    assert validate_source("smb://com0068/02. share/") is None


def test_escape_unescape_roundtrip():
    raw = "//com0068/02. share"
    escaped = escape_fstab(raw)
    assert escaped == "//com0068/02.\\040share"
    assert " " not in escaped
    assert unescape_fstab(escaped) == raw


def test_fstab_line_with_space_stays_6_fields():
    line = build_fstab_line("//com0068/02. share", "/mnt/du-lieu",
                            build_options(1000, 1000, None, guest=True))
    assert len(line.split()) == 6, line  # dau cach tho se lam vo thanh 7+ field
    assert "\\040" in line
    # Doc lai phai ra dung ten goc.
    assert privileged._strict_check_line(line) is None


def test_parse_unescapes_device(tmp_path):
    fstab = tmp_path / "fstab"
    fstab.write_text("//com0068/02.\\040share  /mnt/dl  cifs  guest,nofail  0  0\n")
    entries = parse_fstab(fstab)
    assert len(entries) == 1
    assert entries[0].device == "//com0068/02. share"
    assert find_entry(entries, source="smb://com0068/02. share/") is not None


def test_is_mounted_escaped_target(tmp_path):
    proc = tmp_path / "mounts"
    proc.write_text("//com0068/02.\\040share /mnt/du\\040lieu cifs rw 0 0\n")
    assert is_mounted("/mnt/du lieu", proc)


def test_build_options_has_nofail_and_netdev():
    opts = build_options(1000, 1000, Path("/etc/samba/credentials/x.cred"))
    assert "nofail" in opts.split(",")
    assert "_netdev" in opts.split(",")
    assert "credentials=/etc/samba/credentials/x.cred" in opts
    assert "uid=1000" in opts and "gid=1000" in opts
    assert "iocharset=utf8" in opts


def test_build_options_guest():
    opts = build_options(1000, 1000, None, guest=True)
    assert "guest" in opts.split(",")
    assert "nofail" in opts.split(",")


def test_build_fstab_line():
    line = build_fstab_line("//s/share", "/mnt/x", "guest,nofail")
    parts = line.split()
    assert parts[0] == "//s/share" and parts[1] == "/mnt/x" and parts[2] == "cifs"


def test_parse_and_find(tmp_path):
    fstab = tmp_path / "fstab"
    fstab.write_text(
        "# comment\n"
        "UUID=abc / ext4 defaults 0 1\n"
        "//192.168.1.10/dl  /mnt/dl  cifs  credentials=/root/x,uid=1000,nofail  0  0\n"
        "dong loi\n"
    )
    entries = parse_fstab(fstab)
    assert len(entries) == 2
    e = find_entry(entries, target="/mnt/dl")
    assert e is not None and e.fstype == "cifs" and has_nofail(e.options)
    assert find_entry(entries, target="/mnt/khong-co") is None
    assert find_entry(entries, source="//192.168.1.10/dl") is not None


def test_is_mounted_fake_proc(tmp_path):
    proc = tmp_path / "mounts"
    proc.write_text("//srv/share /mnt/dl cifs rw 0 0\n/dev/sda1 / ext4 rw 0 0\n")
    assert is_mounted("/mnt/dl", proc)
    assert not is_mounted("/mnt/khac", proc)
    assert list_cifs_mounts(proc) == [("//srv/share", "/mnt/dl")]


def test_credentials_path():
    p = credentials_path_for("/mnt/du-lieu")
    assert p.name == "foldersync-du-lieu.cred"


# ---------------------------------------------------------------- privileged
def _make_fstab(tmp_path: Path) -> Path:
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=abc / ext4 defaults 0 1\n")
    return fstab


def test_fstab_add_verify_and_remove(tmp_path):
    fstab = _make_fstab(tmp_path)
    line = build_fstab_line("//s/share", "/mnt/x", build_options(1000, 1000, None, guest=True))

    r = privileged.fstab_add(line, fstab)
    assert r["ok"], r
    # Phai co file backup.
    assert list(tmp_path.glob("fstab.bak.*")), "khong thay file backup fstab"
    entries = parse_fstab(fstab)
    assert find_entry(entries, target="/mnt/x") is not None

    # Them trung -> tu choi.
    r2 = privileged.fstab_add(line, fstab)
    assert not r2["ok"]

    # Verify doc lap.
    assert privileged.fstab_verify(fstab)["ok"]

    # Xoa.
    r3 = privileged.fstab_remove("/mnt/x", fstab)
    assert r3["ok"], r3
    assert find_entry(parse_fstab(fstab), target="/mnt/x") is None

    # Xoa cai khong co -> bao loi nhe.
    assert not privileged.fstab_remove("/mnt/khong-co", fstab)["ok"]


def test_fstab_add_rolls_back_on_bad_line(tmp_path):
    fstab = _make_fstab(tmp_path)
    before = fstab.read_text()
    # Dong thieu truong -> bi tu choi truoc khi ghi.
    r = privileged.fstab_add("//s/share", fstab)
    assert not r["ok"]
    assert fstab.read_text() == before


def test_write_credentials_permissions(tmp_path):
    cred = tmp_path / "test.cred"
    r = privileged.write_credentials(str(cred), "user1", "mat-khau", "DOMAIN")
    assert r["ok"], r
    assert stat.S_IMODE(cred.stat().st_mode) == 0o600
    text = cred.read_text()
    assert "username=user1" in text and "password=mat-khau" in text and "domain=DOMAIN" in text


def test_test_mount_fails_gracefully():
    # Khong co server that -> phai tra ve dict loi, khong raise.
    r = privileged.test_mount("//127.0.0.1/khong-co", "guest")
    assert not r["ok"]
    assert r["message"]


def test_cli_json_output(tmp_path):
    fstab = _make_fstab(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "foldersync.privileged", "fstab-verify", "--fstab", str(fstab)],
        capture_output=True, text=True, cwd=Path("foldersync").resolve().parent,
    )
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["ok"] is True
    assert proc.returncode == 0


def test_run_privileged_direct_as_root(tmp_path):
    # Tren VM nay dang la root -> chay truc tiep, khong can pkexec.
    import os

    if os.geteuid() != 0:
        return
    fstab = _make_fstab(tmp_path)
    r = privileged.run_privileged(["fstab-verify", "--fstab", str(fstab)])
    assert r["ok"] is True, r
