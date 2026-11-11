#!/usr/bin/env python3
"""
Automated Database Backup & Restore Utility for BTC Quantum Intelligence
Uses SQLite Online Backup API for safe, non-blocking snapshots in WAL mode.
"""

import os
import sys
import time
import shutil
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Locate project root and backend path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_DB_PATH = PROJECT_DIR / "backend" / "data" / "btc_quantum.db"
DEFAULT_BACKUP_DIR = PROJECT_DIR / "backups"

def get_db_path() -> Path:
    env_path = os.getenv("DB_PATH")
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = PROJECT_DIR / p
        return p
    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH
    # Fallback to local root db if exists
    root_db = PROJECT_DIR / "backend" / "btc_quantum.db"
    if root_db.exists():
        return root_db
    return DEFAULT_DB_PATH

def check_integrity(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        conn.close()
        return result is not None and result[0] == "ok"
    except Exception as e:
        print(f"Integrity check failed with error: {e}", file=sys.stderr)
        return False

def backup_db(backup_dir: Path, max_backups: int = 30) -> Path:
    source_path = get_db_path()
    if not source_path.exists():
        raise FileNotFoundError(f"Source database not found at: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_file = backup_dir / f"ledger-{timestamp}.db"
    temp_file = backup_dir / f".ledger-{timestamp}.tmp"

    print(f"Creating consistent online snapshot of {source_path}...")
    src_conn = sqlite3.connect(str(source_path))
    dst_conn = sqlite3.connect(str(temp_file))

    try:
        # Atomic online SQLite backup
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        # Verify integrity
        if not check_integrity(temp_file):
            if temp_file.exists():
                temp_file.unlink()
            raise RuntimeError("Backup failed integrity check!")

        # Move verified temporary file to final backup destination
        temp_file.rename(backup_file)
        file_size_kb = backup_file.stat().st_size / 1024.0
        print(f"✓ Backup successfully created: {backup_file} ({file_size_kb:.1f} KB)")

        # Rotate old backups
        all_backups = sorted(backup_dir.glob("ledger-*.db"))
        if len(all_backups) > max_backups:
            to_remove = all_backups[:-max_backups]
            for old in to_remove:
                old.unlink()
                print(f"Pruned older backup: {old.name}")

        return backup_file
    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        raise e

def restore_db(backup_file: Path) -> bool:
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found at: {backup_file}")

    print(f"Verifying integrity of backup {backup_file}...")
    if not check_integrity(backup_file):
        raise RuntimeError(f"Cannot restore: Backup file {backup_file} is corrupted or invalid.")

    target_path = get_db_path()
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Clean any old WAL/SHM files
    wal_file = target_path.with_name(f"{target_path.name}-wal")
    shm_file = target_path.with_name(f"{target_path.name}-shm")

    # Safety copy of current db if it exists
    if target_path.exists():
        safety_copy = target_dir / f"safety-pre-restore-{int(time.time())}.db"
        shutil.copy2(target_path, safety_copy)
        print(f"Created safety copy of existing database: {safety_copy}")

    if wal_file.exists():
        wal_file.unlink()
    if shm_file.exists():
        shm_file.unlink()

    shutil.copy2(backup_file, target_path)
    print(f"✓ Database restored successfully to: {target_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="BTC Quantum Database Backup & Restore Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a verified snapshot of the database")
    backup_parser.add_argument("--dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Backup destination directory")
    backup_parser.add_argument("--keep", type=int, default=30, help="Number of recent backups to keep")

    restore_parser = subparsers.add_parser("restore", help="Restore database from a verified snapshot")
    restore_parser.add_argument("file", type=Path, help="Path to backup file")

    args = parser.parse_args()

    if args.command == "backup":
        try:
            backup_db(args.dir, args.keep)
        except Exception as e:
            print(f"Error during backup: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "restore":
        try:
            restore_db(args.file)
        except Exception as e:
            print(f"Error during restore: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
