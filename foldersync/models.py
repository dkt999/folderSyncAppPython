"""Model du lieu - port tu Models.cs (BackupTask)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date


@dataclass
class BackupTask:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Task backup"
    source: str = ""
    destination: str = ""
    mirror: bool = False
    enabled: bool = True
    # Gio chay hang ngay, moi phan tu dang "HH:mm" (24h).
    scheduled_times: list[str] = field(default_factory=list)

    last_run_utc: str | None = None      # ISO 8601 UTC
    last_run_success: bool | None = None
    last_exit_code: int | None = None
    last_run_summary: str = ""

    # Cac truong runtime, KHONG luu xuong file (tuong duong [XmlIgnore] ben C#).
    is_running: bool = field(default=False, repr=False, compare=False)
    fired_slots_today: set[str] = field(default_factory=set, repr=False, compare=False)
    fired_slots_date: date | None = field(default=None, repr=False, compare=False)
    # % hoan thanh lan chay hien tai (0-100). -1 = chua co du lieu.
    progress: int = field(default=-1, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "destination": self.destination,
            "mirror": self.mirror,
            "enabled": self.enabled,
            "scheduled_times": list(self.scheduled_times),
            "last_run_utc": self.last_run_utc,
            "last_run_success": self.last_run_success,
            "last_exit_code": self.last_exit_code,
            "last_run_summary": self.last_run_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupTask":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "Task backup"),
            source=str(data.get("source") or ""),
            destination=str(data.get("destination") or ""),
            mirror=bool(data.get("mirror", False)),
            enabled=bool(data.get("enabled", True)),
            scheduled_times=[str(t) for t in data.get("scheduled_times", [])],
            last_run_utc=data.get("last_run_utc"),
            last_run_success=data.get("last_run_success"),
            last_exit_code=data.get("last_exit_code"),
            last_run_summary=str(data.get("last_run_summary") or ""),
        )
