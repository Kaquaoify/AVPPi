"""Entrypoint for AVPPi FastAPI application."""

from __future__ import annotations

import uvicorn

from .api import create_app
from .core import ApplicationCore
from .logging_setup import setup_logging
from .settings import ROOT_DIR, load_config


CONFIG = load_config()
setup_logging(CONFIG.log_directory)
STATE_FILE = ROOT_DIR / "data" / "state.json"
CORE = ApplicationCore(CONFIG, STATE_FILE)
app = create_app(CORE)


def main() -> None:
    """Launch the uvicorn server."""
    uvicorn.run(
        "app.main:app",
        host=CONFIG.api_host,
        port=CONFIG.api_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()

