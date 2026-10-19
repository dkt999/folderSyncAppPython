"""Logic quan ly mount SMB/CIFS - phan thuan (khong can root, khong can Qt).

Quy trinh an toan khi them o dia mang vao /etc/fstab:
  1. Mount THU vao thu muc tam (khong dung cham gi den fstab).
  2. Chi khi mount thu thanh cong moi cho phep ghi fstab.
  3. Truoc khi ghi: backup /etc/fstab, kiem tra trung lap.
  4. Sau khi ghi: validate cu phap bang `findmnt --verify` (fallback `mount -fav`).
  5. Entry LUON co `nofail` -> o mang loi may van boot binh thuong,
     va `_netdev` -> systemd hieu la o mang, mount sau khi co mang.
"""
from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path

FSTAB_PATH = Path("/etc/fstab")
PROC_MOUNTS = Path("/proc/mounts")
CREDENTIALS_DIR = Path("/etc/samba/credentials")


@dataclass
class FstabEntry:
    device: str
    mountpoint: str
    fstype: str
    options: str
    dump: str = "0"
    fsck: str = "0"


def normalize_source(source: str) -> str:
    """Chuan hoa dia chi share: chap nhan ca dang smb://... paste tu Files,
    tra ve dang //server/share."""
    s = source.strip()
    if s.lower().startswith("smb://"):
        s = "//" + s[6:]
    s = s.replace("%20", " ")
    return s.rstrip("/")


def escape_fstab(value: str) -> str:
    """Escape khoang trang theo chuan fstab: ' ' -> '\\040'.
    fstab tach field bang khoang trang nen device/target co dau cach
    (VD: //server/02. share) BAT BUOC phai escape, khong la vo dong fstab."""
    return value.replace("\\", "\\134").replace(" ", "\\040")


def unescape_fstab(value: str) -> str:
    """Nguoc lai cua escape_fstab (dung khi doc fstab de hien thi)."""
    return value.replace("\\040", " ").replace("\\134", "\\")


def server_of(source: str) -> str:
    """Lay ten may tu '//server/share'."""
    parts = normalize_source(source).split("/")
    return parts[2] if len(parts) > 2 else ""


def resolve_server(server: str) -> str | None:
    """Phan giai ten may thanh IP. Tra ve None neu khong phan giai duoc.

    Luu y: Nautilus (Files) tu do tim may trong mang (NetBIOS/WSD) nen mo duoc
    smb://ten-may/...; nhung mount qua kernel (mount.cifs) can ten phan giai
    duoc qua DNS he thong. Neu None -> nen dung dia chi IP thay cho ten may.
    """
    try:
        return socket.gethostbyname(server)
    except (socket.gaierror, UnicodeError):
        return None


def normalize_target(raw: str) -> str:
    """Chuan hoa diem mount thanh '/mnt/<ten>'.
    Nguoi dung chi can go ten (VD: COM0068Share); co go thua '/mnt/'
    hay '/mnt/ten' vao cung tu chuan hoa, khong bao gio bi lap '/mnt/mnt/'."""
    t = raw.strip().strip("/")
    if not t or t.lower() == "mnt":
        return ""
    if t.lower().startswith("mnt/"):
        t = t[4:].strip("/")
    if not t:
        return ""
    return "/mnt/" + t


def validate_source(source: str) -> str | None:
    """Kiem tra dinh dang //server/share. Tra ve None neu hop le,
    nguoc lai tra ve thong bao loi tieng Viet."""
    s = normalize_source(source)
    if not s.startswith("//"):
        return 'Dia chi share phai bat dau bang "//", VD: //192.168.1.10/du-lieu'
    rest = s[2:]
    if "/" not in rest:
        return 'Thieu ten share, VD: //192.168.1.10/du-lieu'
    server, share = rest.split("/", 1)
    if not server or not share or "/" in share:
        return 'Dinh dang phai la //server/share (khong them duong dan con)'
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", server):
        return f'Ten server/IP "{server}" co ky tu khong hop le'
    if not re.fullmatch(r"[^/\\\\]+", share):
        return f'Ten share "{share}" khong hop le'
    return None


def validate_target(target: str) -> str | None:
    # target da qua normalize_target -> luon dang '/mnt/<ten>' hoac rong.
    t = target.strip()
    if not t:
        return "Nhap ten diem mount, VD: COM0068Share"
    if not t.startswith("/"):
        return "Diem mount phai la duong dan tuyet doi, VD: /mnt/du-lieu"
    if t in ("/", "/etc", "/bin", "/usr", "/var", "/home", "/root", "/boot"):
        return f'Khong duoc mount de len thu muc he thong "{t}"'
    # Dau cach o diem mount duoc chap nhan - luc ghi fstab se tu escape \040.
    return None


def credentials_path_for(target: str) -> Path:
    """Duong dan file chua username/password cho 1 diem mount."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(target).name or "share")
    return CREDENTIALS_DIR / f"foldersync-{safe}.cred"


def build_options(
    uid: int,
    gid: int,
    cred_path: Path | None = None,
    guest: bool = False,
) -> str:
    """Dung file credentials (mat khau KHONG nam trong fstab)."""
    opts: list[str] = []
    if guest:
        opts.append("guest")
    elif cred_path is not None:
        opts.append(f"credentials={cred_path}")
    opts += [
        f"uid={uid}",
        f"gid={gid}",
        "iocharset=utf8",
        "_netdev",  # bao systemd: day la o mang, cho co mang roi moi mount
        "nofail",   # QUAN TRONG: o mang loi -> bo qua, may van boot binh thuong
    ]
    return ",".join(opts)


def build_fstab_line(source: str, target: str, options: str) -> str:
    source = normalize_source(source)
    return f"{escape_fstab(source)}  {escape_fstab(target)}  cifs  {options}  0  0"


def parse_fstab(path: Path = FSTAB_PATH) -> list[FstabEntry]:
    entries: list[FstabEntry] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        entries.append(
            FstabEntry(
                device=unescape_fstab(parts[0]),
                mountpoint=unescape_fstab(parts[1]),
                fstype=parts[2],
                options=parts[3],
                dump=parts[4] if len(parts) > 4 else "0",
                fsck=parts[5] if len(parts) > 5 else "0",
            )
        )
    return entries


def find_entry(
    entries: list[FstabEntry], target: str | None = None, source: str | None = None
) -> FstabEntry | None:
    for e in entries:
        if target is not None and e.mountpoint == target:
            return e
        if source is not None and normalize_source(e.device) == normalize_source(source):
            return e
    return None


def is_mounted(target: str, proc_mounts: Path = PROC_MOUNTS) -> bool:
    """Kiem tra diem mount co dang duoc mount khong (doc /proc/mounts).
    /proc/mounts cung escape dau cach thanh \\040 nen so ca 2 dang."""
    escaped = escape_fstab(target)
    try:
        for line in proc_mounts.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] in (target, escaped):
                return True
    except OSError:
        pass
    return False


def list_cifs_mounts(proc_mounts: Path = PROC_MOUNTS) -> list[tuple[str, str]]:
    """Tra ve [(device, mountpoint)] cua cac mount cifs hien tai."""
    result: list[tuple[str, str]] = []
    try:
        for line in proc_mounts.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "cifs":
                result.append((parts[0], parts[1]))
    except OSError:
        pass
    return result


def has_nofail(options: str) -> bool:
    return "nofail" in (o.strip() for o in options.split(","))


def current_uid_gid() -> tuple[int, int]:
    return os.getuid(), os.getgid()
