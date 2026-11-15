"""Uvicorn entry point."""

import uvicorn

from supportkit.aio import UVICORN_LOOP


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(
        "supportkit.api.app:create_app", factory=True, host=host, port=port, loop=UVICORN_LOOP
    )
