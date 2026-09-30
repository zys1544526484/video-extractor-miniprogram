from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def backup_database(source: Path, destination: Path) -> None:
    """Copy a live SQLite snapshot to a new, private file without overwriting anything."""
    source = source.resolve(strict=True)
    destination = destination.resolve()
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as original:
        # Reserve only a new file; even an existing empty file must be preserved.
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(destination)) as snapshot:
                original.backup(snapshot, pages=256)
                if snapshot.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise RuntimeError("SQLite backup failed integrity validation")
        except BaseException:
            destination.unlink()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up SQLite to a NEW file; never overwrite.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        backup_database(args.source, args.destination)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f"SQLite backup failed ({type(error).__name__}); existing files preserved.\n")
    print("SQLite backup and integrity check PASS")


if __name__ == "__main__":
    main()
