"""Helpers to interact with rclone."""

from __future__ import annotations

import logging
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Iterable, List, Optional

from .settings import AppConfig
from .state_manager import StateManager


@dataclass
class RcloneCommandResult:
    """Result of an rclone invocation."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


class RcloneManager:
    """Encapsulates rclone operations and logging."""

    def __init__(self, config: AppConfig, state: StateManager) -> None:
        self._config = config
        self._state = state
        self._logger = logging.getLogger("avppi.rclone")
        self._lock = threading.RLock()
        self._log_buffer: Deque[str] = deque(maxlen=500)
        self._active_job: Optional[str] = None

    def _append_log(self, message: str) -> None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"{timestamp} UTC | {message}"
        self._log_buffer.append(formatted)
        self._logger.info(message)

    def get_recent_logs(self) -> List[str]:
        with self._lock:
            return list(self._log_buffer)

    def _run_rclone(self, args: Iterable[str]) -> RcloneCommandResult:
        command = [self._config.rclone_binary, *args]
        self._append_log(f"Running command: {' '.join(command)}")
        process = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        if stdout:
            for line in stdout.splitlines():
                self._append_log(f"rclone stdout | {line}")
        if stderr:
            for line in stderr.splitlines():
                self._append_log(f"rclone stderr | {line}")
        success = process.returncode == 0
        if success:
            self._append_log("Command completed successfully")
        else:
            self._append_log(f"Command failed with exit code {process.returncode}")
        return RcloneCommandResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
        )

    def _build_remote_path(self, remote_path: Optional[str] = None) -> str:
        settings = self._state.get_rclone_settings()
        remote_name = settings.get("remote_name") or self._config.remote_name
        remote_dir = remote_path or settings.get("remote_path") or self._config.remote_path
        return f"{remote_name}:{remote_dir}"

    def sync_media(self, remote_path: Optional[str] = None) -> RcloneCommandResult:
        with self._lock:
            if self._active_job:
                raise RuntimeError(f"Another rclone job is running: {self._active_job}")
            self._active_job = "sync"
        try:
            remote = self._build_remote_path(remote_path)
            local_dir = self._config.media_directory
            local_dir.mkdir(parents=True, exist_ok=True)
            self._append_log(f"Starting sync from {remote} to {local_dir}")
            return self._run_rclone(["sync", remote, str(local_dir), "--create-empty-src-dirs"])
        finally:
            with self._lock:
                self._active_job = None

    def test_connection(self) -> RcloneCommandResult:
        with self._lock:
            if self._active_job:
                raise RuntimeError(f"Another rclone job is running: {self._active_job}")
            self._active_job = "test"
        try:
            remote = self._build_remote_path()
            self._append_log(f"Testing connectivity to {remote}")
            return self._run_rclone(["lsf", remote, "--max-depth", "1", "--files-only"])
        finally:
            with self._lock:
                self._active_job = None

    def is_busy(self) -> bool:
        with self._lock:
            return self._active_job is not None

    def update_config(self, token: str, remote_path: Optional[str] = None) -> Path:
        """Write rclone configuration with the provided token."""
        config_path = self._config.rclone_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        remote_name = self._config.remote_name
        self._append_log(f"Updating rclone config at {config_path}")
        content = (
            f"[{remote_name}]\n"
            "type = drive\n"
            "scope = drive.file\n"
            "token = " + token.strip() + "\n"
        )
        with config_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        if remote_path:
            self._state.update_rclone_settings(remote_path=remote_path)
        self._state.update_rclone_settings(token=token)
        self._append_log("rclone configuration was updated")
        return config_path

