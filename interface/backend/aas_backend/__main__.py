"""Run the backend: ``python -m aas_backend`` (binds to 127.0.0.1 only)."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings), host=settings.backend_host, port=settings.backend_port, log_level="info"
    )


if __name__ == "__main__":
    main()
