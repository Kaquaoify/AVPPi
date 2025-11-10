"""Playback watchdog to detect frozen VLC playback."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .vlc_controller import VLCController


class PlaybackWatchdog:
    """Monitor VLC playback and trigger a recovery if it appears stuck."""

    def __init__(
        self,
        controller: VLCController,
        logger: Optional[logging.Logger] = None,
        poll_interval: int = 10,
        freeze_threshold: int = 30,
        min_progress_ms: int = 500,
    ) -> None:
        self._controller = controller
        self._logger = (logger or logging.getLogger("avppi")).getChild("watchdog")
        self._poll_interval = poll_interval
        self._freeze_threshold = freeze_threshold
        self._min_progress_ms = min_progress_ms
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="PlaybackWatchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        previous_snapshot = None
        stalled_duration = 0
        while not self._stop.wait(self._poll_interval):
            try:
                snapshot = self._controller.get_snapshot()
            except Exception:  # pragma: no cover - defensive
                self._logger.exception("Failed to obtain VLC snapshot")
                continue

            if snapshot.state != "playing" or snapshot.position_ms < 0:
                stalled_duration = 0
                previous_snapshot = snapshot
                continue

            if (
                previous_snapshot
                and snapshot.media == previous_snapshot.media
                and abs(snapshot.position_ms - previous_snapshot.position_ms) < self._min_progress_ms
            ):
                stalled_duration += self._poll_interval
                if stalled_duration >= self._freeze_threshold:
                    self._logger.warning(
                        "Playback appears frozen on '%s'; initiating recovery", snapshot.media
                    )
                    try:
                        self._controller.recover_playback()
                    except Exception:
                        self._logger.exception("Failed to recover VLC playback")
                    stalled_duration = 0
            else:
                stalled_duration = 0

            previous_snapshot = snapshot
