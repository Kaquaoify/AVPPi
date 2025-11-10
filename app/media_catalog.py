"""Media directory helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}


@dataclass
class MediaItem:
    """Represents a video file discovered in the media directory."""

    name: str
    path: Path
    size_bytes: int
    modified_at: float


def is_supported_video(path: Path) -> bool:
    """Return True if the path has a supported video extension."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_media(directory: Path) -> List[MediaItem]:
    """Return a sorted list of available media items."""
    items: List[MediaItem] = []
    if not directory.exists():
        return items
    for entry in directory.iterdir():
        if entry.is_file() and is_supported_video(entry):
            stat = entry.stat()
            items.append(
                MediaItem(
                    name=entry.name,
                    path=entry,
                    size_bytes=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )
    items.sort(key=lambda item: item.name.lower())
    return items


def build_vlc_playlist_args(items: Iterable[MediaItem]) -> List[str]:
    """Return a list of filesystem paths as strings for VLC."""
    return [str(item.path) for item in items]
