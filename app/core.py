"""Application core wiring helpers."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import List, Optional

from .media_catalog import MediaItem, scan_media
from .rclone_manager import RcloneManager, RcloneCommandResult
from .settings import AppConfig
from .state_manager import StateManager
from .scheduler import PlaybackScheduler
from .sanitizer import MediaSanitizer
from .sync_scheduler import SyncScheduler
from .vlc_controller import VLCController, VLCError


class ApplicationCore:
    """Holds the main services used by the FastAPI layer."""

    def __init__(self, config: AppConfig, state_path: Path) -> None:
        self.config = config
        self.state = StateManager(state_path, config)
        self._logger = logging.getLogger("avppi")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.vlc = VLCController(config, self.state)
        self.rclone = RcloneManager(config, self.state)
        self._media_items: List[MediaItem] = []
        self._media_lock = threading.RLock()
        self._sync_lock = asyncio.Lock()
        self.scheduler = PlaybackScheduler(self.state, self.vlc, self._logger.getChild("scheduler"))
        self.sync_scheduler = SyncScheduler(self.state, self, self._logger)
        self.sanitizer = MediaSanitizer(config, self._logger.getChild("sanitizer"))

    def initialise(self) -> None:
        """Load media and start playback on startup."""
        self._logger.info("Initialising application core")
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        media = scan_media(self.config.media_directory)
        with self._media_lock:
            self._media_items = media
        if media:
            try:
                self.vlc.load_playlist(media)
                self.vlc.set_volume_percent(self.state.get_volume_level())
                self.vlc.play()
                self._logger.info("Playback started with %d items", len(media))
            except VLCError as exc:
                self._logger.exception("Failed to start playback: %s", exc)
        else:
            self._logger.warning("No media files found in %s", self.config.media_directory)
        self.scheduler.start()
        self.sync_scheduler.start()
        self._run_startup_sync()

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._loop

    def list_media(self) -> List[MediaItem]:
        with self._media_lock:
            return list(self._media_items)

    def get_media_by_name(self, filename: str) -> Optional[MediaItem]:
        with self._media_lock:
            for item in self._media_items:
                if item.name == filename:
                    return item
        return None

    def insert_after_current(self, filename: str) -> bool:
        item = self.get_media_by_name(filename)
        if not item:
            return False
        try:
            self.vlc.insert_after_current(item)
        except VLCError as exc:
            self._logger.error("Failed to insert %s: %s", filename, exc)
            return False
        return True

    def rescan_media(self, autoplay: bool = True) -> List[MediaItem]:
        media = scan_media(self.config.media_directory)
        with self._media_lock:
            self._media_items = media
        if media:
            try:
                self.vlc.load_playlist(media)
                if autoplay:
                    self.vlc.play()
            except VLCError as exc:
                self._logger.error("Failed to rebuild VLC playlist: %s", exc)
        else:
            try:
                self.vlc.stop()
            except VLCError as exc:
                self._logger.warning("Failed to stop VLC during rescan: %s", exc)
        return media

    async def sync_and_reload(self) -> RcloneCommandResult:
        """Run rclone sync, rebuild playlist, and restart playback."""
        async with self._sync_lock:
            self._logger.info("Starting sync operation")
            result = await asyncio.to_thread(self.rclone.sync_media)
            self._logger.info("Sync result: success=%s", result.success)
            media = self.rescan_media(autoplay=False)
            if media:
                try:
                    self.vlc.play()
                except VLCError as exc:
                    self._logger.error("Failed to restart playback after sync: %s", exc)
            return result

    async def run_rclone_test(self) -> RcloneCommandResult:
        async with self._sync_lock:
            return await asyncio.to_thread(self.rclone.test_connection)

    async def update_rclone_config(self, token: str, remote_path: Optional[str]) -> Path:
        async with self._sync_lock:
            return await asyncio.to_thread(self.rclone.update_config, token, remote_path)

    async def sanitize_media(self) -> List[str]:
        async with self._sync_lock:
            self._logger.info("Starting media sanitisation")
            self.vlc.stop()
            sanitized = await asyncio.to_thread(self.sanitizer.sanitize)
            media = self.rescan_media()
            if media:
                self.vlc.play()
            return sanitized

    def _run_startup_sync(self) -> None:
        async def _task() -> None:
            try:
                self._logger.info("Running startup rclone sync")
                await self.sync_and_reload()
            except Exception:
                self._logger.exception("Startup sync failed")

        loop = self.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_task(), loop)
        else:
            try:
                asyncio.run(_task())
            except Exception:
                self._logger.exception("Startup sync failed (loop unavailable)")
