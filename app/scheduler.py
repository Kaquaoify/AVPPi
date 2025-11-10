"""Background scheduler that applies playback windows."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time
from typing import Dict, Optional, Sequence

from .state_manager import StateManager
from .vlc_controller import VLCController


class PlaybackScheduler:
    """Check schedule configuration and toggle playback accordingly."""

    def __init__(
        self,
        state: StateManager,
        vlc: VLCController,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._state = state
        self._vlc = vlc
        self._logger = logger or logging.getLogger("avppi.scheduler")
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_active: Optional[bool] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="PlaybackScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=1)

    def request_check(self) -> None:
        """Wake the scheduler so the new configuration is applied quickly."""
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._evaluate_window()
            except Exception:  # pragma: no cover - defensive logging
                self._logger.exception("Playback schedule tick failed")
            finally:
                self._wait_with_wake(30)

    def _wait_with_wake(self, timeout: int) -> None:
        self._wake.wait(timeout=timeout)
        self._wake.clear()

    def _evaluate_window(self) -> None:
        config = self._state.get_schedule_settings()
        if not config.get("enabled"):
            if self._last_active is False:
                self._logger.info("Schedule disabled – resuming playback")
                self._vlc.play()
            self._last_active = None
            return
        active = self._is_within_window(config, datetime.now())
        previous = self._last_active
        self._last_active = active
        if previous is None:
            previous = not active
        if active and not previous:
            self._logger.info("Schedule window started – resuming playback")
            self._vlc.play()
        elif not active and previous:
            self._logger.info("Schedule window ended – pausing playback")
            self._vlc.pause()

    @staticmethod
    def _parse_time(value: str) -> time:
        return datetime.strptime(value, "%H:%M").time()

    def _is_within_window(self, config: Dict[str, object], now: datetime) -> bool:
        try:
            start = self._parse_time(str(config.get("start", "00:00")))
            end = self._parse_time(str(config.get("end", "00:00")))
        except ValueError:
            return False
        days = self._coerce_days(config.get("days", []))
        if not days:
            return False
        weekday = now.weekday()
        current_time = now.time()
        if start == end:
            return weekday in days
        if start < end:
            return weekday in days and start <= current_time < end
        # Overnight schedule (e.g. 20:00 -> 06:00)
        if weekday in days and current_time >= start:
            return True
        previous_day = (weekday - 1) % 7
        if previous_day in days and current_time < end:
            return True
        return False

    @staticmethod
    def _coerce_days(days: object) -> Sequence[int]:
        try:
            candidates = {int(day) for day in days}  # type: ignore[arg-type]
        except TypeError:
            return []
        return sorted(day for day in candidates if 0 <= day <= 6)
