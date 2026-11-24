#!/usr/bin/env python3
"""Back up the Stock Manager database and recipe photos.

Usage:
    python scripts/backup.py [--dest DIR] [--keep N]

Each run writes one folder named by the local time, for example
`20261125-031500/`, containing:

- `database.sql.gz`: a `mysqldump` of the database in `DATABASE_URL`;
- `media.tar.gz`: the `MEDIA_DIR` folder (skipped when `MEDIA_DIR` is unset);
- `manifest.json`: what was backed up, sizes and SHA-256 checksums.

The folder is written under a temporary name and renamed when complete, so a
failed run never leaves a folder that looks like a finished backup. After a
successful run, only the newest `--keep` backups (default 7, one week of
daily runs) are kept.

Settings come from the environment and the project's `.env`:
`DATABASE_URL`, `MEDIA_DIR`, and `BACKUP_DIR` (the default for `--dest`).
The database password is passed to `mysqldump` through `MYSQL_PWD`, never on
the command line, and is never printed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# A finished backup folder name; anything else in the destination is left alone.
BACKUP_NAME = re.compile(r"^\d{8}-\d{6}$")
DEFAULT_KEEP = 7


def _load_env() -> None:
    """Load `.env` from the project root without overriding the environment."""
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mysqldump_command(database_url: str) -> tuple[list[str], dict[str, str], str]:
    """Return the mysqldump arguments, extra environment, and database name."""
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if not url.drivername.startswith("mysql"):
        raise SystemExit(f"Backup supports MySQL only, not {url.drivername}")
    if not url.database:
        raise SystemExit("DATABASE_URL has no database name")

    command = [
        shutil.which("mysqldump") or "mysqldump",
        "--single-transaction",  # consistent snapshot without locking InnoDB tables
        "--routines", "--triggers", "--events",
        "--hex-blob",
        "--no-tablespaces",  # avoids needing the PROCESS privilege
        # GTID info is only for replicas; with it, MySQL 8 runs FLUSH TABLES,
        # which needs the RELOAD privilege the app user does not have.
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
    ]
    if url.username:
        command.append(f"--user={url.username}")
    socket = url.query.get("unix_socket")
    if socket:
        command.append(f"--socket={socket}")
    else:
        command.append(f"--host={url.host or 'localhost'}")
        command.append(f"--port={url.port or 3306}")
    command.append(url.database)
    env = {"MYSQL_PWD": url.password} if url.password else {}
    return command, env, url.database


def dump_database(database_url: str, target: Path) -> str:
    """Write a gzip-compressed dump of the database to `target`."""
    command, extra_env, database = mysqldump_command(database_url)
    env = {**os.environ, **extra_env}
    with gzip.open(target, "wb") as output:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        assert process.stdout is not None
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            output.write(chunk)
        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        if process.wait() != 0:
            # mysqldump's messages do not contain the password.
            raise SystemExit(f"mysqldump failed: {stderr.strip()}")
    return database


def archive_media(media_dir: Path, target: Path) -> int:
    """Write `media_dir` to a gzip-compressed tar file; return the file count."""
    count = 0
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(media_dir.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                archive.add(path, arcname=Path("media") / path.relative_to(media_dir))
                count += 1
    return count


def prune(dest: Path, keep: int) -> list[str]:
    """Delete finished backups beyond the newest `keep`; return their names."""
    finished = sorted(
        (entry for entry in dest.iterdir() if entry.is_dir() and BACKUP_NAME.match(entry.name)),
        key=lambda entry: entry.name,
    )
    removed = finished[:-keep] if keep > 0 else []
    for entry in removed:
        shutil.rmtree(entry)
    return [entry.name for entry in removed]


def run_backup(dest: Path, keep: int, *, now: datetime | None = None) -> Path:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")
    media_value = os.getenv("MEDIA_DIR", "").strip()
    media_dir = Path(media_value).expanduser() if media_value else None

    dest.mkdir(parents=True, exist_ok=True)
    name = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    final = dest / name
    if final.exists():
        raise SystemExit(f"{final} already exists")
    partial = dest / f".{name}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir()

    try:
        files = {}
        database = dump_database(database_url, partial / "database.sql.gz")
        files["database.sql.gz"] = partial / "database.sql.gz"
        media_count = None
        if media_dir is not None:
            if not media_dir.is_dir():
                raise SystemExit(f"MEDIA_DIR does not exist: {media_dir}")
            media_count = archive_media(media_dir, partial / "media.tar.gz")
            files["media.tar.gz"] = partial / "media.tar.gz"

        manifest = {
            "created_at": name,
            "database": database,
            "media_dir": str(media_dir) if media_dir else None,
            "media_files": media_count,
            "files": {
                key: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
                for key, path in files.items()
            },
        }
        (partial / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        partial.rename(final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise

    removed = prune(dest, keep)
    sizes = ", ".join(f"{key} {info['bytes'] / 1_048_576:.1f} MB" for key, info in manifest["files"].items())
    print(f"Backup written: {final} ({sizes})")
    if removed:
        print(f"Removed old backups: {', '.join(removed)}")
    return final


def main(argv: list[str] | None = None) -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Back up the Stock Manager database and recipe photos.")
    parser.add_argument("--dest", default=os.getenv("BACKUP_DIR", ""),
                        help="Backup folder (default: BACKUP_DIR)")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                        help=f"Number of backups to keep (default: {DEFAULT_KEEP})")
    args = parser.parse_args(argv)
    if not args.dest:
        parser.error("set BACKUP_DIR or pass --dest")
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    run_backup(Path(args.dest).expanduser(), args.keep)


if __name__ == "__main__":
    sys.exit(main())
