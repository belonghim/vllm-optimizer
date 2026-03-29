#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def run_backup(db_path: str, backup_dir: str, keep: int) -> None:
    src = Path(db_path)
    if not src.exists():
        raise FileNotFoundError(f"Source DB not found: {src}")

    dst_dir = Path(backup_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = dst_dir / f"optimizer-{ts}.db"

    with sqlite3.connect(str(src)) as src_conn:
        with sqlite3.connect(str(dst)) as dst_conn:
            src_conn.backup(dst_conn)

    print(f"Backup created: {dst}")

    backups = sorted(dst_dir.glob("optimizer-*.db"))
    for old in backups[:-keep]:
        old.unlink()
        print(f"Deleted old backup: {old}")


def main() -> None:
    parser = argparse.ArgumentParser(description="WAL-safe SQLite backup for vLLM Optimizer")
    parser.add_argument("--db", default="/data/app.db", help="Source DB path (default: /data/app.db)")
    parser.add_argument("--backup-dir", default="/data/backup", help="Backup output directory (default: /data/backup)")
    parser.add_argument("--keep", type=int, default=7, help="Number of daily backups to retain (default: 7)")
    args = parser.parse_args()
    run_backup(args.db, args.backup_dir, args.keep)


if __name__ == "__main__":
    main()
