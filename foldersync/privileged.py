"""Cac thao tac can quyen root: mount, ghi /etc/fstab, ghi file credentials.

- Khi chay voi euid==0: goi truc tiep cac ham ben duoi.
- Khi chay user thuong: GUI goi `run_privileged([...])`, ham nay tu them
  `pkexec` phia truoc de hien hop thoai nhap mat khau cua he thong.
- Moi lenh in 1 dong JSON ra stdout: {"ok": bool, "message": str, "detail": str}
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .mounts import FSTAB_PATH, parse_fstab

MOUNT_TIMEOUT = 60


def _result(ok: bool, message: str = "", detail: str = "") -> dict:
    return {"ok": ok, "message": message, "detail": detail}


def _run(cmd: list[str], timeout: int = MOUNT_TIMEOUT) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Het thoi gian cho ({timeout}s) - server khong phan hoi"


# ---------------------------------------------------------------- test mount
def test_mount(source: str, options: str) -> dict:
    """Mount THU vao thu muc tam, khong dung den fstab.
    Thanh cong -> chung to thong so (server/share/user/pass) dung."""
    tmpdir = tempfile.mkdtemp(prefix="foldersync-mount-test-")
    try:
        code, _out, err = _run(["mount", "-t", "cifs", source, tmpdir, "-o", options])
        if code != 0:
            return _result(False, "Mount thu that bai.", _friendly_mount_error(err))
        try:
            if not os.path.ismount(tmpdir):
                return _result(False, "Mount thu that bai (khong thay diem mount).", err)
            os.listdir(tmpdir)  # doc thu de chac chan share truy cap duoc
        except OSError as exc:
            return _result(False, "Mount duoc nhung khong doc duoc share.", str(exc))
        return _result(True, "Mount thu thanh cong, doc duoc share.")
    finally:
        subprocess.run(["umount", tmpdir], capture_output=True, timeout=30)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def _friendly_mount_error(stderr: str) -> str:
    s = stderr.lower()
    if "permission denied" in s or "13" in s.split():
        return "Sai username/password hoac khong co quyen truy cap share."
    if "no such device" in s:
        return "Thieu goi cifs-utils (can cai: sudo apt install cifs-utils)."
    if "host is down" in s or "no route to host" in s or "connection refused" in s:
        return "Khong ket noi duoc toi server (sai dia chi hoac server tat/firewall)."
    if "no such file or directory" in s:
        return "Ten share khong ton tai tren server."
    return stderr or "Khong ro nguyen nhan."


# ---------------------------------------------------------------- fstab
def _backup_fstab(fstab: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = fstab.with_name(f"fstab.bak.{stamp}")
    shutil.copy2(fstab, backup)
    return backup


def _strict_check_line(line: str) -> str | None:
    """Kiem tra chat che dong fstab do chinh app sinh ra. None = hop le."""
    parts = line.split()
    if len(parts) != 6:
        return f"Dong fstab phai co dung 6 truong, dang co {len(parts)}."
    device, target, fstype, _opts, dump, fsck = parts
    if not device.startswith("//"):
        return "Device phai dang //server/share."
    if not target.startswith("/"):
        return "Diem mount phai la duong dan tuyet doi."
    if fstype != "cifs":
        return "Fstype phai la cifs."
    if dump not in ("0", "1") or fsck not in ("0", "1", "2"):
        return "Truong dump/fsck khong hop le."
    return None


def _findmnt_info(fstab: Path) -> str:
    """Chay findmnt --verify lay thong tin (khong dung de ket luan loi
    vi no bao ca van de ngu nghia nhu share offline - dieu nay la binh thuong
    voi o mang co nofail)."""
    if not shutil.which("findmnt"):
        return ""
    _code, out, err = _run(["findmnt", "--verify", "--tab-file", str(fstab)], timeout=30)
    return (out + "\n" + err).strip()


def fstab_add(line: str, fstab: Path = FSTAB_PATH) -> dict:
    # 1. Kiem tra chat che dong do chinh app sinh ra, TRUOC khi dung den fstab.
    err = _strict_check_line(line)
    if err:
        return _result(False, "Dong fstab khong hop le: " + err)
    target = line.split()[1]

    entries_before = parse_fstab(fstab)
    if any(e.mountpoint == target for e in entries_before):
        return _result(False, f'Da co dong fstab cho diem mount "{target}". Hay xoa truoc.')

    try:
        backup = _backup_fstab(fstab)
    except OSError as exc:
        return _result(False, "Khong backup duoc /etc/fstab.", str(exc))

    # 2. Ghi append (luon bat dau bang \n de khong dinh vao dong cuoi cu).
    try:
        with fstab.open("a", encoding="utf-8") as f:
            f.write(f"\n# FolderSync: mount o dia mang tu dong\n{line}\n")
    except OSError as exc:
        return _result(False, "Khong ghi duoc /etc/fstab.", str(exc))

    # 3. Doc lai va doi chieu: phai tang dung 1 entry va tim thay target.
    #    Neu file bi ghi loi (VD: dinh dong), khoi phuc backup ngay.
    entries_after = parse_fstab(fstab)
    from .mounts import find_entry as _find  # noqa: PLC0415

    if len(entries_after) != len(entries_before) + 1 or _find(entries_after, target=target) is None:
        shutil.copy2(backup, fstab)
        return _result(
            False,
            "Ghi fstab that bai (file sau khi ghi khong nhu mong doi) - da khoi phuc ban cu.",
        )
    info = _findmnt_info(fstab)
    msg = f"Da them vao fstab (backup: {backup.name})."
    return _result(True, msg, info)


def fstab_remove(target: str, fstab: Path = FSTAB_PATH) -> dict:
    entries = parse_fstab(fstab)
    if not any(e.mountpoint == target for e in entries):
        return _result(False, f'Khong tim thay dong fstab cho "{target}".')
    try:
        backup = _backup_fstab(fstab)
    except OSError as exc:
        return _result(False, "Khong backup duoc /etc/fstab.", str(exc))

    try:
        lines = fstab.read_text(encoding="utf-8").splitlines()
        kept = []
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2 and not ln.strip().startswith("#") and parts[1] == target:
                continue
            kept.append(ln)
        fstab.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as exc:
        return _result(False, "Khong ghi duoc /etc/fstab.", str(exc))

    # Doi chieu: so entry phai giam dung 1 va khong con target.
    from .mounts import find_entry as _find  # noqa: PLC0415

    entries_after = parse_fstab(fstab)
    if len(entries_after) != len(entries) - 1 or _find(entries_after, target=target) is not None:
        shutil.copy2(backup, fstab)
        return _result(False, "Loi sau khi xoa - da khoi phuc ban cu.")
    return _result(True, f"Da xoa khoi fstab (backup: {backup.name}).")


def fstab_verify(fstab: Path = FSTAB_PATH) -> dict:
    """Kiem tra fstab: dem so dong khong parse duoc (parse error that su).
    findmnt con bao ca van de ngu nghia (VD: share offline) - nhung thong tin
    nay chi de tham khao, khong tinh la loi cu phap."""
    try:
        lines = fstab.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return _result(False, "Khong doc duoc /etc/fstab.", str(exc))
    bad = [
        (i + 1, ln)
        for i, ln in enumerate(lines)
        if ln.strip() and not ln.strip().startswith("#") and len(ln.split()) < 4
    ]
    info = _findmnt_info(fstab)
    if bad:
        detail = "\n".join(f"dong {n}: {ln}" for n, ln in bad)
        if info:
            detail += "\n--- findmnt --verify ---\n" + info
        return _result(False, f"Phat hien {len(bad)} dong loi cu phap trong fstab!", detail)
    msg = "Khong phat hien loi cu phap trong /etc/fstab."
    return _result(True, msg, info)


# ---------------------------------------------------------------- mount/umount
def ensure_mountpoint(target: str) -> dict:
    try:
        Path(target).mkdir(parents=True, exist_ok=True)
        return _result(True, f"Da tao diem mount {target}.")
    except OSError as exc:
        return _result(False, f"Khong tao duoc diem mount {target}.", str(exc))


def mount_target(target: str) -> dict:
    code, _out, err = _run(["mount", target])
    if code != 0:
        # mount khong bao loi neu da mount roi? -> kiem tra ismount cho chac.
        if not os.path.ismount(target):
            return _result(False, f"Khong mount duoc {target}.", _friendly_mount_error(err))
    if os.path.ismount(target):
        return _result(True, f"Da mount {target}.")
    return _result(False, f"Khong mount duoc {target}.", _friendly_mount_error(err))


def umount_target(target: str) -> dict:
    if not os.path.ismount(target):
        return _result(True, f"{target} hien khong duoc mount.")
    code, _out, err = _run(["umount", target])
    if code != 0:
        return _result(False, f"Khong go duoc {target} (co the dang duoc su dung).", err)
    return _result(True, f"Da go mount {target}.")


# ---------------------------------------------------------------- credentials
def write_credentials(path: str, username: str, password: str, domain: str = "") -> dict:
    try:
        cred = Path(path)
        cred.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cred.parent, 0o700)
        except OSError:
            pass
        lines = [f"username={username}", f"password={password}"]
        if domain:
            lines.append(f"domain={domain}")
        # Ghi qua file tam roi doi ten de khong lo thoi diem file chua ghi xong.
        tmp = cred.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(cred)
        os.chmod(cred, 0o600)
        return _result(True, f"Da luu credentials (quyen 600) tai {cred}.")
    except OSError as exc:
        return _result(False, "Khong luu duoc file credentials.", str(exc))


# ---------------------------------------------------------------- CLI
def _cmd_test_mount(ns: argparse.Namespace) -> dict:
    return test_mount(ns.source, ns.options)


def _cmd_fstab_add(ns: argparse.Namespace) -> dict:
    return fstab_add(ns.line, Path(ns.fstab))


def _cmd_fstab_remove(ns: argparse.Namespace) -> dict:
    return fstab_remove(ns.target, Path(ns.fstab))


def _cmd_fstab_verify(ns: argparse.Namespace) -> dict:
    return fstab_verify(Path(ns.fstab))


def _cmd_ensure_mountpoint(ns: argparse.Namespace) -> dict:
    return ensure_mountpoint(ns.target)


def _cmd_mount_target(ns: argparse.Namespace) -> dict:
    return mount_target(ns.target)


def _cmd_umount_target(ns: argparse.Namespace) -> dict:
    return umount_target(ns.target)


def _cmd_write_credentials(ns: argparse.Namespace) -> dict:
    password = sys.stdin.read().strip()
    if not password:
        return _result(False, "Mat khau rong.")
    return write_credentials(ns.path, ns.username, password, ns.domain or "")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="foldersync.privileged")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("test-mount")
    s.add_argument("--source", required=True)
    s.add_argument("--options", required=True)
    s.set_defaults(func=_cmd_test_mount)

    s = sub.add_parser("fstab-add")
    s.add_argument("--line", required=True)
    s.add_argument("--fstab", default=str(FSTAB_PATH))
    s.set_defaults(func=_cmd_fstab_add)

    s = sub.add_parser("fstab-remove")
    s.add_argument("--target", required=True)
    s.add_argument("--fstab", default=str(FSTAB_PATH))
    s.set_defaults(func=_cmd_fstab_remove)

    s = sub.add_parser("fstab-verify")
    s.add_argument("--fstab", default=str(FSTAB_PATH))
    s.set_defaults(func=_cmd_fstab_verify)

    s = sub.add_parser("ensure-mountpoint")
    s.add_argument("--target", required=True)
    s.set_defaults(func=_cmd_ensure_mountpoint)

    s = sub.add_parser("mount-target")
    s.add_argument("--target", required=True)
    s.set_defaults(func=_cmd_mount_target)

    s = sub.add_parser("umount-target")
    s.add_argument("--target", required=True)
    s.set_defaults(func=_cmd_umount_target)

    s = sub.add_parser("write-credentials")
    s.add_argument("--path", required=True)
    s.add_argument("--username", required=True)
    s.add_argument("--domain", default="")
    s.set_defaults(func=_cmd_write_credentials)  # password doc tu stdin
    return p


def run_privileged(args: list[str], stdin_text: str | None = None, timeout: int = 120) -> dict:
    """Chay 1 lenh privileged, tu them pkexec neu khong phai root.
    Tra ve dict JSON tu helper."""
    app_root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "-m", "foldersync.privileged", *args]
    if os.geteuid() != 0:
        if not shutil.which("pkexec"):
            return _result(False, "Khong tim thay pkexec de xin quyen root.")
        cmd = ["pkexec", *cmd]
    try:
        proc = subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True,
            cwd=str(app_root), timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _result(False, "Het thoi gian cho thao tac.")
    except OSError as exc:
        return _result(False, "Khong chay duoc lenh.", str(exc))

    # pkexec co the bi huy boi nguoi dung -> stdout rong.
    stdout = (proc.stdout or "").strip()
    if not stdout:
        err = (proc.stderr or "").strip()
        if proc.returncode == 127:
            return _result(False, "Nguoi dung da huy xac thuc (khong co quyen root).")
        return _result(False, "Lenh khong tra ve ket qua.", err)
    try:
        return json.loads(stdout.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return _result(False, "Ket qua tra ve khong hop le.", stdout[-500:])


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    result = ns.func(ns)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
