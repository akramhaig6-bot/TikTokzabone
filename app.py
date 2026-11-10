#!/usr/bin/env python3
"""Single-process web panel + Telegram polling and durable delivery workers."""

import os, threading, logging
from system.web import create_app
from system.telegram import run

app = create_app()
if __name__ == "__main__":
    from waitress import serve

    from system.lock import acquire

    worker_lock = acquire()
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    threading.Thread(target=run, args=(stop,), daemon=True).start()
    try:
        serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), threads=8)
    finally:
        stop.set()
        worker_lock.close()
