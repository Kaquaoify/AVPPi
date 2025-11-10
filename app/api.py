"""FastAPI app factory for AVPPi."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .core import ApplicationCore
from .media_catalog import MediaItem
from .vlc_controller import VLCError


class VolumeRequest(BaseModel):
    level: int = Field(ge=0, le=100)


class InsertRequest(BaseModel):
    filename: str


class LanguageRequest(BaseModel):
    language: str


class RcloneConfigRequest(BaseModel):
    token: str
    remote_path: Optional[str] = None


class ScheduleRequest(BaseModel):
    enabled: bool
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    days: List[int] = Field(default_factory=list)

    @field_validator("days")
    @classmethod
    def _validate_days(cls, value: List[int]) -> List[int]:
        if any((day < 0 or day > 6) for day in value):
            raise ValueError("Days must be between 0 (Monday) and 6 (Sunday).")
        return value


class SyncScheduleRequest(BaseModel):
    enabled: bool
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class OperationResponse(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


def _media_item_to_dict(item: MediaItem) -> Dict[str, Any]:
    return {
        "name": item.name,
        "size_bytes": item.size_bytes,
        "modified_at": item.modified_at,
    }


def create_app(core: ApplicationCore) -> FastAPI:
    """Instantiate the FastAPI app with routes and dependencies."""
    app = FastAPI(title="AVPPi", version="1.0.0")
    app_dir = Path(__file__).resolve().parent
    static_dir = app_dir / "web" / "static"
    template_path = app_dir / "web" / "templates" / "index.html"
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount("/locales", StaticFiles(directory=locales_dir), name="locales")

    @app.on_event("startup")
    async def _startup() -> None:
        core.initialise()

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(template_path)

    def _wrap_vlc_call(action):
        try:
            return action()
        except VLCError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    def _safe_status() -> Dict[str, Any]:
        try:
            return core.vlc.get_status()
        except VLCError as exc:
            if hasattr(core, "_logger"):
                core._logger.warning("Unable to fetch VLC status: %s", exc)  # type: ignore[attr-defined]
            return {
                "state": "unknown",
                "volume_percent": str(core.vlc.get_volume_percent()),
                "current_track": "",
            }

    @app.get("/api/media")
    async def list_media() -> Dict[str, Any]:
        items = core.list_media()
        return {"videos": [_media_item_to_dict(item) for item in items]}

    @app.get("/api/status")
    async def status() -> Dict[str, Any]:
        media = core.list_media()
        status_data = _safe_status()
        return {
            "vlc": status_data,
            "language": core.state.get_language(),
            "videos": [_media_item_to_dict(item) for item in media],
        }

    @app.post("/api/control/play-pause", response_model=OperationResponse)
    async def play_pause() -> OperationResponse:
        _wrap_vlc_call(core.vlc.pause_toggle)
        return OperationResponse(success=True, message="Toggled play/pause")

    @app.post("/api/control/next", response_model=OperationResponse)
    async def next_track() -> OperationResponse:
        _wrap_vlc_call(core.vlc.next_track)
        return OperationResponse(success=True, message="Advanced to next video")

    @app.post("/api/control/previous", response_model=OperationResponse)
    async def previous_track() -> OperationResponse:
        _wrap_vlc_call(core.vlc.previous_track)
        return OperationResponse(success=True, message="Moved to previous video")

    @app.post("/api/control/volume", response_model=OperationResponse)
    async def set_volume(payload: VolumeRequest) -> OperationResponse:
        _wrap_vlc_call(lambda: core.vlc.set_volume_percent(payload.level))
        return OperationResponse(success=True, message="Volume updated")

    @app.post("/api/playlist/insert", response_model=OperationResponse)
    async def playlist_insert(payload: InsertRequest) -> OperationResponse:
        inserted = core.insert_after_current(payload.filename)
        if not inserted:
            raise HTTPException(status_code=404, detail="Video not found")
        return OperationResponse(success=True, message="Video inserted into playlist")

    @app.post("/api/settings/language", response_model=OperationResponse)
    async def change_language(payload: LanguageRequest) -> OperationResponse:
        core.state.set_language(payload.language)
        return OperationResponse(success=True, message="Language updated")

    @app.post("/api/system/rescan", response_model=OperationResponse)
    async def rescan_library() -> OperationResponse:
        media = _wrap_vlc_call(core.rescan_media)
        return OperationResponse(
            success=True,
            message="Media library rescanned",
            details={"count": len(media)},
        )

    @app.post("/api/system/restart", response_model=OperationResponse)
    async def restart_system(background: BackgroundTasks) -> OperationResponse:
        if not core.config.allow_shutdown_commands:
            raise HTTPException(status_code=403, detail="Restart disabled by configuration")
        background.add_task(_run_restart_command, core.config.restart_command)
        return OperationResponse(success=True, message="System restart initiated")

    @app.post("/api/rclone/sync", response_model=OperationResponse)
    async def rclone_sync() -> OperationResponse:
        if core.rclone.is_busy():
            raise HTTPException(status_code=409, detail="An rclone operation is already running")
        try:
            result = await core.sync_and_reload()
        except VLCError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return OperationResponse(success=result.success, message="Sync completed", details={"returncode": result.returncode})

    @app.post("/api/rclone/test", response_model=OperationResponse)
    async def rclone_test() -> OperationResponse:
        if core.rclone.is_busy():
            raise HTTPException(status_code=409, detail="An rclone operation is already running")
        result = await core.run_rclone_test()
        return OperationResponse(success=result.success, message="Test completed", details={"returncode": result.returncode})

    @app.post("/api/rclone/config", response_model=OperationResponse)
    async def rclone_config(payload: RcloneConfigRequest) -> OperationResponse:
        if core.rclone.is_busy():
            raise HTTPException(status_code=409, detail="Cannot update config during rclone job")
        path = await core.update_rclone_config(payload.token, payload.remote_path)
        return OperationResponse(success=True, message="Configuration saved", details={"path": str(path)})

    @app.post("/api/rclone/sanitize", response_model=OperationResponse)
    async def rclone_sanitize() -> OperationResponse:
        if core.rclone.is_busy():
            raise HTTPException(status_code=409, detail="Cannot sanitize while rclone job is running")
        sanitized = await core.sanitize_media()
        return OperationResponse(
            success=True,
            message="Sanitisation completed",
            details={"processed": sanitized, "count": len(sanitized)},
        )

    @app.get("/api/rclone/logs")
    async def rclone_logs() -> Dict[str, List[str]]:
        return {"logs": core.rclone.get_recent_logs()}

    @app.get("/api/settings/summary")
    async def settings_summary() -> Dict[str, Any]:
        rclone = core.state.get_rclone_settings()
        return {
            "language": core.state.get_language(),
            "remote_name": rclone.get("remote_name"),
            "remote_path": rclone.get("remote_path"),
            "local_directory": str(core.config.media_directory),
            "rclone_config_path": str(core.config.rclone_config_path),
            "schedule": core.state.get_schedule_settings(),
            "sync_schedule": core.state.get_sync_schedule_settings(),
        }

    @app.post("/api/settings/schedule", response_model=OperationResponse)
    async def update_schedule(payload: ScheduleRequest) -> OperationResponse:
        try:
            core.state.update_schedule_settings(
                enabled=payload.enabled,
                start=payload.start,
                end=payload.end,
                days=payload.days,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        core.scheduler.request_check()
        return OperationResponse(success=True, message="Schedule updated")

    @app.post("/api/settings/sync-schedule", response_model=OperationResponse)
    async def update_sync_schedule(payload: SyncScheduleRequest) -> OperationResponse:
        try:
            core.state.update_sync_schedule_settings(enabled=payload.enabled, time=payload.time)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return OperationResponse(success=True, message="Sync schedule updated")

    return app


def _run_restart_command(command: str) -> None:
    """Execute the restart command in the background."""
    subprocess.Popen(shlex.split(command))  # noqa: S603,S607
