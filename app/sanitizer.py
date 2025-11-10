"""Media sanitization helpers using ffprobe/ffmpeg."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, List

from .settings import AppConfig


class SanitizerError(Exception):
    """Raised when a sanitisation step fails."""


SAFE_PIXEL_FORMATS = {"yuv420p"}
SAFE_PROFILES = {"High", "Main", "Baseline"}
SAFE_CODECS = {"h264"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}


class MediaSanitizer:
    """Inspect and, if necessary, transcode videos into a safe format."""

    def __init__(self, config: AppConfig, logger: logging.Logger | None = None) -> None:
        self._media_dir = Path(config.media_directory)
        self._logger = (logger or logging.getLogger("avppi")).getChild("sanitizer")

    def sanitize(self) -> List[str]:
        sanitized: List[str] = []
        for media in self._iter_media_files():
            if not self._needs_transcode(media):
                continue
            self._logger.info("Sanitising %s", media.name)
            try:
                self._transcode(media)
                sanitized.append(media.name)
            except SanitizerError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise SanitizerError(f"Failed to sanitise {media}: {exc}") from exc
        return sanitized

    def _iter_media_files(self) -> Iterable[Path]:
        if not self._media_dir.exists():
            return []
        return (path for path in self._media_dir.rglob("*") if self._is_candidate(path))

    @staticmethod
    def _is_candidate(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS

    def _needs_transcode(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,profile,pix_fmt,field_order",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            self._logger.warning("ffprobe failed for %s: %s", path.name, exc.stderr.strip())
            return True

        try:
            data = json.loads(result.stdout or "{}")
            stream = data.get("streams", [{}])[0]
        except (json.JSONDecodeError, IndexError):
            return True

        codec = str(stream.get("codec_name", "")).lower()
        profile = str(stream.get("profile", ""))
        pix_fmt = str(stream.get("pix_fmt", "")).lower()
        field = str(stream.get("field_order", "")).lower()

        if codec not in SAFE_CODECS:
            return True
        if profile and profile not in SAFE_PROFILES:
            return True
        if pix_fmt and pix_fmt not in SAFE_PIXEL_FORMATS:
            return True
        if field and field != "progressive":
            return True
        return False

    def _transcode(self, path: Path) -> None:
        tmp_dir = path.parent
        with tempfile.NamedTemporaryFile(prefix=path.stem, suffix=".mp4", dir=tmp_dir, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "yadif=0:-1:0",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(tmp_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.move(path, backup)
            shutil.move(tmp_path, path)
            backup.unlink(missing_ok=True)
        except subprocess.CalledProcessError as exc:
            raise SanitizerError(
                f"ffmpeg failed for {path.name}: {exc.stderr.decode('utf-8', 'ignore') if exc.stderr else exc}"
            ) from exc
        finally:
            tmp_path.unlink(missing_ok=True)
