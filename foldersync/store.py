"""Luu/doc danh sach task - port tu TaskStore.cs.

Ben C# luu XML o %AppData%\\FolderSyncApp\\tasks.xml.
Ben Linux luu JSON o ~/.config/FolderSyncApp/tasks.json (JSON gon hon XML).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import BackupTask

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "FolderSyncApp"
TASKS_FILE = CONFIG_DIR / "tasks.json"


def load_tasks(path: Path | None = None) -> list[BackupTask]:
    """Doc danh sach task. File loi hoac khong doc duoc -> tra ve list rong
    (khong crash app), giong hanh vi try/catch ben C#."""
    file_path = path or TASKS_FILE
    try:
        if not file_path.exists():
            return []
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = [BackupTask.from_dict(item) for item in data]
        # Loai bo task trung id (phong file bi ghi loi).
        seen: set[str] = set()
        unique: list[BackupTask] = []
        for t in tasks:
            if t.id not in seen:
                seen.add(t.id)
                unique.append(t)
        return unique
    except Exception as exc:  # noqa: BLE001 - giong C#: file loi thi bat dau list trong
        log.warning("Khong doc duoc %s (%s), dung danh sach trong.", file_path, exc)
        return []


def save_tasks(tasks: list[BackupTask], path: Path | None = None) -> None:
    file_path = path or TASKS_FILE
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tasks], f, ensure_ascii=False, indent=2)
    tmp_path.replace(file_path)
