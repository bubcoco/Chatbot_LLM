"""Event-loop helpers."""

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

# psycopg async cannot run on Windows' default ProactorEventLoop.
UVICORN_LOOP: str = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"


def run(coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run() replacement that uses SelectorEventLoop on Windows."""
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coro)
