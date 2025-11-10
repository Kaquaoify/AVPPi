"""Persistent application state handling."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from copy import deepcopy

from .settings import AppConfig


class StateManager:
    """Thread-safe JSON backed state storage."""

    def __init__(self, state_path: Path, config: AppConfig) -> None:
        self._path = state_path
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = {}
        self._config = config
        self._load_or_create()

    def _load_or_create(self) -> None:
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as handle:
                    self._state = json.load(handle)
            except json.JSONDecodeError:
                self._state = {}
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._state = {}
        self._state.setdefault("language", self._config.default_language)
        self._state.setdefault(
            "rclone",
            {
                "token": "",
                "remote_path": self._config.remote_path,
                "remote_name": self._config.remote_name,
            },
        )
        self._state.setdefault("volume_level", 80)
        self._state.setdefault("schedule", self._default_schedule())
        self._state.setdefault("sync_schedule", self._default_sync_schedule())
        self._persist_unlocked()

    def _default_schedule(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "start": "08:00",
            "end": "20:00",
            "days": list(range(7)),
        }

    def _default_sync_schedule(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "time": "06:00",
            "last_run_date": "",
        }

    def _persist_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(self._state, handle, indent=2)

    def save(self) -> None:
        with self._lock:
            self._persist_unlocked()

    def get_language(self) -> str:
        with self._lock:
            return str(self._state.get("language", self._config.default_language))

    def set_language(self, language: str) -> None:
        with self._lock:
            self._state["language"] = language
            self._persist_unlocked()

    def get_volume_level(self) -> int:
        with self._lock:
            return int(self._state.get("volume_level", 80))

    def set_volume_level(self, level: int) -> None:
        with self._lock:
            self._state["volume_level"] = int(level)
            self._persist_unlocked()

    def get_schedule_settings(self) -> Dict[str, Any]:
        with self._lock:
            schedule = deepcopy(self._state.get("schedule", self._default_schedule()))
            schedule["enabled"] = bool(schedule.get("enabled", False))
            schedule["start"] = schedule.get("start", "08:00")
            schedule["end"] = schedule.get("end", "20:00")
            schedule["days"] = sorted(
                {int(day) for day in schedule.get("days", list(range(7))) if 0 <= int(day) <= 6}
            )
            return schedule

    def update_schedule_settings(
        self,
        *,
        enabled: Optional[bool] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: Optional[List[int]] = None,
    ) -> None:
        with self._lock:
            schedule = self._state.setdefault("schedule", self._default_schedule())
            if enabled is not None:
                schedule["enabled"] = bool(enabled)
            if start is not None:
                schedule["start"] = self._validate_time_string(start)
            if end is not None:
                schedule["end"] = self._validate_time_string(end)
            if days is not None:
                cleaned = sorted({int(day) for day in days if 0 <= int(day) <= 6})
                if schedule.get("enabled") and not cleaned:
                    raise ValueError("At least one day must be selected when the schedule is enabled.")
                schedule["days"] = cleaned
            self._persist_unlocked()

    def get_sync_schedule_settings(self) -> Dict[str, Any]:
        with self._lock:
            schedule = deepcopy(self._state.get("sync_schedule", self._default_sync_schedule()))
            schedule["enabled"] = bool(schedule.get("enabled", True))
            schedule["time"] = schedule.get("time", "06:00")
            schedule["last_run_date"] = schedule.get("last_run_date", "")
            return schedule

    def update_sync_schedule_settings(
        self,
        *,
        enabled: Optional[bool] = None,
        time: Optional[str] = None,
    ) -> None:
        with self._lock:
            schedule = self._state.setdefault("sync_schedule", self._default_sync_schedule())
            if enabled is not None:
                schedule["enabled"] = bool(enabled)
            if time is not None:
                schedule["time"] = self._validate_time_string(time)
            if schedule.get("enabled", True):
                schedule["last_run_date"] = ""
            self._persist_unlocked()

    def set_sync_last_run(self, date_str: str) -> None:
        with self._lock:
            schedule = self._state.setdefault("sync_schedule", self._default_sync_schedule())
            schedule["last_run_date"] = date_str
            self._persist_unlocked()

    @staticmethod
    def _validate_time_string(value: str) -> str:
        try:
            parsed = datetime.strptime(value.strip(), "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must be provided as HH:MM (24h).") from exc
        return parsed.strftime("%H:%M")

    def get_rclone_settings(self) -> Dict[str, Any]:
        with self._lock:
            rclone = dict(self._state.get("rclone", {}))
            rclone.setdefault("remote_name", self._config.remote_name)
            rclone.setdefault("remote_path", self._config.remote_path)
            return rclone

    def update_rclone_settings(
        self, *, token: Optional[str] = None, remote_path: Optional[str] = None
    ) -> None:
        with self._lock:
            rclone = self._state.setdefault("rclone", {})
            if token is not None:
                rclone["token"] = token
            if remote_path is not None:
                rclone["remote_path"] = remote_path
            rclone.setdefault("remote_name", self._config.remote_name)
            self._persist_unlocked()
