"""VLC playback controller for desktop environments."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

import vlc

from .media_catalog import MediaItem, build_vlc_playlist_args
from .settings import AppConfig
from .state_manager import StateManager


class VLCError(Exception):
    """Base exception for VLC control issues."""


@dataclass
class PlaybackSnapshot:
    media: str
    position_ms: int
    state: str


def _build_state_labels() -> Dict[int, str]:
    labels = {
        "NothingSpecial": "nothing_special",
        "Opening": "opening",
        "Buffering": "buffering",
        "Playing": "playing",
        "Paused": "paused",
        "Stopped": "stopped",
        "Ended": "ended",
        "Error": "error",
    }
    resolved: Dict[int, str] = {}
    for attr, label in labels.items():
        state_value = getattr(vlc.State, attr, None)
        if state_value is None:
            continue
        try:
            resolved[int(state_value)] = label
        except (TypeError, ValueError):
            continue
    return resolved


class VLCController:
    """Manage VLC playback via libVLC bindings."""

    _STATE_LABELS = _build_state_labels()

    def __init__(self, config: AppConfig, state: StateManager) -> None:
        self._config = config
        self._state = state
        self._logger = logging.getLogger("avppi.playback")
        self._instance = vlc.Instance(config.vlc_options or ["--quiet"])
        self._media_list = self._instance.media_list_new()
        self._player = self._instance.media_list_player_new()
        self._player.set_media_list(self._media_list)
        self._media_player = self._player.get_media_player()
        self._player.set_playback_mode(vlc.PlaybackMode.loop)
        self._media_lock = threading.RLock()
        self._playlist: List[MediaItem] = []
        self._current_background: Optional[vlc.Media] = None

    # Playlist handling -------------------------------------------------

    def load_playlist(self, items: List[MediaItem]) -> None:
        """Replace VLC playlist with items from the media directory."""
        self._set_playlist(items, start_index=0)

    def insert_after_current(self, item: MediaItem) -> None:
        with self._media_lock:
            try:
                media = self._instance.media_new_path(str(item.path))
                current_media = self._media_player.get_media()
                current_index = (
                    self._media_list.index_of_item(current_media) if current_media else -1
                )
                target = current_index + 1 if current_index >= 0 else self._media_list.count()
                self._media_list.insert_media(media, target)
                if target >= len(self._playlist):
                    self._playlist.append(item)
                else:
                    self._playlist.insert(target, item)
                self._logger.info("Inserted %s at position %s", item.name, target)
            except Exception as exc:  # pragma: no cover - libVLC exceptions are opaque
                raise VLCError(f"Impossible d'insérer {item.name}: {exc}") from exc

    def _clear_media_list(self) -> None:
        self._media_list.lock()
        try:
            for index in reversed(range(self._media_list.count())):
                self._media_list.remove_index(index)
        finally:
            self._media_list.unlock()

    def _load_background_clip(self) -> None:
        background = self._instance.media_new(self._config.vlc_background_media)
        self._clear_media_list()
        self._media_list.add_media(background)
        self._current_background = background
        self.play()

    def _rebuild_media_list(self) -> None:
        self._clear_media_list()
        if not self._playlist:
            self._logger.info("Playlist is empty; loading fallback background.")
            self._load_background_clip()
            return
        for path in build_vlc_playlist_args(self._playlist):
            media = self._instance.media_new_path(path)
            self._media_list.add_media(media)

    def _play_index(self, index: int) -> None:
        self._player.stop()
        try:
            media = self._media_list.item_at_index(index)
        except Exception:
            media = None
        if media:
            self._player.play_item(media)
        else:
            self._player.play()

    # Playback controls -------------------------------------------------

    def play(self) -> None:
        with self._media_lock:
            self._player.play()

    def pause_toggle(self) -> None:
        with self._media_lock:
            self._media_player.pause()

    def pause(self) -> None:
        with self._media_lock:
            self._media_player.set_pause(1)

    def stop(self) -> None:
        with self._media_lock:
            self._player.stop()

    def next_track(self) -> None:
        with self._media_lock:
            self._player.next()

    def previous_track(self) -> None:
        with self._media_lock:
            self._player.previous()

    def set_volume_percent(self, percent: int) -> None:
        with self._media_lock:
            self._media_player.audio_set_volume(percent)
            self._state.set_volume_level(percent)

    def get_volume_percent(self) -> int:
        return max(0, self._media_player.audio_get_volume())

    # Status -------------------------------------------------------------

    def get_status(self) -> Dict[str, str]:
        media = self._media_player.get_media()
        mrl = media.get_mrl() if media else ""
        return {
            "state": self._derive_state_label(),
            "volume_percent": str(self.get_volume_percent()),
            "current_track": self._mrl_to_display_name(mrl),
        }

    def get_snapshot(self) -> PlaybackSnapshot:
        with self._media_lock:
            media = self._media_player.get_media()
            mrl = media.get_mrl() if media else ""
            return PlaybackSnapshot(
                media=self._mrl_to_display_name(mrl),
                position_ms=max(0, self._media_player.get_time()),
                state=self._derive_state_label(),
            )

    def recover_playback(self, skip: bool = False) -> None:
        """Attempt to recover when playback appears stuck."""
        with self._media_lock:
            self._logger.warning("Attempting VLC recovery cycle%s", " + skip" if skip else "")
            self._player.stop()
            time.sleep(0.5)
            if skip:
                self._player.next()
            else:
                self._player.play()

    def remove_current_media(self) -> Optional[str]:
        """Remove the currently playing media from the playlist and rebuild."""
        with self._media_lock:
            media = self._media_player.get_media()
            if not media:
                return None
            mrl = media.get_mrl()
            if not mrl:
                return None
            display_name = self._mrl_to_display_name(mrl)
            target_path = Path(unquote(mrl[7:])) if mrl.startswith("file://") else Path(mrl)
            before = len(self._playlist)
            target_str = str(target_path.resolve())
            new_playlist = [item for item in self._playlist if str(Path(item.path).resolve()) != target_str]
            if len(new_playlist) == before:
                return None
            self._logger.warning("Removed problematic media '%s' from playlist", display_name)
            removed_index = next(
                (i for i, item in enumerate(self._playlist) if str(Path(item.path).resolve()) == target_str),
                0,
            )
            self._playlist = new_playlist
            if self._playlist:
                next_index = removed_index if removed_index < len(self._playlist) else 0
                self._set_playlist(self._playlist, start_index=next_index)
            else:
                self._load_background_clip()
            return display_name

    def _derive_state_label(self) -> str:
        """Combine multiple libVLC signals to get a user-friendly state."""
        for raw in (self._player.get_state(), self._media_player.get_state()):
            label = self._state_to_text(raw)
            if label not in ("unknown", "nothing_special", ""):
                return label
        if self._media_player.is_playing() == 1:
            return "playing"
        if self._playlist:
            return "paused"
        return "stopped"

    def _state_to_text(self, state: Optional[vlc.State]) -> str:
        """Convert VLC state to a lower-case string without relying on Enum.name."""
        if state is None:
            return "unknown"
        name = getattr(state, "name", None)
        if isinstance(name, str):
            return self._normalize_state_name(name)
        if isinstance(state, str):
            return self._normalize_state_name(state)
        for attr in ("value", "real", "raw"):
            value = getattr(state, attr, None)
            if isinstance(value, int):
                return self._STATE_LABELS.get(value, "unknown")
        try:
            coerced = int(state)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._normalize_state_name(str(state))
        return self._STATE_LABELS.get(coerced, "unknown")

    @staticmethod
    def _normalize_state_name(raw: str) -> str:
        if not raw:
            return "unknown"
        lowered = raw.lower()
        if lowered.startswith("state."):
            lowered = lowered.split(".", 1)[1]
        return lowered

    def _mrl_to_display_name(self, mrl: str) -> str:
        if not mrl:
            return ""
        if mrl.startswith("file://"):
            try:
                return Path(unquote(mrl[7:])).name
            except ValueError:
                return unquote(mrl[7:])
        return unquote(mrl)

    def _set_playlist(self, items: List[MediaItem], start_index: int = 0) -> None:
        self._player.stop()
        self._playlist = list(items)
        self._rebuild_media_list()
        if self._playlist:
            self._logger.info("Playlist loaded with %d items", len(self._playlist))
            self._play_index(min(start_index, len(self._playlist) - 1))
        else:
            self._load_background_clip()
