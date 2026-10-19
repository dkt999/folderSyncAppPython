"""Tu khoi dong cung he thong - port tu Registry Run ben Windows.

Tren Ubuntu dung XDG autostart: file ~/.config/autostart/FolderSync.desktop
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_FILE = AUTOSTART_DIR / "FolderSync.desktop"


def _exec_command() -> str:
    """Lenh khoi dong app, mo an (minimized) xuong tray."""
    # main.py nam cung thu muc voi package foldersync.
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{sys.executable}" "{main_py}" --minimized'


def _desktop_content() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=FolderSync\n"
        "Comment=Cong cu dong bo thu muc theo lich\n"
        f"Exec={_exec_command()}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def is_autostart_enabled() -> bool:
    return DESKTOP_FILE.exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(_desktop_content(), encoding="utf-8")
        DESKTOP_FILE.chmod(0o644)
    else:
        try:
            DESKTOP_FILE.unlink()
        except FileNotFoundError:
            pass
