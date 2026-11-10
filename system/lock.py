"""Prevent multiple bot pollers from running against one data directory (Linux)."""

import fcntl
from .store import ROOT


def acquire():
    handle = (ROOT / "worker.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise SystemExit(
            "Another instance is already running for this DATA_DIR. Stop it before starting a second poller."
        )
    return handle
