"""Configuration loading utilities for AVPPi."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "app_config.yaml"


@dataclass(frozen=True)
class AppConfig:
    """Static configuration values loaded from YAML."""

    media_directory: Path
    log_directory: Path
    vlc_options: List[str]
    vlc_background_media: str
    remote_name: str
    remote_path: str
    default_language: str
    api_host: str
    api_port: int
    rclone_binary: str
    rclone_config_path: Path
    restart_command: str
    allow_shutdown_commands: bool
    max_playlist_items: int


def _ensure_path(path_value: Any) -> Path:
    """Return a resolved Path from a YAML scalar."""
    path = Path(str(path_value)).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load the application configuration from YAML."""
    path = config_path or Path(os.environ.get("AVPPI_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    data = _load_yaml(path)

    return AppConfig(
        media_directory=_ensure_path(data.get("media_directory", "media")),
        log_directory=_ensure_path(data.get("log_directory", "logs")),
        vlc_options=[str(arg) for arg in data.get("vlc_options", ["--fullscreen", "--quiet"])],
        vlc_background_media=str(data.get("vlc_background_media", "color:black")),
        remote_name=str(data.get("remote_name", "drive")),
        remote_path=str(data.get("remote_path", "AVPPi-medias")),
        default_language=str(data.get("default_language", "fr")),
        api_host=str(data.get("api_host", "0.0.0.0")),
        api_port=int(data.get("api_port", 8000)),
        rclone_binary=str(data.get("rclone_binary", "rclone")),
        rclone_config_path=_ensure_path(
            data.get("rclone_config_path", "~/.config/rclone/rclone.conf")
        ),
        restart_command=str(data.get("restart_command", "sudo /sbin/reboot")),
        allow_shutdown_commands=bool(data.get("allow_shutdown_commands", False)),
        max_playlist_items=int(data.get("max_playlist_items", 500)),
    )
