"""Daily rclone synchronisation scheduler."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time
from typing import Optional

import asyncio

from .state_manager import StateManager


class SyncScheduler:
    """Trigger rclone sync once per day at a configured time."""

    def __init__(
        self,
        state: StateManager,
        core: "ApplicationCore",  # type: ignore[name-defined]
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._state = state
        self._core = core
        self._logger = (logger or logging.getLogger("avppi")).getChild("sync_scheduler")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="SyncScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._evaluate()
            except Exception:  # pragma: no cover - defensive
                self._logger.exception("Unexpected exception in sync scheduler loop")
            finally:
                self._stop.wait(timeout=60)

    def _evaluate(self) -> None:
        config = self._state.get_sync_schedule_settings()
        if not config.get("enabled"):
            return
        target = self._parse_time(str(config.get("time", "06:00")))
        now = datetime.now()
        if now.time() < target:
            return
        last_run = config.get("last_run_date") or ""
        today = now.date().isoformat()
        if last_run == today:
            return
        if self._core.rclone.is_busy():
            self._logger.info("Skipping scheduled sync because rclone is already running")
            return
        self._logger.info("Scheduled rclone sync triggered at %s", now.strftime("%H:%M"))
        if self._trigger_sync():
            self._state.set_sync_last_run(today)

    def _trigger_sync(self) -> bool:
        loop = getattr(self._core, "loop", None)
        if loop and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._core.sync_and_reload(), loop)
                future.result()
                return True
            except Exception:
                self._logger.exception("Scheduled rclone sync failed")
                return False
        self._logger.warning("Cannot run scheduled sync: event loop unavailable")
        return False

    @staticmethod
    def _parse_time(value: str) -> time:
        return datetime.strptime(value, "%H:%M").time()


__all__ = ["SyncScheduler"]
