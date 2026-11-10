#!/usr/bin/env python3
"""Consistent SQLite snapshot plus the encryption/session keys needed to restore it."""

import argparse, shutil, sqlite3, os
from pathlib import Path
from system.store import ROOT


def backup(destination):
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    source = sqlite3.connect(
        "file:" + str((ROOT / "system.sqlite3").resolve()) + "?mode=ro", uri=True
    )
    target = sqlite3.connect(destination / "system.sqlite3")
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    # No upload deletion is exposed; copy precisely the files referenced by the snapshot.
    snapshot = sqlite3.connect(destination / "system.sqlite3")
    try:
        tables = {
            r[0]
            for r in snapshot.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        filenames = (
            [r[0] for r in snapshot.execute("SELECT stored_name FROM assets")]
            if "assets" in tables
            else []
        )
    finally:
        snapshot.close()
    if filenames:
        (destination / "uploads").mkdir(mode=0o700)
        for filename in filenames:
            if Path(filename).name != filename:
                raise ValueError("Unsafe filename in backup metadata")
            shutil.copyfile(
                ROOT / "uploads" / filename, destination / "uploads" / filename
            )
            os.chmod(destination / "uploads" / filename, 0o600)
    for name in ("encryption.key", "session.key"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, destination / name)
            os.chmod(destination / name, 0o600)
    print(
        "Backup written. Keep this directory private; it contains the Telegram token encryption key."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination")
    backup(p.parse_args().destination)
