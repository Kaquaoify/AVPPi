"""Lightweight playback watchdog that restarts VLC if playback stalls."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from .vlc_controller import PlaybackSnapshot, VLCController


class PlaybackWatchdog:
    """Monitor VLC position and restart playback when it stops advancing."""

    def __init__(
        self,
        controller: VLCController,
        logger: logging.Logger,
        check_interval: float = 2.0,
        freeze_window: float = 10.0,
        min_progress_ms: int = 750,
        restart_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._controller = controller
        self._logger = logger
        self._check_interval = check_interval
        self._freeze_window = freeze_window
        self._min_progress_ms = min_progress_ms
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._restart_callback = restart_callback
        self._restart_pending = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="PlaybackWatchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # Internal helpers -------------------------------------------------

    def _run(self) -> None:
        last_snapshot: Optional[PlaybackSnapshot] = None
        last_progress_time = time.monotonic()
        while not self._stop_event.wait(self._check_interval):
            snapshot = self._controller.get_snapshot()
            now = time.monotonic()
            if snapshot.state not in {"playing", "buffering"}:
                last_snapshot = snapshot
                last_progress_time = now
                continue

            progressed = self._has_progressed(snapshot, last_snapshot)
            if progressed:
                last_progress_time = now
                self._restart_pending = False
            elif now - last_progress_time >= self._freeze_window:
                self._handle_freeze(snapshot)
                last_progress_time = now
            last_snapshot = snapshot

    def _has_progressed(
        self, current: PlaybackSnapshot, previous: Optional[PlaybackSnapshot]
    ) -> bool:
        if previous is None:
            return True
        if current.media != previous.media:
            return True
        if current.position_ms < previous.position_ms - 1000:
            return True
        if current.position_ms - previous.position_ms >= self._min_progress_ms:
            return True
        return False

    def _handle_freeze(self, snapshot: PlaybackSnapshot) -> None:
        media = snapshot.media or "<unknown>"
        if self._restart_pending:
            return
        self._restart_pending = True
        self._logger.warning("Playback frozen on '%s'; restarting application", media)
        if not self._restart_callback:
            return
        try:
            self._restart_callback(media)
        except Exception:
            self._logger.exception("Failed to trigger restart for '%s'", media)
