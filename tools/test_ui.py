#!/usr/bin/env python3
"""Run DOM acceptance tests with a disposable data directory; never reuse real users."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def main():
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-isolated-", dir=cache) as data_dir:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "DATA_DIR": data_dir,
            "PORT": str(port),
            "COOKIE_SECURE": "0",
            "COOKIE_PARTITIONED": "0",
            "SETUP_SECRET": "",
        }
        with (cache / "ui-server.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if server.poll() is not None:
                        raise RuntimeError(
                            "UI test server exited. See .cache/ui-server.log"
                        )
                    try:
                        with urllib.request.urlopen(
                            base + "/api/session", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise RuntimeError("UI test server did not become ready")
                        time.sleep(0.1)
                result = subprocess.run(
                    ["node", "tests/ui_smoke.cjs"],
                    cwd=ROOT,
                    env={**env, "TEST_BASE_URL": base},
                    timeout=120,
                )
                return result.returncode
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    sys.exit(main())
