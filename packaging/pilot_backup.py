"""Offline-capable SQLite + documents snapshot for the single-agency pilot.

Run from a separate scheduled process. A consistent SQLite snapshot is made using
sqlite3.backup (never copy the live WAL database file). Documents are copied into
the archive; upload concurrency must be quiesced by the operator for a guaranteed
cross-resource snapshot. No automatic deletion of older backups.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def backup(data_dir: Path, destination: Path):
    data_dir = data_dir.resolve()
    source_db = data_dir / "policem.sqlite3"
    documents = data_dir / "documents"
    if not source_db.is_file():
        raise FileNotFoundError(f"Database missing: {source_db}")
    if not documents.is_dir():
        raise FileNotFoundError(f"Documents folder missing: {documents}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Backup already exists: {destination}")
    with tempfile.TemporaryDirectory(prefix="policem-backup-") as tmp:
        db_copy = Path(tmp) / "policem.sqlite3"
        with closing(sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(db_copy)) as dst:
                src.backup(dst)
                dst.commit()
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Snapshot database integrity check failed")
        manifest = {"format": 1, "created_utc": int(time.time()), "files": {}}
        partial = destination.with_name(destination.name + ".partial")
        try:
            with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                db_bytes = db_copy.read_bytes()
                archive.writestr("policem.sqlite3", db_bytes)
                manifest["files"]["policem.sqlite3"] = sha256(db_bytes)
                for path in sorted(documents.rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    rel = path.relative_to(documents)
                    if ".." in rel.parts:
                        raise ValueError("Unsafe document path")
                    name = "documents/" + rel.as_posix()
                    data = path.read_bytes()
                    archive.writestr(name, data)
                    manifest["files"][name] = sha256(data)
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            verify(partial)
            partial.rename(destination)
        finally:
            if partial.exists():
                partial.unlink()
    return destination

def verify(archive_path: Path):
    with zipfile.ZipFile(archive_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != 1:
            raise ValueError("Unsupported backup format")
        expected = manifest["files"]
        actual = {i.filename for i in archive.infolist() if not i.is_dir()}
        if actual != set(expected) | {"manifest.json"}:
            raise ValueError("Backup archive file list mismatch")
        for name, digest in expected.items():
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts or "\\" in name:
                raise ValueError("Unsafe archive path")
            if sha256(archive.read(name)) != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        return len(expected)

def restore(archive_path: Path, target: Path):
    # Offline-only: refuse existing data. Caller must stop the Windows service
    # and restore into a new empty location, then validate before cutover.
    if target.exists():
        raise FileExistsError("Restore target already exists; use a new directory")
    verify(archive_path)
    target.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for name in json.loads(archive.read("manifest.json"))["files"]:
                out = target / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.read(name))
        with closing(sqlite3.connect(target / "policem.sqlite3")) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Restored database integrity check failed")
    except BaseException:
        import shutil
        shutil.rmtree(target)
        raise
    return target

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("POLICEM_DATA", str(Path(os.environ.get("PROGRAMDATA", ".")) / "Policem" / "data"))))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    if args.action == "backup":
        print(backup(args.data, args.archive))
    elif args.action == "verify":
        print("Verified files:", verify(args.archive))
    else:
        if args.target is None:
            parser.error("--target is required for restore")
        print(restore(args.archive, args.target))

if __name__ == "__main__":
    main()
