"""scripts/backup.py: dump command, archive layout, retention and failure cleanup."""

import gzip
import importlib.util
import json
import tarfile
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup.py"


@pytest.fixture()
def backup():
    spec = importlib.util.spec_from_file_location("backup_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dump_command_keeps_the_password_out_of_the_arguments(backup):
    command, env, database = backup.mysqldump_command(
        "mysql+pymysql://app:s3cret@127.0.0.1:3307/stock_manager",
    )
    assert database == "stock_manager"
    assert env == {"MYSQL_PWD": "s3cret"}
    assert not any("s3cret" in part for part in command)
    assert "--user=app" in command and "--host=127.0.0.1" in command and "--port=3307" in command
    assert "--single-transaction" in command and command[-1] == "stock_manager"


def test_dump_command_uses_the_socket_and_no_password(backup):
    command, env, _ = backup.mysqldump_command(
        "mysql+pymysql://root@localhost/stock_manager?unix_socket=/tmp/mysql.sock",
    )
    assert "--socket=/tmp/mysql.sock" in command
    assert not any(part.startswith("--host") for part in command)
    assert env == {}


def test_dump_command_rejects_other_databases(backup):
    with pytest.raises(SystemExit, match="MySQL only"):
        backup.mysqldump_command("sqlite:///stock.db")


def _fake_dump(backup, monkeypatch, content=b"-- dump\n"):
    def dump(database_url, target):
        with gzip.open(target, "wb") as output:
            output.write(content)
        return "stock_manager"

    monkeypatch.setattr(backup, "dump_database", dump)


def test_backup_writes_dump_media_and_manifest(backup, tmp_path, monkeypatch):
    media = tmp_path / "media"
    (media / "photos" / "ab").mkdir(parents=True)
    (media / "photos" / "ab" / "ab12.jpg").write_bytes(b"jpeg")
    (media / ".DS_Store").write_bytes(b"x")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://root@localhost/stock_manager")
    monkeypatch.setenv("MEDIA_DIR", str(media))
    _fake_dump(backup, monkeypatch)

    folder = backup.run_backup(tmp_path / "out", 14, now=datetime(2026, 11, 25, 3, 15, 0))

    assert folder.name == "20261125-031500"
    assert sorted(path.name for path in folder.iterdir()) == [
        "database.sql.gz", "manifest.json", "media.tar.gz",
    ]
    with gzip.open(folder / "database.sql.gz") as dump:
        assert dump.read() == b"-- dump\n"
    with tarfile.open(folder / "media.tar.gz") as archive:
        assert archive.getnames() == ["media/photos/ab/ab12.jpg"]
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["database"] == "stock_manager" and manifest["media_files"] == 1
    assert manifest["files"]["media.tar.gz"]["sha256"] == backup._sha256(folder / "media.tar.gz")
    assert not any(path.name.startswith(".") for path in (tmp_path / "out").iterdir())


def test_backup_without_media_dir_only_dumps_the_database(backup, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://root@localhost/stock_manager")
    monkeypatch.delenv("MEDIA_DIR", raising=False)
    _fake_dump(backup, monkeypatch)
    folder = backup.run_backup(tmp_path, 3, now=datetime(2026, 11, 25))
    assert sorted(path.name for path in folder.iterdir()) == ["database.sql.gz", "manifest.json"]
    assert json.loads((folder / "manifest.json").read_text())["media_files"] is None


def test_failed_backup_leaves_no_folder_and_keeps_old_backups(backup, tmp_path, monkeypatch):
    old = tmp_path / "20261101-000000"
    old.mkdir()
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://root@localhost/stock_manager")
    monkeypatch.delenv("MEDIA_DIR", raising=False)

    def broken(database_url, target):
        target.write_bytes(b"partial")
        raise SystemExit("mysqldump failed: access denied")

    monkeypatch.setattr(backup, "dump_database", broken)
    with pytest.raises(SystemExit, match="access denied"):
        backup.run_backup(tmp_path, 1, now=datetime(2026, 11, 25))
    assert [path.name for path in tmp_path.iterdir()] == ["20261101-000000"]


def test_prune_keeps_the_newest_and_ignores_other_entries(backup, tmp_path):
    for name in ("20261120-000000", "20261121-000000", "20261122-000000", "notes", ".x.partial"):
        (tmp_path / name).mkdir()
    (tmp_path / "README.txt").write_text("keep me")
    assert backup.prune(tmp_path, 2) == ["20261120-000000"]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".x.partial", "20261121-000000", "20261122-000000", "README.txt", "notes",
    ]


def test_main_requires_a_destination(backup, monkeypatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    monkeypatch.setattr(backup, "_load_env", lambda: None)
    with pytest.raises(SystemExit):
        backup.main([])
