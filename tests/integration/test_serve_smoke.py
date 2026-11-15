"""Real `supportkit serve` subprocess: proves the selector event loop works under uvicorn (Windows)."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
import pytest

SCRIPTS = Path(sys.executable).parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_serve_chat_against_seed(database_url):
    with psycopg.connect(database_url, connect_timeout=2) as conn:
        row = conn.execute(
            "SELECT 1 FROM orders WHERE shop_id = 'baan-bai-cha' AND customer_id = 'C-0001' "
            "AND order_no = 'BC-1042'"
        ).fetchone()
    if row is None:
        pytest.skip("baan-bai-cha seed rows absent")

    port = _free_port()
    env = {
        **os.environ,
        "SUPPORTKIT_DEMO_MODE": "true",
        "SUPPORTKIT_MODEL": "fake:rules",
        "DATABASE_URL": database_url,
    }
    exe = SCRIPTS / ("supportkit.exe" if sys.platform == "win32" else "supportkit")
    cmd = (
        [str(exe), "serve", "--port", str(port)]
        if exe.exists()
        else [sys.executable, "-m", "supportkit.cli", "serve", "--port", str(port)]
    )
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    base = f"http://127.0.0.1:{port}"
    session = f"smoke{int(time.time())}"
    try:
        deadline = time.monotonic() + 40
        while True:
            if proc.poll() is not None:
                pytest.fail(f"server exited early with code {proc.returncode}")
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.fail("server did not become healthy in time")
            time.sleep(0.3)

        headers = {
            "X-Demo-Shop-Id": "baan-bai-cha",
            "X-Demo-Customer-Id": "C-0001",
            "X-Demo-Session": session,
        }
        r = httpx.post(
            f"{base}/chat",
            headers=headers,
            json={"message": "Where is order BC-1042?"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert "KEX26111042TH" in r.json()["reply"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        # Clean up the demo thread this smoke test created; a failure here should surface.
        with psycopg.connect(database_url, connect_timeout=2, autocommit=True) as conn:
            tid = f"baan-bai-cha:web:demo-C-0001-{session}"
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                conn.execute(f"DELETE FROM {t} WHERE thread_id = %s", (tid,))
