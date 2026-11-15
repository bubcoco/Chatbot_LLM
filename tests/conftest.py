import asyncio
import os

import psycopg
import pytest

from supportkit.db import create_pool
from supportkit.settings import get_settings

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


def pytest_asyncio_loop_factories(config, item):
    # Psycopg async needs a selector loop on Windows. Must be a non-empty mapping.
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture(scope="session")
def database_url() -> str:
    url = get_settings().database_url
    try:
        with psycopg.connect(url, connect_timeout=2):
            pass
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    return url


@pytest.fixture
async def pool(database_url):
    async with create_pool(database_url, max_size=4) as p:
        yield p
