"""Playback watchdog to detect frozen VLC playback."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .vlc_controller import VLCController


class PlaybackWatchdog:
    """Monitor VLC playback and drop files that remain stuck."""

    def __init__(
        self,
        controller: VLCController,
        logger: Optional[logging.Logger] = None,
        poll_interval: int = 5,
        freeze_threshold: int = 10,
        min_runtime_ms: int = 3000,
    ) -> None:
        self._controller = controller
        self._logger = (logger or logging.getLogger("avppi")).getChild("watchdog")
        self._poll_interval = poll_interval
        self._freeze_threshold = freeze_threshold
        self._min_runtime_ms = min_runtime_ms
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
        last_position: Optional[int] = None
        stalled_duration = 0
        max_position = 0
        current_media = ""
        while not self._stop.wait(self._poll_interval):
            try:
                snapshot = self._controller.get_snapshot()
            except Exception:  # pragma: no cover
                self._logger.exception("Failed to obtain VLC snapshot")
                continue

            media_name = snapshot.media or ""

            if not media_name:
                current_media = ""
                stalled_duration = 0
                max_position = 0
                last_position = snapshot.position_ms
                continue

            if media_name != current_media:
                stalled_duration = 0
                max_position = 0
                current_media = media_name

            if snapshot.state != "playing" or snapshot.position_ms < 0:
                stalled_duration = 0
                last_position = snapshot.position_ms
                continue

            if last_position is None or snapshot.position_ms > last_position:
                stalled_duration = 0
                max_position = max(max_position, snapshot.position_ms)
            else:
                stalled_duration += self._poll_interval

            if (
                stalled_duration >= self._freeze_threshold
                and current_media
                and max_position >= self._min_runtime_ms
            ):
                removed = self._controller.remove_current_media()
                if removed:
                    self._logger.warning("Removed frozen media '%s' from playlist", removed)
                else:
                    self._logger.warning("Playback frozen but no media could be removed")
                stalled_duration = 0
                max_position = 0
                current_media = ""

            last_position = snapshot.position_ms
