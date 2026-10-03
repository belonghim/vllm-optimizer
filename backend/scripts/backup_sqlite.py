#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DBS = ["/data/app.db", "/data/optuna.db"]


def run_backup(db_path: str, backup_dir: str, keep: int, ts: str | None = None) -> None:
    src = Path(db_path)
    if not src.exists():
        raise FileNotFoundError(f"Source DB not found: {src}")

    dst_dir = Path(backup_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    ts = ts or datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = dst_dir / f"{src.stem}-{ts}.db"

    with sqlite3.connect(str(src)) as src_conn:
        with sqlite3.connect(str(dst)) as dst_conn:
            src_conn.backup(dst_conn)

    print(f"Backup created: {dst}")

    backups = sorted(dst_dir.glob(f"{src.stem}-*.db"))
    for old in backups[:-keep]:
        old.unlink()
        print(f"Deleted old backup: {old}")


def run_backups(dbs: list[str], backup_dir: str, keep: int, ts: str | None = None) -> int:
    """Back up every existing DB; missing sources are skipped (optuna.db may not exist yet)."""
    ts = ts or datetime.now().strftime("%Y%m%d-%H%M%S")
    created = 0
    for db in dbs:
        if not Path(db).exists():
            print(f"WARNING: skipping missing DB: {db}")
            continue
        run_backup(db, backup_dir, keep, ts=ts)
        created += 1
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="WAL-safe SQLite backup for vLLM Optimizer")
    parser.add_argument(
        "--db",
        action="append",
        dest="dbs",
        help=f"Source DB path (repeatable; default: {', '.join(DEFAULT_DBS)})",
    )
    parser.add_argument("--backup-dir", default="/data/backup", help="Backup output directory (default: /data/backup)")
    parser.add_argument("--keep", type=int, default=7, help="Number of daily backups to retain (default: 7)")
    args = parser.parse_args()

    if run_backups(args.dbs or DEFAULT_DBS, args.backup_dir, args.keep) == 0:
        raise SystemExit("No databases found to back up")


if __name__ == "__main__":
    main()
