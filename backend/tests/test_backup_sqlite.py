import sqlite3
from pathlib import Path

import pytest
from scripts.backup_sqlite import run_backup, run_backups


def _make_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('x')")


def test_run_backup_copies_db(tmp_path: Path) -> None:
    src = tmp_path / "app.db"
    _make_db(src)
    backup_dir = tmp_path / "backup"

    run_backup(str(src), str(backup_dir), keep=7, ts="20261003-020000")

    dst = backup_dir / "app-20261003-020000.db"
    assert dst.exists()
    with sqlite3.connect(str(dst)) as conn:
        assert conn.execute("SELECT v FROM t").fetchone() == ("x",)


def test_run_backup_retains_latest_per_source(tmp_path: Path) -> None:
    src = tmp_path / "optuna.db"
    _make_db(src)
    backup_dir = tmp_path / "backup"

    for day in range(1, 5):
        run_backup(str(src), str(backup_dir), keep=2, ts=f"2026100{day}-000000")

    assert [p.name for p in sorted(backup_dir.glob("optuna-*.db"))] == [
        "optuna-20261003-000000.db",
        "optuna-20261004-000000.db",
    ]


def test_run_backup_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_backup(str(tmp_path / "missing.db"), str(tmp_path / "backup"), keep=7)


def test_run_backups_skips_missing_and_backs_up_existing(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    _make_db(app_db)
    backup_dir = tmp_path / "backup"

    created = run_backups([str(app_db), str(tmp_path / "optuna.db")], str(backup_dir), keep=7, ts="20261003-020000")

    assert created == 1
    assert (backup_dir / "app-20261003-020000.db").exists()
    assert not list(backup_dir.glob("optuna-*.db"))


def test_run_backups_returns_zero_when_nothing_exists(tmp_path: Path) -> None:
    created = run_backups([str(tmp_path / "app.db"), str(tmp_path / "optuna.db")], str(tmp_path / "backup"), keep=7)

    assert created == 0
